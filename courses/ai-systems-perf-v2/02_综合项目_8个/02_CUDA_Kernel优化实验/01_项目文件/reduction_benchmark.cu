#include <cuda_runtime.h>

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    cudaError_t error__ = (call);                                            \
    if (error__ != cudaSuccess) {                                            \
      std::cerr << "CUDA error: " << cudaGetErrorString(error__)            \
                << " at " << __FILE__ << ":" << __LINE__ << std::endl;     \
      std::exit(EXIT_FAILURE);                                               \
    }                                                                        \
  } while (0)

__global__ void reduce_atomic_baseline(const float* x, float* output, int n) {
  int index = blockIdx.x * blockDim.x + threadIdx.x;
  int stride = blockDim.x * gridDim.x;
  for (int i = index; i < n; i += stride) {
    atomicAdd(output, x[i]);
  }
}

__global__ void reduce_shared_v1(const float* x, float* output, int n) {
  extern __shared__ float shared[];
  int tid = threadIdx.x;
  int index = blockIdx.x * blockDim.x + tid;
  int stride = blockDim.x * gridDim.x;

  float local = 0.0f;
  for (int i = index; i < n; i += stride) {
    local += x[i];
  }
  shared[tid] = local;
  __syncthreads();

  for (int offset = blockDim.x / 2; offset > 0; offset >>= 1) {
    if (tid < offset) {
      shared[tid] += shared[tid + offset];
    }
    __syncthreads();
  }

  if (tid == 0) {
    atomicAdd(output, shared[0]);
  }
}

__inline__ __device__ float warp_sum(float value) {
  for (int offset = 16; offset > 0; offset >>= 1) {
    value += __shfl_down_sync(0xffffffffu, value, offset);
  }
  return value;
}

__global__ void reduce_warp_v2(const float* x, float* output, int n) {
  __shared__ float warp_sums[32];
  int tid = threadIdx.x;
  int lane = tid & 31;
  int warp_id = tid >> 5;
  int warp_count = (blockDim.x + 31) / 32;
  int index = blockIdx.x * blockDim.x + tid;
  int stride = blockDim.x * gridDim.x;

  float local = 0.0f;
  for (int i = index; i < n; i += stride) {
    local += x[i];
  }
  local = warp_sum(local);

  if (lane == 0) {
    warp_sums[warp_id] = local;
  }
  __syncthreads();

  if (warp_id == 0) {
    float block_value = lane < warp_count ? warp_sums[lane] : 0.0f;
    block_value = warp_sum(block_value);
    if (lane == 0) {
      atomicAdd(output, block_value);
    }
  }
}

struct Stats {
  float p50_ms;
  float p95_ms;
  float min_ms;
  float max_ms;
  float result;
};

float percentile(std::vector<float> values, double q) {
  std::sort(values.begin(), values.end());
  double position = (values.size() - 1) * q;
  size_t lower = static_cast<size_t>(std::floor(position));
  size_t upper = static_cast<size_t>(std::ceil(position));
  if (lower == upper) return values[lower];
  double weight = position - lower;
  return static_cast<float>(values[lower] * (1.0 - weight) + values[upper] * weight);
}

