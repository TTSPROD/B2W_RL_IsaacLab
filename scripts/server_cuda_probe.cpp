// Bounded synthetic CUDA probe; this does not benchmark Isaac Lab or PPO.
#include <cuda_runtime.h>
#include <cublas_v2.h>
#include <cstdio>
#include <cstdlib>
#include <cmath>
#include <vector>

#define CUDA(x) do { cudaError_t e=(x); if(e!=cudaSuccess) { std::fprintf(stderr,"CUDA: %s\n",cudaGetErrorString(e)); return 2; } } while(0)
#define BLAS(x) do { cublasStatus_t e=(x); if(e!=CUBLAS_STATUS_SUCCESS) { std::fprintf(stderr,"cuBLAS: %d\n",int(e)); return 3; } } while(0)

int main(int argc, char** argv) {
    std::setvbuf(stdout,nullptr,_IONBF,0);
    std::fprintf(stderr,"stage: CUDA context\n");
    CUDA(cudaSetDevice(0));
    cudaDeviceProp p{}; CUDA(cudaGetDeviceProperties(&p,0));
    size_t free_bytes,total_bytes; CUDA(cudaMemGetInfo(&free_bytes,&total_bytes));
    if(free_bytes < (size_t(4)<<30)) return 4;
    int driver,runtime; CUDA(cudaDriverGetVersion(&driver)); CUDA(cudaRuntimeGetVersion(&runtime));
    std::printf("{\"device\":\"%s\",\"compute_capability\":\"%d.%d\",\"sm_count\":%d,\"driver_api\":%d,\"runtime_api\":%d,",p.name,p.major,p.minor,p.multiProcessorCount,driver,runtime);
    const size_t bytes=size_t(128)<<20;
    void *a,*b; CUDA(cudaMalloc(&a,bytes)); CUDA(cudaMalloc(&b,bytes));
    CUDA(cudaMemset(a,7,bytes)); CUDA(cudaMemset(b,0,bytes));
    cudaEvent_t start,end; CUDA(cudaEventCreate(&start)); CUDA(cudaEventCreate(&end));
    for(int i=0;i<10;i++) CUDA(cudaMemcpy(b,a,bytes,cudaMemcpyDeviceToDevice));
    std::printf("\"d2d_gb_s_read_plus_write\":[");
    for(int trial=0;trial<3;trial++) {
        CUDA(cudaEventRecord(start));
        for(int i=0;i<100;i++) CUDA(cudaMemcpyAsync(b,a,bytes,cudaMemcpyDeviceToDevice));
        CUDA(cudaEventRecord(end)); CUDA(cudaEventSynchronize(end));
        float ms; CUDA(cudaEventElapsedTime(&ms,start,end));
        std::printf("%s%.3f",trial?",":"",2.0*bytes*100/(ms*1e6));
    }
    unsigned char sample=0; CUDA(cudaMemcpy(&sample,b,1,cudaMemcpyDeviceToHost));
    if(sample!=7) return 5;
    CUDA(cudaFree(a)); CUDA(cudaFree(b));
    if(argc>1) {
        std::printf("],\"copy_correctness\":\"passed\",\"isaac_lab_benchmark\":false}\n");
        CUDA(cudaEventDestroy(start)); CUDA(cudaEventDestroy(end));
        return 0;
    }
    std::fprintf(stderr,"stage: matrix allocation\n");
    const int n=4096; const size_t matrix_bytes=size_t(n)*n*sizeof(float);
    float *A,*B,*C; CUDA(cudaMalloc(&A,matrix_bytes)); CUDA(cudaMalloc(&B,matrix_bytes)); CUDA(cudaMalloc(&C,matrix_bytes));
    std::vector<float> host(size_t(n)*n,1.0f);
    CUDA(cudaMemcpy(A,host.data(),matrix_bytes,cudaMemcpyHostToDevice)); CUDA(cudaMemcpy(B,host.data(),matrix_bytes,cudaMemcpyHostToDevice));
    std::fprintf(stderr,"stage: cuBLAS initialization\n");
    cublasHandle_t handle; BLAS(cublasCreate(&handle));
    BLAS(cublasSetMathMode(handle,CUBLAS_PEDANTIC_MATH));
    int blas_version; BLAS(cublasGetVersion(handle,&blas_version));
    float alpha=1,beta=0;
    std::fprintf(stderr,"stage: SGEMM\n");
    for(int i=0;i<10;i++) BLAS(cublasSgemm(handle,CUBLAS_OP_N,CUBLAS_OP_N,n,n,n,&alpha,A,n,B,n,&beta,C,n));
    std::printf("],\"cublas_version\":%d,\"fp32_sgemm_4096_tflops\":[",blas_version);
    for(int trial=0;trial<3;trial++) {
        CUDA(cudaEventRecord(start));
        for(int i=0;i<30;i++) BLAS(cublasSgemm(handle,CUBLAS_OP_N,CUBLAS_OP_N,n,n,n,&alpha,A,n,B,n,&beta,C,n));
        CUDA(cudaEventRecord(end)); CUDA(cudaEventSynchronize(end));
        float ms; CUDA(cudaEventElapsedTime(&ms,start,end));
        std::printf("%s%.3f",trial?",":"",2.0*n*n*n*30/(ms*1e9));
    }
    CUDA(cudaMemcpy(host.data(),C,matrix_bytes,cudaMemcpyDeviceToHost));
    for(float value:host) if(!std::isfinite(value)||std::fabs(value-n)>0.01) return 6;
    std::printf("],\"correctness\":\"passed\",\"tf32\":false,\"isaac_lab_benchmark\":false}\n");
    BLAS(cublasDestroy(handle)); CUDA(cudaFree(A)); CUDA(cudaFree(B)); CUDA(cudaFree(C));
    CUDA(cudaEventDestroy(start)); CUDA(cudaEventDestroy(end));
    return 0;
}
