#include <cuda_runtime.h>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>

#define CHECK(call) do {                                                   \
  cudaError_t e = (call);                                                  \
  if (e != cudaSuccess) {                                                  \
    std::fprintf(stderr, "%s:%d CUDA error: %s\n",                      \
                 __FILE__, __LINE__, cudaGetErrorString(e));               \
    std::exit(1);                                                          \
  }                                                                        \
} while (0)

__global__ void add_one(float* x, int n) {
  int i = blockIdx.x * blockDim.x + threadIdx.x;
  if (i < n) x[i] += 1.0f;
}

int main(int argc, char** argv) {
  const int n = argc > 1 ? std::atoi(argv[1]) : 4096;
  const int nodes = argc > 2 ? std::atoi(argv[2]) : 32;
  const int iterations = argc > 3 ? std::atoi(argv[3]) : 1000;
  if (n <= 0 || nodes <= 0 || iterations <= 0) return 2;

  int device = 0;
  cudaDeviceProp prop{};
  CHECK(cudaGetDeviceProperties(&prop, device));
  std::printf("gpu=%s capability=%d.%d\n", prop.name, prop.major, prop.minor);

  float* x = nullptr;
  CHECK(cudaMalloc(&x, n * sizeof(float)));
  cudaStream_t stream;
  CHECK(cudaStreamCreateWithFlags(&stream, cudaStreamNonBlocking));
  const int block = 256;
  const int grid = (n + block - 1) / block;

  for (int i = 0; i < 10; ++i)
    add_one<<<grid, block, 0, stream>>>(x, n);
  CHECK(cudaStreamSynchronize(stream));

  cudaGraph_t graph;
  cudaGraphExec_t graph_exec;
  CHECK(cudaStreamBeginCapture(stream, cudaStreamCaptureModeGlobal));
  for (int j = 0; j < nodes; ++j)
    add_one<<<grid, block, 0, stream>>>(x, n);
  CHECK(cudaStreamEndCapture(stream, &graph));
  CHECK(cudaGraphInstantiate(&graph_exec, graph, nullptr, nullptr, 0));

  cudaEvent_t start, end;
  CHECK(cudaEventCreate(&start));
  CHECK(cudaEventCreate(&end));

  CHECK(cudaMemsetAsync(x, 0, n * sizeof(float), stream));
  CHECK(cudaEventRecord(start, stream));
  auto eager_cpu_start = std::chrono::steady_clock::now();
  for (int i = 0; i < iterations; ++i)
    for (int j = 0; j < nodes; ++j)
      add_one<<<grid, block, 0, stream>>>(x, n);
  auto eager_cpu_end = std::chrono::steady_clock::now();
  CHECK(cudaEventRecord(end, stream));
  CHECK(cudaEventSynchronize(end));
  float eager_ms = 0.0f;
  CHECK(cudaEventElapsedTime(&eager_ms, start, end));

  CHECK(cudaMemsetAsync(x, 0, n * sizeof(float), stream));
  CHECK(cudaEventRecord(start, stream));
  auto graph_cpu_start = std::chrono::steady_clock::now();
  for (int i = 0; i < iterations; ++i)
    CHECK(cudaGraphLaunch(graph_exec, stream));
  auto graph_cpu_end = std::chrono::steady_clock::now();
  CHECK(cudaEventRecord(end, stream));
  CHECK(cudaEventSynchronize(end));
  float graph_ms = 0.0f;
  CHECK(cudaEventElapsedTime(&graph_ms, start, end));

  float first = 0.0f;
  CHECK(cudaMemcpy(&first, x, sizeof(float), cudaMemcpyDeviceToHost));
  const float expected = static_cast<float>(nodes * iterations);
  if (std::fabs(first - expected) > 0.5f) {
    std::fprintf(stderr, "validation failed: got=%f expected=%f\n", first, expected);
    return 3;
  }

  const double eager_submit_ms =
      std::chrono::duration<double, std::milli>(eager_cpu_end-eager_cpu_start).count();
  const double graph_submit_ms =
      std::chrono::duration<double, std::milli>(graph_cpu_end-graph_cpu_start).count();
  std::printf("nodes=%d iterations=%d n=%d\n", nodes, iterations, n);
  std::printf("eager_gpu_total_ms=%.3f graph_gpu_total_ms=%.3f speedup=%.3fx\n",
              eager_ms, graph_ms, eager_ms / graph_ms);
  std::printf("eager_cpu_submit_ms=%.3f graph_cpu_submit_ms=%.3f submit_speedup=%.3fx\n",
              eager_submit_ms, graph_submit_ms, eager_submit_ms / graph_submit_ms);
  std::printf("validation=PASS value=%.0f\n", first);

  CHECK(cudaEventDestroy(start));
  CHECK(cudaEventDestroy(end));
  CHECK(cudaGraphExecDestroy(graph_exec));
  CHECK(cudaGraphDestroy(graph));
  CHECK(cudaStreamDestroy(stream));
  CHECK(cudaFree(x));
  return 0;
}
