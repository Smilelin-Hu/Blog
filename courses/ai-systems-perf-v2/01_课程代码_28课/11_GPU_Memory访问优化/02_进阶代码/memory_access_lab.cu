#include <cuda_runtime.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

#define CUDA_CHECK(call)                                                       \
    do {                                                                       \
        cudaError_t error__ = (call);                                          \
        if (error__ != cudaSuccess) {                                          \
            std::cerr << "CUDA error " << __FILE__ << ":" << __LINE__          \
                      << " -> " << cudaGetErrorString(error__) << "\n";       \
            std::exit(EXIT_FAILURE);                                           \
        }                                                                      \
    } while (0)

constexpr int TILE_DIM = 32;
constexpr int BLOCK_ROWS = 8;

__global__ void init_data(float* data, size_t n) {
    const size_t stride = static_cast<size_t>(blockDim.x) * gridDim.x;
    for (size_t i = static_cast<size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
         i < n; i += stride) {
        data[i] = static_cast<float>(i % 1024) * 0.25f;
    }
}

__global__ void read_with_stride(const float* input, float* output,
                                 size_t logical_n, int stride_words,
                                 int offset_words) {
    const size_t grid_stride = static_cast<size_t>(blockDim.x) * gridDim.x;
    for (size_t i = static_cast<size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
         i < logical_n; i += grid_stride) {
        output[i] = input[i * static_cast<size_t>(stride_words) + offset_words];
    }
}

__global__ void transpose_naive(const float* input, float* output,
                                int width, int height) {
    int x = blockIdx.x * TILE_DIM + threadIdx.x;
    int y = blockIdx.y * TILE_DIM + threadIdx.y;
    for (int j = 0; j < TILE_DIM; j += BLOCK_ROWS) {
        if (x < width && y + j < height) {
            output[x * height + (y + j)] = input[(y + j) * width + x];
        }
    }
}

template <int PAD>
__global__ void transpose_tiled(const float* input, float* output,
                               int width, int height) {
    __shared__ float tile[TILE_DIM][TILE_DIM + PAD];

    int x = blockIdx.x * TILE_DIM + threadIdx.x;
    int y = blockIdx.y * TILE_DIM + threadIdx.y;
    for (int j = 0; j < TILE_DIM; j += BLOCK_ROWS) {
        if (x < width && y + j < height) {
            tile[threadIdx.y + j][threadIdx.x] = input[(y + j) * width + x];
        }
    }
    __syncthreads();

    x = blockIdx.y * TILE_DIM + threadIdx.x;
    y = blockIdx.x * TILE_DIM + threadIdx.y;
    for (int j = 0; j < TILE_DIM; j += BLOCK_ROWS) {
        if (x < height && y + j < width) {
            output[(y + j) * height + x] = tile[threadIdx.x][threadIdx.y + j];
        }
    }
}

template <typename Launch>
float time_kernel(Launch launch, int warmup, int repeats) {
    for (int i = 0; i < warmup; ++i) launch();
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());

    cudaEvent_t start{}, stop{};
    CUDA_CHECK(cudaEventCreate(&start));
    CUDA_CHECK(cudaEventCreate(&stop));
    CUDA_CHECK(cudaEventRecord(start));
    for (int i = 0; i < repeats; ++i) launch();
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    float total_ms = 0.0f;
    CUDA_CHECK(cudaEventElapsedTime(&total_ms, start, stop));
    CUDA_CHECK(cudaEventDestroy(start));
    CUDA_CHECK(cudaEventDestroy(stop));
    return total_ms / repeats;
}

void verify_stride(const float* d_output, size_t n, int stride, int offset) {
    std::vector<float> host(n);
    CUDA_CHECK(cudaMemcpy(host.data(), d_output, n * sizeof(float),
                          cudaMemcpyDeviceToHost));
    double max_error = 0.0;
    for (size_t i = 0; i < n; ++i) {
        const size_t source_index = i * static_cast<size_t>(stride) + offset;
        const float expected = static_cast<float>(source_index % 1024) * 0.25f;
        if (!std::isfinite(host[i])) {
            throw std::runtime_error("stride output contains non-finite value");
        }
        max_error = std::max(max_error,
                             std::abs(static_cast<double>(host[i] - expected)));
    }
    if (max_error > 1e-6) throw std::runtime_error("stride verification failed");
}

void verify_transpose(const float* d_output, int width, int height) {
    const size_t n = static_cast<size_t>(width) * height;
    std::vector<float> host(n);
    CUDA_CHECK(cudaMemcpy(host.data(), d_output, n * sizeof(float),
                          cudaMemcpyDeviceToHost));
    for (int out_row = 0; out_row < width; ++out_row) {
        for (int out_col = 0; out_col < height; ++out_col) {
            const size_t input_index = static_cast<size_t>(out_col) * width + out_row;
            const float expected = static_cast<float>(input_index % 1024) * 0.25f;
            const float got = host[static_cast<size_t>(out_row) * height + out_col];
            if (!std::isfinite(got) || std::abs(got - expected) > 1e-6f) {
                throw std::runtime_error("transpose verification failed");
            }
        }
    }
}

