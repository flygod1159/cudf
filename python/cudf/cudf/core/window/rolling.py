# Copyright (c) 2020-2021, NVIDIA CORPORATION

import itertools

import numba
import pandas as pd
from pandas.api.indexers import BaseIndexer

import cudf
from cudf import _lib as libcudf
from cudf.api.types import is_integer, is_number
from cudf.core import column
from cudf.core.column.column import as_column
from cudf.utils import cudautils
from cudf.utils.utils import GetAttrGetItemMixin


class Rolling(GetAttrGetItemMixin):
    """
    Rolling window calculations.

    Parameters
    ----------
    window : int, offset or a BaseIndexer subclass
        Size of the window, i.e., the number of observations used
        to calculate the statistic.
        For datetime indexes, an offset can be provided instead
        of an int. The offset must be convertible to a timedelta.
        As opposed to a fixed window size, each window will be
        sized to accommodate observations within the time period
        specified by the offset.
        If a BaseIndexer subclass is passed, calculates the window
        boundaries based on the defined ``get_window_bounds`` method.
    min_periods : int, optional
        The minimum number of observations in the window that are
        required to be non-null, so that the result is non-null.
        If not provided or ``None``, ``min_periods`` is equal to
        the window size.
    center : bool, optional
        If ``True``, the result is set at the center of the window.
        If ``False`` (default), the result is set at the right edge
        of the window.

    Returns
    -------
    ``Rolling`` object.

    Examples
    --------
    >>> import cudf
    >>> a = cudf.Series([1, 2, 3, None, 4])

    Rolling sum with window size 2.

    >>> print(a.rolling(2).sum())
    0
    1    3
    2    5
    3
    4
    dtype: int64

    Rolling sum with window size 2 and min_periods 1.

    >>> print(a.rolling(2, min_periods=1).sum())
    0    1
    1    3
    2    5
    3    3
    4    4
    dtype: int64

    Rolling count with window size 3.

    >>> print(a.rolling(3).count())
    0    1
    1    2
    2    3
    3    2
    4    2
    dtype: int64

    Rolling count with window size 3, but with the result set at the
    center of the window.

    >>> print(a.rolling(3, center=True).count())
    0    2
    1    3
    2    2
    3    2
    4    1 dtype: int64

    Rolling max with variable window size specified by an offset;
    only valid for datetime index.

    >>> a = cudf.Series(
    ...     [1, 9, 5, 4, np.nan, 1],
    ...     index=[
    ...         pd.Timestamp('20190101 09:00:00'),
    ...         pd.Timestamp('20190101 09:00:01'),
    ...         pd.Timestamp('20190101 09:00:02'),
    ...         pd.Timestamp('20190101 09:00:04'),
    ...         pd.Timestamp('20190101 09:00:07'),
    ...         pd.Timestamp('20190101 09:00:08')
    ...     ]
    ... )

    >>> print(a.rolling('2s').max())
    2019-01-01T09:00:00.000    1
    2019-01-01T09:00:01.000    9
    2019-01-01T09:00:02.000    9
    2019-01-01T09:00:04.000    4
    2019-01-01T09:00:07.000
    2019-01-01T09:00:08.000    1
    dtype: int64

    Apply custom function on the window with the *apply* method

    >>> import numpy as np
    >>> import math
    >>> b = cudf.Series([16, 25, 36, 49, 64, 81], dtype=np.float64)
    >>> def some_func(A):
    ...     b = 0
    ...     for a in A:
    ...         b = b + math.sqrt(a)
    ...     return b
    ...
    >>> print(b.rolling(3, min_periods=1).apply(some_func))
    0     4.0
    1     9.0
    2    15.0
    3    18.0
    4    21.0
    5    24.0
    dtype: float64

    And this also works for window rolling set by an offset

    >>> import pandas as pd
    >>> c = cudf.Series(
    ...     [16, 25, 36, 49, 64, 81],
    ...     index=[
    ...          pd.Timestamp('20190101 09:00:00'),
    ...          pd.Timestamp('20190101 09:00:01'),
    ...          pd.Timestamp('20190101 09:00:02'),
    ...          pd.Timestamp('20190101 09:00:04'),
    ...          pd.Timestamp('20190101 09:00:07'),
    ...          pd.Timestamp('20190101 09:00:08')
    ...      ],
    ...     dtype=np.float64
    ... )
    >>> print(c.rolling('2s').apply(some_func))
    2019-01-01T09:00:00.000     4.0
    2019-01-01T09:00:01.000     9.0
    2019-01-01T09:00:02.000    11.0
    2019-01-01T09:00:04.000     7.0
    2019-01-01T09:00:07.000     8.0
    2019-01-01T09:00:08.000    17.0
    dtype: float64
    """

    _PROTECTED_KEYS = frozenset(("obj",))

    _time_window = False

    def __init__(
        self,
        obj,
        window,
        min_periods=None,
        center=False,
        axis=0,
        win_type=None,
    ):
        self.obj = obj
        self.window = window
        self.min_periods = min_periods
        self.center = center
        self._normalize()
        self.agg_params = {}
        if axis != 0:
            raise NotImplementedError("axis != 0 is not supported yet.")
        self.axis = axis

        if win_type is not None:
            if win_type != "boxcar":
                raise NotImplementedError(
                    "Only the default win_type 'boxcar' is currently supported"
                )
        self.win_type = win_type

    def __getitem__(self, arg):
        if isinstance(arg, tuple):
            arg = list(arg)
        return self.obj[arg].rolling(
            window=self.window,
            min_periods=self.min_periods,
            center=self.center,
        )

    def _apply_agg_series(self, sr, agg_name):
        source_column = sr._column
        min_periods = self.min_periods or 1
        if isinstance(self.window, int):
            preceding_window = None
            following_window = None
            window = self.window
        elif isinstance(self.window, BaseIndexer):
            start, end = self.window.get_window_bounds(
                num_values=len(self.obj),
                min_periods=self.min_periods,
                center=self.center,
                closed=None,
            )
            start = as_column(start, dtype="int32")
            end = as_column(end, dtype="int32")

            idx = cudf.core.column.arange(len(start))
            preceding_window = (idx - start + cudf.Scalar(1, "int32")).astype(
                "int32"
            )
            following_window = (end - idx - cudf.Scalar(1, "int32")).astype(
                "int32"
            )
            window = None
        else:
            preceding_window = as_column(self.window)
            following_window = column.full(
                self.window.size, 0, dtype=self.window.dtype
            )
            window = None

        result_col = libcudf.rolling.rolling(
            source_column=source_column,
            pre_column_window=preceding_window,
            fwd_column_window=following_window,
            window=window,
            min_periods=min_periods,
            center=self.center,
            op=agg_name,
            agg_params=self.agg_params,
        )
        return sr._from_data({sr.name: result_col}, sr._index)

    def _apply_agg_dataframe(self, df, agg_name):
        result_df = cudf.DataFrame({})
        for i, col_name in enumerate(df.columns):
            result_col = self._apply_agg_series(df[col_name], agg_name)
            result_df.insert(i, col_name, result_col)
        result_df.index = df.index
        return result_df

    def _apply_agg(self, agg_name):
        if isinstance(self.obj, cudf.Series):
            return self._apply_agg_series(self.obj, agg_name)
        else:
            return self._apply_agg_dataframe(self.obj, agg_name)

    def sum(self):
        return self._apply_agg("sum")

    def min(self):
        return self._apply_agg("min")

    def max(self):
        return self._apply_agg("max")

    def mean(self):
        return self._apply_agg("mean")

    def var(self, ddof=1):
        self.agg_params["ddof"] = ddof
        return self._apply_agg("var")

    def std(self, ddof=1):
        self.agg_params["ddof"] = ddof
        return self._apply_agg("std")

    def count(self):
        return self._apply_agg("count")

    def apply(self, func, *args, **kwargs):
        """
        Counterpart of `pandas.core.window.Rolling.apply
        <https://pandas.pydata.org/pandas-docs/stable/reference/api/pandas.core.window.rolling.Rolling.apply.html>`_.

        Parameters
        ----------
        func : function
            A user defined function that takes an 1D array as input
        args : tuple
            unsupported.
        kwargs
            unsupported

        See also
        --------
        cudf.Series.applymap : Apply an elementwise function to
            transform the values in the Column.

        Notes
        -----
        See notes of the :meth:`cudf.Series.applymap`

        Example
        -------

        >>> import cudf
        >>> def count_if_gt_3(window):
        ...     count = 0
        ...     for i in window:
        ...             if i > 3:
        ...                     count += 1
        ...     return count
        ...
        >>> s = cudf.Series([0, 1.1, 5.8, 3.1, 6.2, 2.0, 1.5])
        >>> s.rolling(3, min_periods=1).apply(count_if_gt_3)
        0    0
        1    0
        2    1
        3    2
        4    3
        5    2
        6    1
        dtype: int64
        """
        has_nulls = False
        if isinstance(self.obj, cudf.Series):
            if self.obj._column.has_nulls():
                has_nulls = True
        else:
            for col in self.obj._data:
                if self.obj[col].has_nulls:
                    has_nulls = True
        if has_nulls:
            raise NotImplementedError(
                "Handling UDF with null values is not yet supported"
            )
        return self._apply_agg(func)

    def _normalize(self):
        """
        Normalize the *window* and *min_periods* args

        *window* can be:

        * An integer, in which case it is the window size.
          If *min_periods* is unspecified, it is set to be equal to
          the window size.

        * A timedelta offset, in which case it is used to generate
          a column of window sizes to use for each element.
          If *min_periods* is unspecified, it is set to 1.
          Only valid for datetime index.
        """
        window, min_periods = self.window, self.min_periods
        if is_number(window):
            # only allow integers
            if not is_integer(window):
                raise ValueError("window must be an integer")
            if window <= 0:
                raise ValueError("window cannot be zero or negative")
            if self.min_periods is None:
                min_periods = window
        else:
            if isinstance(
                window, (numba.cuda.devicearray.DeviceNDArray, BaseIndexer)
            ):
                # window is a device_array of window sizes or BaseIndexer
                self.window = window
                self.min_periods = min_periods
                return

            if not isinstance(self.obj.index, cudf.core.index.DatetimeIndex):
                raise ValueError(
                    "window must be an integer for non datetime index"
                )

            self._time_window = True

            try:
                window = pd.to_timedelta(window)
                # to_timedelta will also convert np.arrays etc.,
                if not isinstance(window, pd.Timedelta):
                    raise ValueError
                window = window.to_timedelta64()
            except ValueError as e:
                raise ValueError(
                    "window must be integer or convertible to a timedelta"
                ) from e
            if self.min_periods is None:
                min_periods = 1

        self.window = self._window_to_window_sizes(window)
        self.min_periods = min_periods

    def _window_to_window_sizes(self, window):
        """
        For non-fixed width windows,
        convert the window argument into window sizes.
        """
        if is_integer(window):
            return window
        else:
            return cudautils.window_sizes_from_offset(
                self.obj.index._values.data_array_view, window
            )

    def __repr__(self):
        return "{} [window={},min_periods={},center={}]".format(
            self.__class__.__name__, self.window, self.min_periods, self.center
        )


