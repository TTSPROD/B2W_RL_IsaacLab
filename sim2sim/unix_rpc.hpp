#pragma once
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <chrono>
#include <string>
#include <stdexcept>
inline int64_t monotonic_ns() {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count();
}
inline int rpc_socket(const std::string& name) {
  if(name.empty() || name.size()>100) throw std::invalid_argument("Invalid abstract socket name");
  int fd=socket(AF_UNIX,SOCK_DGRAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);
  if(fd<0) throw std::runtime_error("socket failed");
  sockaddr_un address{}; address.sun_family=AF_UNIX;
  std::memcpy(address.sun_path+1,name.data(),name.size());
  if(bind(fd,reinterpret_cast<sockaddr*>(&address),offsetof(sockaddr_un,sun_path)+1+name.size())<0) {
    close(fd);throw std::runtime_error("abstract socket bind failed");
  }
  return fd;
}