template <typename Launcher>
Stats benchmark(Launcher launch, float* d_output, int warmup, int iterations) {
  for (int i = 0; i < warmup; ++i) {
    CUDA_CHECK(cudaMemset(d_output, 0, sizeof(float)));
    launch();
  }
  CUDA_CHECK(cudaGetLastError());
  CUDA_CHECK(cudaDeviceSynchronize());

  cudaEvent_t start, stop;
  CUDA_CHECK(cudaEventCreate(&start));
  CUDA_CHECK(cudaEventCreate(&stop));
  std::vector<float> samples;
  samples.reserve(iterations);

  for (int i = 0; i < iterations; ++i) {
    CUDA_CHECK(cudaMemset(d_output, 0, sizeof(float)));
    CUDA_CHECK(cudaEventRecord(start));
    launch();
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    CUDA_CHECK(cudaGetLastError());
    float elapsed = 0.0f;
    CUDA_CHECK(cudaEventElapsedTime(&elapsed, start, stop));
    samples.push_back(elapsed);
  }

  float result = 0.0f;
  CUDA_CHECK(cudaMemcpy(&result, d_output, sizeof(float), cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaEventDestroy(start));
  CUDA_CHECK(cudaEventDestroy(stop));

  std::vector<float> sorted = samples;
  std::sort(sorted.begin(), sorted.end());
  return {percentile(samples, 0.50), percentile(samples, 0.95),
          sorted.front(), sorted.back(), result};
}

void print_stats(const std::string& name, const Stats& stats, size_t elements,
                 float expected) {
  double effective_gbps = (elements * sizeof(float)) / (stats.p50_ms * 1e6);
  double relative_error = std::abs(stats.result - expected) / std::max(1.0f, expected);
  std::cout << std::left << std::setw(18) << name
            << " p50=" << std::setw(9) << stats.p50_ms
            << " p95=" << std::setw(9) << stats.p95_ms
            << " min=" << std::setw(9) << stats.min_ms
            << " max=" << std::setw(9) << stats.max_ms
            << " effective_GB/s=" << std::setw(9) << effective_gbps
            << " result=" << stats.result
            << " rel_error=" << relative_error << '\n';
  if (relative_error > 1e-4) {
    throw std::runtime_error(name + " correctness check failed");
  }
}

int main(int argc, char** argv) {
  size_t elements = 1u << 22;
  int block_size = 256;
  int blocks = 256;
  int warmup = 10;
  int iterations = 50;

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "--elements" && i + 1 < argc) elements = std::stoull(argv[++i]);
    else if (arg == "--block" && i + 1 < argc) block_size = std::stoi(argv[++i]);
    else if (arg == "--blocks" && i + 1 < argc) blocks = std::stoi(argv[++i]);
    else if (arg == "--warmup" && i + 1 < argc) warmup = std::stoi(argv[++i]);
    else if (arg == "--iters" && i + 1 < argc) iterations = std::stoi(argv[++i]);
    else {
      std::cerr << "Usage: " << argv[0]
                << " [--elements N] [--block N] [--blocks N]"
                << " [--warmup N] [--iters N]\n";
      return EXIT_FAILURE;
    }
  }

  if (elements == 0 || blocks <= 0 || warmup <= 0 || iterations <= 0 ||
      block_size < 32 || block_size > 1024 || block_size % 32 != 0 ||
      (block_size & (block_size - 1)) != 0) {
    std::cerr << "Invalid arguments: block must be a power of two, a multiple of 32, and <= 1024.\n";
    return EXIT_FAILURE;
  }

  int device = 0;
  cudaDeviceProp props{};
  CUDA_CHECK(cudaGetDevice(&device));
  CUDA_CHECK(cudaGetDeviceProperties(&props, device));
  std::cout << "GPU=" << props.name
            << " compute_capability=" << props.major << "." << props.minor
            << " global_memory_GiB=" << props.totalGlobalMem / double(1ull << 30)
            << " SMs=" << props.multiProcessorCount << '\n';
  std::cout << "elements=" << elements << " blocks=" << blocks
            << " block_size=" << block_size << " warmup=" << warmup
            << " iterations=" << iterations << '\n';

  if (elements > static_cast<size_t>(std::numeric_limits<int>::max())) {
    std::cerr << "This teaching implementation requires elements <= INT_MAX.\n";
    return EXIT_FAILURE;
  }

  std::vector<float> host(elements, 1.0f);
  float expected = static_cast<float>(elements);
  float* d_input = nullptr;
  float* d_output = nullptr;
  CUDA_CHECK(cudaMalloc(&d_input, elements * sizeof(float)));
  CUDA_CHECK(cudaMalloc(&d_output, sizeof(float)));
  CUDA_CHECK(cudaMemcpy(d_input, host.data(), elements * sizeof(float), cudaMemcpyHostToDevice));

  auto baseline = benchmark(
      [&] { reduce_atomic_baseline<<<blocks, block_size>>>(d_input, d_output, static_cast<int>(elements)); },
      d_output, warmup, iterations);
  auto shared = benchmark(
      [&] { reduce_shared_v1<<<blocks, block_size, block_size * sizeof(float)>>>(
                d_input, d_output, static_cast<int>(elements)); },
      d_output, warmup, iterations);
  auto warp = benchmark(
      [&] { reduce_warp_v2<<<blocks, block_size>>>(d_input, d_output, static_cast<int>(elements)); },
      d_output, warmup, iterations);

  print_stats("atomic_baseline", baseline, elements, expected);
  print_stats("shared_v1", shared, elements, expected);
  print_stats("warp_v2", warp, elements, expected);
  std::cout << "speedup_shared=" << baseline.p50_ms / shared.p50_ms
            << " speedup_warp=" << baseline.p50_ms / warp.p50_ms
            << " warp_vs_shared=" << shared.p50_ms / warp.p50_ms << '\n';

  CUDA_CHECK(cudaFree(d_input));
  CUDA_CHECK(cudaFree(d_output));
  return EXIT_SUCCESS;
}