class RollingGroupby(Rolling):
    """
    Grouped rolling window calculation.

    See also
    --------
    cudf.core.window.Rolling
    """

    def __init__(self, groupby, window, min_periods=None, center=False):
        sort_order = groupby.grouping.keys.argsort()

        # TODO: there may be overlap between the columns
        # of `groupby.grouping.keys` and `groupby.obj`.
        # As an optimization, avoid gathering those twice.
        self._group_keys = groupby.grouping.keys.take(sort_order)
        obj = groupby.obj.drop(columns=groupby.grouping._named_columns).take(
            sort_order
        )

        gb_size = groupby.size().sort_index()
        self._group_starts = (
            gb_size.cumsum().shift(1).fillna(0).repeat(gb_size)
        )

        super().__init__(obj, window, min_periods=min_periods, center=center)

    def _window_to_window_sizes(self, window):
        if is_integer(window):
            return cudautils.grouped_window_sizes_from_offset(
                column.arange(len(self.obj)).data_array_view,
                self._group_starts,
                window,
            )
        else:
            return cudautils.grouped_window_sizes_from_offset(
                self.obj.index._values.data_array_view,
                self._group_starts,
                window,
            )

    def _apply_agg(self, agg_name):
        if agg_name == "count" and not self._time_window:
            self.min_periods = 0
        index = cudf.MultiIndex.from_frame(
            cudf.DataFrame(
                {
                    key: value
                    for key, value in itertools.chain(
                        self._group_keys._data.items(),
                        self.obj.index._data.items(),
                    )
                }
            )
        )

        result = super()._apply_agg(agg_name).set_index(index)
        return result
