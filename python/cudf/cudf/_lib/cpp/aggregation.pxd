# Copyright (c) 2020-2021, NVIDIA CORPORATION.
from libc.stdint cimport int32_t
from libcpp.memory cimport unique_ptr
from libcpp.string cimport string
from libcpp.vector cimport vector

from cudf._lib.cpp.types cimport (
    data_type,
    interpolation,
    null_policy,
    size_type,
)

ctypedef int32_t underlying_type_t_correlation_type

cdef extern from "cudf/aggregation.hpp" namespace "cudf" nogil:

    cdef cppclass aggregation:
        ctypedef enum Kind:
            SUM 'cudf::aggregation::SUM'
            PRODUCT 'cudf::aggregation::PRODUCT'
            MIN 'cudf::aggregation::MIN'
            MAX 'cudf::aggregation::MAX'
            COUNT_VALID 'cudf::aggregation::COUNT_VALID'
            COUNT_ALL 'cudf::aggregation::COUNT_ALL'
            ANY 'cudf::aggregation::ANY'
            ALL 'cudf::aggregation::ALL'
            SUM_OF_SQUARES 'cudf::aggregation::SUM_OF_SQUARES'
            MEAN 'cudf::aggregation::MEAN'
            VARIANCE 'cudf::aggregation::VARIANCE'
            STD 'cudf::aggregation::STD'
            MEDIAN 'cudf::aggregation::MEDIAN'
            QUANTILE 'cudf::aggregation::QUANTILE'
            ARGMAX 'cudf::aggregation::ARGMAX'
            ARGMIN 'cudf::aggregation::ARGMIN'
            NUNIQUE 'cudf::aggregation::NUNIQUE'
            NTH_ELEMENT 'cudf::aggregation::NTH_ELEMENT'
            COLLECT 'cudf::aggregation::COLLECT_LIST'
            COLLECT_SET 'cudf::aggregation::COLLECT_SET'
            PTX 'cudf::aggregation::PTX'
            CUDA 'cudf::aggregation::CUDA'
            CORRELATION 'cudf::aggregation::CORRELATION'

        Kind kind

    cdef cppclass rolling_aggregation:
        aggregation.Kind kind

    cdef cppclass groupby_aggregation:
        aggregation.Kind kind

    cdef cppclass groupby_scan_aggregation:
        aggregation.Kind kind

    ctypedef enum udf_type:
        CUDA 'cudf::udf_type::CUDA'
        PTX 'cudf::udf_type::PTX'

    ctypedef enum correlation_type:
        PEARSON 'cudf::correlation_type::PEARSON'
        KENDALL 'cudf::correlation_type::KENDALL'
        SPEARMAN 'cudf::correlation_type::SPEARMAN'

    cdef unique_ptr[T] make_sum_aggregation[T]() except +

    cdef unique_ptr[T] make_product_aggregation[T]() except +

    cdef unique_ptr[T] make_min_aggregation[T]() except +

    cdef unique_ptr[T] make_max_aggregation[T]() except +

    cdef unique_ptr[T] make_count_aggregation[T]() except +

    cdef unique_ptr[T] make_count_aggregation[T](null_policy) except +

    cdef unique_ptr[T] make_any_aggregation[T]() except +

    cdef unique_ptr[T] make_all_aggregation[T]() except +

    cdef unique_ptr[T] make_sum_of_squares_aggregation[T]() except +

    cdef unique_ptr[T] make_mean_aggregation[T]() except +

    cdef unique_ptr[T] make_variance_aggregation[T](
        size_type ddof) except +

    cdef unique_ptr[T] make_std_aggregation[T](size_type ddof) except +

    cdef unique_ptr[T] make_median_aggregation[T]() except +

    cdef unique_ptr[T] make_quantile_aggregation[T](
        vector[double] q, interpolation i) except +

    cdef unique_ptr[T] make_argmax_aggregation[T]() except +

    cdef unique_ptr[T] make_argmin_aggregation[T]() except +

    cdef unique_ptr[T] make_nunique_aggregation[T]() except +

    cdef unique_ptr[T] make_nth_element_aggregation[T](
        size_type n
    ) except +

    cdef unique_ptr[T] make_nth_element_aggregation[T](
        size_type n,
        null_policy null_handling
    ) except +

    cdef unique_ptr[T] make_collect_list_aggregation[T]() except +

    cdef unique_ptr[T] make_collect_set_aggregation[T]() except +

    cdef unique_ptr[T] make_udf_aggregation[T](
        udf_type type,
        string user_defined_aggregator,
        data_type output_type) except +

    cdef unique_ptr[T] make_correlation_aggregation[T](
        correlation_type type, size_type min_periods) except +
