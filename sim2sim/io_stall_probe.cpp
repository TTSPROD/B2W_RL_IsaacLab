// Test-only per-child fault injector. Stall once on a physics CSV write;
// mark real wall timestamps via syscall, without wrapping its own marker IO.
#include <unistd.h>
#include <sys/uio.h>
#include <sys/syscall.h>
#include <fcntl.h>
#include <dlfcn.h>
#include <atomic>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <time.h>
static std::atomic<bool> injected{false};
static long long now() {timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return 1000000000LL*t.tv_sec+t.tv_nsec;}
static void stall(int fd,size_t bytes) {
  if(bytes<4096 || !std::getenv("B2W_IO_STALL_MARKER"))return;
  char link[64],path[4096];std::snprintf(link,sizeof(link),"/proc/self/fd/%d",fd);
  ssize_t n=readlink(link,path,sizeof(path)-1);if(n<0)return;path[n]=0;
  if(!std::strstr(path,"/physics.csv") || injected.exchange(true))return;
  auto begin=now();timespec delay{0,25000000};nanosleep(&delay,nullptr);auto end=now();
  int marker=open(std::getenv("B2W_IO_STALL_MARKER"),O_WRONLY|O_CREAT|O_TRUNC,0600);
  char text[128];int size=std::snprintf(text,sizeof(text),"{\"start_ns\":%lld,\"end_ns\":%lld}\n",begin,end);
  if(marker>=0){syscall(SYS_write,marker,text,size);close(marker);}
}
extern "C" ssize_t write(int fd,const void* data,size_t bytes) {
  static auto next=reinterpret_cast<ssize_t(*)(int,const void*,size_t)>(dlsym(RTLD_NEXT,"write"));
  stall(fd,bytes);return next(fd,data,bytes);
}
extern "C" ssize_t writev(int fd,const iovec* data,int count) {
  static auto next=reinterpret_cast<ssize_t(*)(int,const iovec*,int)>(dlsym(RTLD_NEXT,"writev"));
  size_t bytes=0;for(int i=0;i<count;++i)bytes+=data[i].iov_len;stall(fd,bytes);return next(fd,data,count);
}
