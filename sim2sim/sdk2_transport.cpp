// Native SDK2 IO shared by offline field checks and the Python policy runtime.
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <unitree/robot/channel/channel_publisher.hpp>
#include <unitree/robot/channel/channel_subscriber.hpp>
#include <unitree/idl/go2/LowCmd_.hpp>
#include <unitree/idl/go2/LowState_.hpp>
#include <chrono>
#include <mutex>
#include <cstring>
#include <cmath>
namespace py = pybind11;
#include "sdk2_io.hpp"
using Clock = std::chrono::steady_clock;
py::dict echo(const std::vector<std::vector<float>>& motors) {
  auto msg=encode(motors); py::dict out;
  std::vector<std::vector<float>> fields;
  for (auto& m:msg.motor_cmd()) fields.push_back({float(m.mode()),m.q(),m.dq(),m.kp(),m.kd(),m.tau()});
  out["motors"]=fields; out["head"]=msg.head(); out["level_flag"]=msg.level_flag();
  out["gpio"]=msg.gpio(); out["crc"]=msg.crc(); out["crc_valid"]=msg.crc()==crc(msg);
  std::vector<uint32_t> words(sizeof(Cmd)/4-1);
  std::memcpy(words.data(),&msg,words.size()*4); out["crc_words"]=words;
  return out;
}
class Transport {
  std::mutex mutex_; State state_{}; Clock::time_point received_{}; uint64_t count_=0;
  unitree::robot::ChannelSubscriberPtr<State> subscriber_;
  unitree::robot::ChannelPublisherPtr<Cmd> publisher_;
public:
  Transport(int domain, const std::string& interface) {
    if (domain!=1 || interface!="lo") throw std::invalid_argument("Simulator only: domain 1 / lo required");
    unitree::robot::ChannelFactory::Instance()->Init(domain,interface);
    publisher_=std::make_shared<unitree::robot::ChannelPublisher<Cmd>>("rt/lowcmd"); publisher_->InitChannel();
    subscriber_=std::make_shared<unitree::robot::ChannelSubscriber<State>>("rt/lowstate");
    subscriber_->InitChannel([this](const void* raw) {
      std::lock_guard<std::mutex> lock(mutex_); state_=*static_cast<const State*>(raw);
      received_=Clock::now(); ++count_;
    }, 1);
  }
  ~Transport() { subscriber_->CloseChannel(); publisher_->CloseChannel(); }
  py::dict state() {
    std::lock_guard<std::mutex> lock(mutex_); py::dict out;
    out["count"]=count_; if (!count_) return out;
    out["age_s"]=std::chrono::duration<double>(Clock::now()-received_).count();
    out["tick"]=state_.tick(); out["quat_wxyz"]=state_.imu_state().quaternion();
    out["crc_valid"]=state_.crc()==crc(state_);
    out["omega_body"]=state_.imu_state().gyroscope();
    std::vector<float> q,dq;
    for (size_t i=0; i<16; ++i) {q.push_back(state_.motor_state()[i].q());dq.push_back(state_.motor_state()[i].dq());}
    out["joint_pos"]=q; out["joint_vel"]=dq; return out;
  }
  bool publish(const std::vector<std::vector<float>>& motors) { return publisher_->Write(encode(motors)); }
};
PYBIND11_MODULE(b2w_sdk2_native,m) {
  m.def("echo",&echo);
  py::class_<Transport>(m,"Transport").def(py::init<int,const std::string&>())
    .def("state",&Transport::state).def("publish",&Transport::publish);
}
