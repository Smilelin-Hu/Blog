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
#include <vector>

#define CUDA_CHECK(call)                                                       \
    do {                                                                       \
        cudaError_t error__ = (call);                                          \
        if (error__ != cudaSuccess) {                                          \
            std::cerr << "CUDA error at " << __FILE__ << ":" << __LINE__      \
                      << " -> " << cudaGetErrorString(error__) << std::endl;   \
            std::exit(EXIT_FAILURE);                                           \
        }                                                                      \
    } while (0)

__global__ void vector_add_grid_stride(const float* x, const float* y,
                                       float* out, size_t n) {
    const size_t start = static_cast<size_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    const size_t stride = static_cast<size_t>(blockDim.x) * gridDim.x;
    for (size_t i = start; i < n; i += stride) {
        out[i] = x[i] + y[i];
    }
}

size_t ceil_div(size_t a, size_t b) {
    return (a + b - 1) / b;
}

void verify(const float* x, const float* y, const float* out, size_t n,
            const std::string& label) {
    double max_error = 0.0;
    size_t bad_index = n;
    for (size_t i = 0; i < n; ++i) {
        const double expected = static_cast<double>(x[i]) + y[i];
        if (!std::isfinite(out[i])) {
            max_error = std::numeric_limits<double>::infinity();
            bad_index = i;
            break;
        }
        const double error = std::abs(static_cast<double>(out[i]) - expected);
        if (error > max_error) {
            max_error = error;
            bad_index = i;
        }
    }
    if (max_error > 1e-6) {
        throw std::runtime_error(label + " verification failed at index " +
                                 std::to_string(bad_index));
    }
    std::cout << label << " verification: PASS, max_error=" << max_error << "\n";
}

float benchmark_kernel(const float* dx, const float* dy, float* dout,
                       size_t n, int block_size, int repeats,
                       int multiprocessors) {
    // Grid-stride Kernel：限制为 SM 数量的若干倍，避免超大 Grid 干扰教学比较。
    const size_t needed = ceil_div(n, static_cast<size_t>(block_size));
    const int grid_size = static_cast<int>(
        std::min<size_t>(needed, static_cast<size_t>(multiprocessors) * 32));

    vector_add_grid_stride<<<grid_size, block_size>>>(dx, dy, dout, n);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaDeviceSynchronize());

    cudaEvent_t start{}, stop{};
    CUDA_CHECK(cudaEventCreate(&start));
    CUDA_CHECK(cudaEventCreate(&stop));
    CUDA_CHECK(cudaEventRecord(start));
    for (int r = 0; r < repeats; ++r) {
        vector_add_grid_stride<<<grid_size, block_size>>>(dx, dy, dout, n);
    }
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    float total_ms = 0.0f;
    CUDA_CHECK(cudaEventElapsedTime(&total_ms, start, stop));
    CUDA_CHECK(cudaEventDestroy(start));
    CUDA_CHECK(cudaEventDestroy(stop));
    return total_ms / repeats;
}

double synchronous_pipeline(const float* hx, const float* hy, float* hout,
                            float* dx, float* dy, float* dout,
                            size_t n, int block, int grid) {
    const size_t bytes = n * sizeof(float);
    const auto begin = std::chrono::steady_clock::now();
    CUDA_CHECK(cudaMemcpy(dx, hx, bytes, cudaMemcpyHostToDevice));
    CUDA_CHECK(cudaMemcpy(dy, hy, bytes, cudaMemcpyHostToDevice));
    vector_add_grid_stride<<<grid, block>>>(dx, dy, dout, n);
    CUDA_CHECK(cudaGetLastError());
    CUDA_CHECK(cudaMemcpy(hout, dout, bytes, cudaMemcpyDeviceToHost));
    CUDA_CHECK(cudaDeviceSynchronize());
    const auto end = std::chrono::steady_clock::now();
    return std::chrono::duration<double, std::milli>(end - begin).count();
}

double asynchronous_pipeline(const float* hx, const float* hy, float* hout,
                             float* dx, float* dy, float* dout,
                             size_t n, int block, int multiprocessors,
                             int stream_count) {
    std::vector<cudaStream_t> streams(stream_count);
    for (auto& stream : streams) {
        CUDA_CHECK(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking));
    }

    const size_t chunk = ceil_div(n, static_cast<size_t>(stream_count));
    const auto begin = std::chrono::steady_clock::now();
    for (int s = 0; s < stream_count; ++s) {
        const size_t offset = static_cast<size_t>(s) * chunk;
        if (offset >= n) break;
        const size_t count = std::min(chunk, n - offset);
        const size_t bytes = count * sizeof(float);
        const int grid = static_cast<int>(std::min<size_t>(
            ceil_div(count, static_cast<size_t>(block)),
            static_cast<size_t>(multiprocessors) * 16));

        CUDA_CHECK(cudaMemcpyAsync(dx + offset, hx + offset, bytes,
                                   cudaMemcpyHostToDevice, streams[s]));
        CUDA_CHECK(cudaMemcpyAsync(dy + offset, hy + offset, bytes,
                                   cudaMemcpyHostToDevice, streams[s]));
        vector_add_grid_stride<<<grid, block, 0, streams[s]>>>(
            dx + offset, dy + offset, dout + offset, count);
        CUDA_CHECK(cudaGetLastError());
        CUDA_CHECK(cudaMemcpyAsync(hout + offset, dout + offset, bytes,
                                   cudaMemcpyDeviceToHost, streams[s]));
    }
    for (auto stream : streams) {
        CUDA_CHECK(cudaStreamSynchronize(stream));
    }
    const auto end = std::chrono::steady_clock::now();
    for (auto stream : streams) {
        CUDA_CHECK(cudaStreamDestroy(stream));
    }
    return std::chrono::duration<double, std::milli>(end - begin).count();
}