int main(int argc, char** argv) {
    try {
        const size_t logical_n = argc > 1 ? std::stoull(argv[1]) : (1ULL << 22);
        const int matrix_size = argc > 2 ? std::stoi(argv[2]) : 4096;
        const int repeats = argc > 3 ? std::stoi(argv[3]) : 50;
        if (logical_n == 0 || matrix_size <= 0 || repeats <= 0) {
            throw std::invalid_argument("arguments must be positive");
        }

        cudaDeviceProp prop{};
        CUDA_CHECK(cudaGetDeviceProperties(&prop, 0));
        CUDA_CHECK(cudaSetDevice(0));
        std::cout << "device=" << prop.name
                  << " cc=" << prop.major << "." << prop.minor
                  << " SMs=" << prop.multiProcessorCount
                  << " memory_GiB=" << prop.totalGlobalMem / 1024.0 / 1024.0 / 1024.0
                  << "\n";

        constexpr int max_stride = 32;
        constexpr int max_offset = 1;
        const size_t input_n = logical_n * max_stride + max_offset;
        float *d_input = nullptr, *d_output = nullptr;
        CUDA_CHECK(cudaMalloc(&d_input, input_n * sizeof(float)));
        CUDA_CHECK(cudaMalloc(&d_output, logical_n * sizeof(float)));

        const int block = 256;
        const int init_grid = std::min<int>(
            static_cast<int>((input_n + block - 1) / block),
            prop.multiProcessorCount * 32);
        init_data<<<init_grid, block>>>(d_input, input_n);
        CUDA_CHECK(cudaGetLastError());
        CUDA_CHECK(cudaDeviceSynchronize());

        std::cout << std::fixed << std::setprecision(3);
        const int access_grid = std::min<int>(
            static_cast<int>((logical_n + block - 1) / block),
            prop.multiProcessorCount * 32);
        for (auto [stride, offset] : std::vector<std::pair<int, int>>{
                 {1, 0}, {1, 1}, {2, 0}, {8, 0}, {32, 0}}) {
            auto launch = [&] {
                read_with_stride<<<access_grid, block>>>(
                    d_input, d_output, logical_n, stride, offset);
            };
            const float ms = time_kernel(launch, 5, repeats);
            verify_stride(d_output, logical_n, stride, offset);
            const double requested_bytes = 2.0 * logical_n * sizeof(float);
            const double requested_gbs = requested_bytes / (ms / 1000.0) / 1e9;
            std::cout << "access stride=" << stride << " offset=" << offset
                      << " ms=" << ms
                      << " requested_GBps=" << requested_gbs << " PASS\n";
        }

        CUDA_CHECK(cudaFree(d_output));
        CUDA_CHECK(cudaFree(d_input));

        const int width = matrix_size;
        const int height = matrix_size;
        const size_t matrix_n = static_cast<size_t>(width) * height;
        const size_t matrix_bytes = matrix_n * sizeof(float);
        float *d_matrix_in = nullptr, *d_matrix_out = nullptr;
        CUDA_CHECK(cudaMalloc(&d_matrix_in, matrix_bytes));
        CUDA_CHECK(cudaMalloc(&d_matrix_out, matrix_bytes));
        const int matrix_init_grid = std::min<int>(
            static_cast<int>((matrix_n + block - 1) / block),
            prop.multiProcessorCount * 32);
        init_data<<<matrix_init_grid, block>>>(d_matrix_in, matrix_n);
        CUDA_CHECK(cudaGetLastError());
        CUDA_CHECK(cudaDeviceSynchronize());

        dim3 threads(TILE_DIM, BLOCK_ROWS);
        dim3 grid((width + TILE_DIM - 1) / TILE_DIM,
                  (height + TILE_DIM - 1) / TILE_DIM);

        auto naive = [&] {
            transpose_naive<<<grid, threads>>>(d_matrix_in, d_matrix_out,
                                               width, height);
        };
        const float naive_ms = time_kernel(naive, 5, repeats);
        verify_transpose(d_matrix_out, width, height);

        auto tiled_no_pad = [&] {
            transpose_tiled<0><<<grid, threads>>>(d_matrix_in, d_matrix_out,
                                                  width, height);
        };
        const float no_pad_ms = time_kernel(tiled_no_pad, 5, repeats);
        verify_transpose(d_matrix_out, width, height);

        auto tiled_pad = [&] {
            transpose_tiled<1><<<grid, threads>>>(d_matrix_in, d_matrix_out,
                                                  width, height);
        };
        const float pad_ms = time_kernel(tiled_pad, 5, repeats);
        verify_transpose(d_matrix_out, width, height);

        const double transpose_payload = 2.0 * matrix_bytes;
        auto print_transpose = [&](const std::string& name, float ms) {
            std::cout << "transpose " << name << " ms=" << ms
                      << " requested_GBps="
                      << transpose_payload / (ms / 1000.0) / 1e9
                      << " PASS\n";
        };
        print_transpose("naive", naive_ms);
        print_transpose("tiled_no_pad", no_pad_ms);
        print_transpose("tiled_pad_33", pad_ms);
        std::cout << "speedup padded_vs_naive=" << naive_ms / pad_ms
                  << " padded_vs_no_pad=" << no_pad_ms / pad_ms << "\n";

        CUDA_CHECK(cudaFree(d_matrix_out));
        CUDA_CHECK(cudaFree(d_matrix_in));
        CUDA_CHECK(cudaDeviceReset());
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "fatal: " << e.what() << "\n";
        return 1;
    }
}
