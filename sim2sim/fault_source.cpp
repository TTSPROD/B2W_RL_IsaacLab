// Real DDS LowState fault source and an independent LowCmd observer.
// Synthetic state is protocol evidence, not a locomotion or physics test.
#include "sdk2_io.hpp"
#include "unix_rpc.hpp"
#include <unitree/robot/channel/channel_publisher.hpp>
#include <unitree/robot/channel/channel_subscriber.hpp>
#include <yaml-cpp/yaml.h>
#include <poll.h>
#include <signal.h>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <mutex>
#include <iostream>
#include <limits>
#include <algorithm>
volatile sig_atomic_t running=1;
class Source {
  State state_{};uint32_t tick_=0,frozen_tick_=0;uint64_t loop_=0;
  std::string mode_="normal";int64_t mode_ns_=0;
  unitree::robot::ChannelPublisherPtr<State> publisher_;
  unitree::robot::ChannelSubscriberPtr<Cmd> subscriber_;
  std::mutex mutex_;std::ofstream commands_;
  uint64_t commands_count_=0;bool last_disabled_=true,crc_valid_=true;
  int64_t first_disabled_=0,last_command_ns_=0;
public:
  Source(const YAML::Node& plan,const std::string& directory) {
    state_.imu_state().quaternion()={1,0,0,0};
    for(int i=0;i<16;++i)state_.motor_state()[i].q()=plan["nominal_joint_pos"][i].as<float>();
    commands_.open(directory+"/observed_commands.csv");commands_<<"received_ns,disabled,crc_valid";
    for(int i=0;i<20;++i)for(const char* f:{"mode","q","dq","kp","kd","tau"})commands_<<",m"<<i<<"_"<<f;
    commands_<<"\n";
    unitree::robot::ChannelFactory::Instance()->Init(1,"lo");
    publisher_=std::make_shared<unitree::robot::ChannelPublisher<State>>("rt/lowstate");publisher_->InitChannel();
    subscriber_=std::make_shared<unitree::robot::ChannelSubscriber<Cmd>>("rt/lowcmd");
    subscriber_->InitChannel([this](const void* raw){
      auto& cmd=*static_cast<const Cmd*>(raw);std::lock_guard<std::mutex> lock(mutex_);
      int64_t now=monotonic_ns();bool disabled=is_disabled(cmd);
      if(disabled && !last_disabled_)first_disabled_=now;
      last_disabled_=disabled;crc_valid_=cmd.crc()==crc(cmd);last_command_ns_=now;++commands_count_;
      commands_<<std::setprecision(9)<<now<<","<<disabled<<","<<crc_valid_;
      for(const auto& m:cmd.motor_cmd())commands_<<","<<int(m.mode())<<","<<m.q()<<","<<m.dq()<<","<<m.kp()<<","<<m.kd()<<","<<m.tau();
      commands_<<"\n";if(commands_count_%250==0)commands_.flush();
    },1);
  }
  ~Source(){subscriber_->CloseChannel();publisher_->CloseChannel();}
  std::string request(const std::string& packet) {
    std::istringstream in(packet);std::string op,mode;uint64_t id=0;in>>op>>id;
    bool ok=bool(in);
    if(op=="MODE") {
      in>>mode;ok=bool(in) && (mode=="normal"||mode=="sparse"||mode=="pause"||mode=="duplicate"||mode=="reorder"||mode=="bad_crc"||mode=="nan"||mode=="inf"||mode=="bad_quat"||mode=="restart"
#ifdef B2W_PD_FAULT_SOURCE
        ||mode=="actual_position"||mode=="actual_velocity"||mode=="actual_tilt"||mode=="nan_torque"
#endif
      );
      if(ok) {
        mode_=mode;mode_ns_=monotonic_ns();frozen_tick_=tick_;
        if(mode=="restart"){tick_=0;mode_="normal";}
      }
    } else if(op!="STATE")ok=false;
    std::lock_guard<std::mutex> lock(mutex_);
    std::ostringstream s;s<<"{\"id\":"<<id<<",\"ok\":"<<(ok?"true":"false")<<",\"mode\":\""<<mode_<<"\",\"applied_ns\":"<<mode_ns_
      <<",\"command_count\":"<<commands_count_<<",\"last_disabled\":"<<(last_disabled_?"true":"false")<<",\"crc_valid\":"<<(crc_valid_?"true":"false")
      <<",\"first_disabled_ns\":"<<first_disabled_<<",\"last_command_ns\":"<<last_command_ns_<<"}";return s.str();
  }
  void publish() {
    tick_+=2;++loop_;if(mode_=="pause" || (mode_=="sparse" && loop_%4==0))return;
    State msg=state_;msg.tick()=mode_=="duplicate"?frozen_tick_:tick_;
    if(mode_=="reorder"){msg.tick()=tick_>20?tick_-20:0;mode_="normal";}
    if(mode_=="nan")msg.imu_state().gyroscope()[0]=std::numeric_limits<float>::quiet_NaN();
    if(mode_=="inf")msg.motor_state()[3].dq()=std::numeric_limits<float>::infinity();
    if(mode_=="bad_quat")msg.imu_state().quaternion()={0,0,0,0};
#ifdef B2W_PD_FAULT_SOURCE
    if(mode_=="actual_position")msg.motor_state()[5].q()=-.4f;
    if(mode_=="actual_velocity")msg.motor_state()[12].dq()=51.f;
    if(mode_=="actual_tilt")msg.imu_state().quaternion()={float(std::cos(.6)),float(std::sin(.6)),0,0};
    if(mode_=="nan_torque")msg.motor_state()[2].tau_est()=std::numeric_limits<float>::quiet_NaN();
#endif
    msg.crc()=crc(msg);if(mode_=="bad_crc")msg.crc()^=1;
    publisher_->Write(msg);
  }
};
int main(int argc,char** argv) {
  if(argc!=4)return 1;signal(SIGTERM,[](int){running=0;});signal(SIGINT,[](int){running=0;});
  try {
    auto plan=YAML::LoadFile(argv[2]);if(plan["hardware_enabled"].as<bool>() || plan["domain"].as<int>()!=1 || plan["interface"].as<std::string>()!="lo")return 3;
    Source source(plan,argv[3]);int fd=rpc_socket(argv[1]);int64_t deadline=monotonic_ns();
    while(running) {
      for(int n=0;n<32;++n) {
        char buffer[4096];sockaddr_un peer{};socklen_t length=sizeof(peer);
        ssize_t size=recvfrom(fd,buffer,sizeof(buffer),MSG_DONTWAIT,reinterpret_cast<sockaddr*>(&peer),&length);if(size<0)break;
        auto reply=source.request(std::string(buffer,size));sendto(fd,reply.data(),reply.size(),MSG_DONTWAIT,reinterpret_cast<sockaddr*>(&peer),length);
      }
      int64_t now=monotonic_ns();if(now>=deadline){source.publish();deadline+=2000000;if(now-deadline>2000000)deadline=now+2000000;}
      pollfd item{fd,POLLIN,0};poll(&item,1,std::max<int64_t>(0,(deadline-monotonic_ns()+999999)/1000000));
    }
    close(fd);
  }catch(const std::exception& error){std::cerr<<error.what()<<"\n";return 2;}
  return 0;
}