int main(int argc, char** argv) {
    try {
        const size_t n = argc > 1 ? std::stoull(argv[1]) : (1ULL << 24);
        const int repeats = argc > 2 ? std::stoi(argv[2]) : 100;
        if (n == 0 || repeats <= 0) {
            throw std::invalid_argument("n and repeats must be positive");
        }

        int device = 0;
        CUDA_CHECK(cudaSetDevice(device));
        cudaDeviceProp prop{};
        CUDA_CHECK(cudaGetDeviceProperties(&prop, device));
        std::cout << "device=" << prop.name
                  << " cc=" << prop.major << "." << prop.minor
                  << " SMs=" << prop.multiProcessorCount
                  << " warp=" << prop.warpSize
                  << " max_threads_per_block=" << prop.maxThreadsPerBlock
                  << " async_engines=" << prop.asyncEngineCount << "\n";

        const size_t bytes = n * sizeof(float);
        float *hx = nullptr, *hy = nullptr, *hout = nullptr;
        float *dx = nullptr, *dy = nullptr, *dout = nullptr;
        CUDA_CHECK(cudaMallocHost(&hx, bytes));
        CUDA_CHECK(cudaMallocHost(&hy, bytes));
        CUDA_CHECK(cudaMallocHost(&hout, bytes));
        CUDA_CHECK(cudaMalloc(&dx, bytes));
        CUDA_CHECK(cudaMalloc(&dy, bytes));
        CUDA_CHECK(cudaMalloc(&dout, bytes));

        for (size_t i = 0; i < n; ++i) {
            hx[i] = static_cast<float>(i % 1024) * 0.25f;
            hy[i] = static_cast<float>(i % 257) * -0.5f;
            hout[i] = std::numeric_limits<float>::quiet_NaN();
        }

        CUDA_CHECK(cudaMemcpy(dx, hx, bytes, cudaMemcpyHostToDevice));
        CUDA_CHECK(cudaMemcpy(dy, hy, bytes, cudaMemcpyHostToDevice));

        std::cout << std::fixed << std::setprecision(3);
        for (int block : {64, 128, 256, 512}) {
            if (block > prop.maxThreadsPerBlock) continue;
            const float ms = benchmark_kernel(dx, dy, dout, n, block, repeats,
                                              prop.multiProcessorCount);
            const double payload_gbs = (3.0 * bytes) / (ms / 1000.0) / 1e9;
            std::cout << "block=" << block << " kernel_ms=" << ms
                      << " payload_GBps=" << payload_gbs << "\n";
        }

        const int block = 256;
        const int grid = static_cast<int>(std::min<size_t>(
            ceil_div(n, static_cast<size_t>(block)),
            static_cast<size_t>(prop.multiProcessorCount) * 32));

        const double sync_ms = synchronous_pipeline(
            hx, hy, hout, dx, dy, dout, n, block, grid);
        verify(hx, hy, hout, n, "synchronous");

        std::fill(hout, hout + n, std::numeric_limits<float>::quiet_NaN());
        const double async_ms = asynchronous_pipeline(
            hx, hy, hout, dx, dy, dout, n, block,
            prop.multiProcessorCount, 4);
        verify(hx, hy, hout, n, "four-stream");

        const double pipeline_bytes = 3.0 * bytes;
        std::cout << "sync_end_to_end_ms=" << sync_ms
                  << " payload_GBps=" << pipeline_bytes / (sync_ms / 1000.0) / 1e9
                  << "\n";
        std::cout << "four_stream_end_to_end_ms=" << async_ms
                  << " payload_GBps=" << pipeline_bytes / (async_ms / 1000.0) / 1e9
                  << " speedup=" << sync_ms / async_ms << "\n";
        std::cout << "note=async overlap is hardware/workload dependent; speedup may be <= 1\n";

        CUDA_CHECK(cudaFree(dout));
        CUDA_CHECK(cudaFree(dy));
        CUDA_CHECK(cudaFree(dx));
        CUDA_CHECK(cudaFreeHost(hout));
        CUDA_CHECK(cudaFreeHost(hy));
        CUDA_CHECK(cudaFreeHost(hx));
        CUDA_CHECK(cudaDeviceReset());
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "fatal: " << e.what() << "\n";
        return 1;
    }
}
