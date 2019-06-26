/*
 * Copyright (c) 2019, NVIDIA CORPORATION.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <benchmark/benchmark.h>
#include <vector>
#include <cudf/cudf.h>
#include <utilities/error_utils.hpp>

#include "generate_input_tables.cuh"


template<typename key_type, typename payload_type>
static void join_benchmark(benchmark::State& state)
{
    const gdf_size_type build_table_size {(gdf_size_type) state.range(0)};
    const gdf_size_type probe_table_size {(gdf_size_type) state.range(1)};
    const gdf_size_type rand_max_val {build_table_size * 2};
    const double selectivity = 0.3;
    const bool is_build_table_key_unique = true;

    std::vector<gdf_column *> build_table;
    std::vector<gdf_column *> probe_table;
    std::vector<gdf_column *> join_result;

    generate_build_probe_tables<key_type, payload_type>(
        build_table, build_table_size, probe_table, probe_table_size,
        selectivity, rand_max_val, is_build_table_key_unique
    );

    gdf_context ctxt = {
        0,                     // input data is not sorted
        gdf_method::GDF_HASH   // hash based join
    };

    int columns_to_join[] = {0};

    join_result.resize(build_table.size() + probe_table.size() - 1, nullptr);

    for (auto & col_ptr : join_result) {
        col_ptr = new gdf_column;
    }

    CUDA_TRY(cudaDeviceSynchronize());

    for (auto _ : state) {
        CUDF_TRY(gdf_inner_join(
            probe_table.data(), probe_table.size(), columns_to_join,
            build_table.data(), build_table.size(), columns_to_join,
            1, build_table.size() + probe_table.size() - 1, join_result.data(),
            nullptr, nullptr, &ctxt)
        );

        CUDA_TRY(cudaDeviceSynchronize());
    }

    free_table(build_table);
    free_table(probe_table);
    free_table(join_result);

    CUDA_TRY(cudaDeviceReset());
}

BENCHMARK_TEMPLATE(join_benchmark, int32_t, int32_t)->Unit(benchmark::kMillisecond)
    ->Args({100'000, 100'000})
    ->Args({100'000, 400'000})
    ->Args({100'000, 1'000'000})
    ->Args({10'000'000, 10'000'000})
    ->Args({10'000'000, 40'000'000})
    ->Args({10'000'000, 100'000'000})
    ->Args({100'000'000, 100'000'000})
    ->Args({80'000'000, 240'000'000});

BENCHMARK_TEMPLATE(join_benchmark, int64_t, int64_t)->Unit(benchmark::kMillisecond)
    ->Args({50'000'000, 50'000'000})
    ->Args({40'000'000, 120'000'000});
