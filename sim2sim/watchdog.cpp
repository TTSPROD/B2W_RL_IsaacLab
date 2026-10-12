#include "sdk2_io.hpp"
#include "unix_rpc.hpp"
#include <unitree/robot/channel/channel_publisher.hpp>
#include <unitree/robot/channel/channel_subscriber.hpp>
#include <yaml-cpp/yaml.h>
#include <poll.h>
#include <signal.h>
#include <deque>
#include <mutex>
#include <sstream>
#include <fstream>
#include <iomanip>
#include <algorithm>
#include <iostream>
#ifdef B2W_PD_TARGET_GUARD
#include "pd_guard.hpp"
#endif

volatile sig_atomic_t running=1;
struct Snapshot { State msg; uint64_t generation; int64_t received; };
class Watchdog {
  YAML::Node plan_;
#ifdef B2W_PD_TARGET_GUARD
  Sim2simPDGuard pd_guard_;
  std::ofstream state_limits_;
#endif
  std::mutex mutex_;
  std::deque<Snapshot> history_;
  uint64_t receipts_=0, generation_=0, epoch_=0, command_seq_=0, inference_seq_=0, target_generation_=0;
  uint32_t last_tick_=0;
  int advancing_=0;
  int64_t last_advance_=0, command_ns_=0, target_ns_=0, inference_ns_=0, fault_ns_=0;
  bool armed_=false, pending_=false;
  std::string fault_;
  Cmd target_=disabled_cmd();
  uint64_t inference_state_=0, inference_command_=0;
  unitree::robot::ChannelSubscriberPtr<State> subscriber_;
  unitree::robot::ChannelPublisherPtr<Cmd> publisher_;
  std::ofstream publishes_, events_, targets_;
  uint64_t publish_count_=0;
  int64_t last_publish_=0, max_interval_=0, first_disabled_=0;
  bool last_disabled_=true;

  int64_t budget(const char* key) const { return plan_["deadlines_ns"][key].as<int64_t>(); }
  void latch(const std::string& reason,int64_t now) {
    if(!fault_.empty()) return;
    fault_=reason;fault_ns_=now;
    events_<<now<<","<<epoch_<<",fault,"<<reason<<"\n";events_.flush();
  }
  void check(int64_t now) {
    if(!armed_ || !fault_.empty()) return;
    if(pending_ && now-inference_ns_>budget("inference")) latch("inference_timeout",now);
    if(now-last_advance_>budget("state")) latch("stale_state",now);
    if(now-command_ns_>budget("command")) latch("stale_command",now);
    if(now-target_ns_>budget("target")) latch("expired_target",now);
  }
  void receive(const State& state) {
    std::lock_guard<std::mutex> lock(mutex_);int64_t now=monotonic_ns();++receipts_;
    if(state.crc()!=crc(state)) {latch("invalid_state_crc",now);advancing_=0;return;}
    double norm=0;
    for(float x:state.imu_state().quaternion()) {if(!std::isfinite(x)){latch("nonfinite_state",now);advancing_=0;return;}norm+=x*x;}
    for(float x:state.imu_state().gyroscope()) if(!std::isfinite(x)){latch("nonfinite_state",now);advancing_=0;return;}
    for(int i=0;i<16;++i) if(!std::isfinite(state.motor_state()[i].q()) || !std::isfinite(state.motor_state()[i].dq())) {
      latch("nonfinite_state",now);advancing_=0;return;
    }
    if(std::abs(std::sqrt(norm)-1)>1e-5){latch("invalid_quaternion",now);advancing_=0;return;}
#ifdef B2W_PD_TARGET_GUARD
    for(int i=0;i<16;++i)if(!std::isfinite(state.motor_state()[i].tau_est())) {
      latch("nonfinite_state",now);advancing_=0;return;
    }
    if(auto violation=pd_guard_.state(state)) {
      if(fault_.empty()) {
        const auto& v=*violation;
        state_limits_<<std::setprecision(17)<<now<<","<<epoch_<<","<<state.tick()<<","<<v.reason<<","<<v.slot
          <<","<<v.quantity<<","<<v.value<<","<<v.lower<<","<<v.upper<<"\n";state_limits_.flush();
      }
      latch(violation->reason,now);advancing_=0;return;
    }
#endif
    if(generation_ && state.tick()<last_tick_) {latch("state_reordered",now);advancing_=0;}
    if(generation_ && state.tick()==last_tick_) return; // duplicated packets cannot renew freshness
    last_tick_=state.tick();last_advance_=now;++advancing_;
    history_.push_back({state,++generation_,now});if(history_.size()>64)history_.pop_front();
  }
  std::string response(uint64_t id,bool ok,const std::string& error="") {
    std::ostringstream s;s<<std::setprecision(17);
    s<<"{\"id\":"<<id<<",\"ok\":"<<(ok?"true":"false")<<",\"error\":\""<<error
      <<"\",\"fault\":\""<<fault_<<"\",\"epoch\":"<<epoch_<<",\"armed\":"<<(armed_?"true":"false")
      <<",\"count\":"<<generation_<<",\"receipts\":"<<receipts_<<",\"command_seq\":"<<command_seq_
      <<",\"inference_seq\":"<<inference_seq_<<",\"target_generation\":"<<target_generation_
      <<",\"pending\":"<<(pending_?"true":"false")<<",\"fault_ns\":"<<fault_ns_
      <<",\"inference_ns\":"<<inference_ns_<<",\"target_ns\":"<<target_ns_<<",\"command_ns\":"<<command_ns_
      <<",\"publish_count\":"<<publish_count_<<",\"max_publish_interval_ns\":"<<max_interval_
      <<",\"first_disabled_ns\":"<<first_disabled_<<",\"last_disabled\":"<<(last_disabled_?"true":"false");
    if(!history_.empty()) {
      const auto& snap=history_.back();const auto& m=snap.msg;
      s<<",\"tick\":"<<m.tick()<<",\"age_s\":"<<double(monotonic_ns()-snap.received)/1e9<<",\"crc_valid\":true";
      auto vector=[&](const char* name,const auto& values) {s<<",\""<<name<<"\":[";bool first=true;for(auto x:values){if(!first)s<<",";s<<x;first=false;}s<<"]";};
      vector("quat_wxyz",m.imu_state().quaternion());vector("omega_body",m.imu_state().gyroscope());
      std::vector<float> q,dq;for(int i=0;i<16;++i){q.push_back(m.motor_state()[i].q());dq.push_back(m.motor_state()[i].dq());}
      vector("joint_pos",q);vector("joint_vel",dq);
    }
    s<<"}";return s.str();
  }
public:
  Watchdog(const YAML::Node& plan,const std::string& directory):plan_(plan)
#ifdef B2W_PD_TARGET_GUARD
    ,pd_guard_(plan)
#endif
  {
    if(plan_["hardware_enabled"].as<bool>() || plan_["domain"].as<int>()!=1 || plan_["interface"].as<std::string>()!="lo")
      throw std::invalid_argument("Simulator only: domain 1 / lo");
    publishes_.open(directory+"/publish.csv");events_.open(directory+"/events.csv");targets_.open(directory+"/targets.csv");
#ifdef B2W_PD_TARGET_GUARD
    state_limits_.open(directory+"/state_limits.csv");
    state_limits_<<"time_ns,epoch,tick,reason,slot,quantity,value,lower,upper\n";
#endif
    publishes_<<"start_ns,end_ns,state_generation,tick,epoch,armed,fault,disabled,command_seq,inference_seq,target_generation,ok\n";
    events_<<"time_ns,epoch,event,reason\n";targets_<<"time_ns,epoch,generation,inference_seq,command_seq,state_generation";
    for(int i=0;i<20;++i)for(const char* f:{"mode","q","dq","kp","kd","tau"})targets_<<",m"<<i<<"_"<<f;
    targets_<<"\n";
    unitree::robot::ChannelFactory::Instance()->Init(1,"lo");
    publisher_=std::make_shared<unitree::robot::ChannelPublisher<Cmd>>("rt/lowcmd");publisher_->InitChannel();
    subscriber_=std::make_shared<unitree::robot::ChannelSubscriber<State>>("rt/lowstate");
    subscriber_->InitChannel([this](const void* raw){receive(*static_cast<const State*>(raw));},1);
  }
  ~Watchdog(){subscriber_->CloseChannel();publisher_->Write(disabled_cmd());publisher_->CloseChannel();}
  std::string request(const std::string& packet) {
    std::lock_guard<std::mutex> lock(mutex_);int64_t now=monotonic_ns();check(now);
    std::istringstream in(packet);std::string op;uint64_t id=0,epoch=0;in>>op>>id;
    if(!in)return response(id,false,"malformed_request");
    if(op=="STATE")return response(id,true);
    in>>epoch;if(!in)return response(id,false,"malformed_request");
    if(epoch!=epoch_)return response(id,false,"stale_epoch");
    if(op=="STOP"){latch("operator_stop",now);return response(id,true);}
    if(op=="FAIL"){latch("actor_error",now);return response(id,true);}
    if(op=="RECOVER") {
      if(history_.empty() || advancing_<3 || now-last_advance_>budget("state"))return response(id,false,"recovery_state_not_fresh");
      ++epoch_;armed_=false;pending_=false;fault_.clear();fault_ns_=0;first_disabled_=0;
      command_seq_=0;inference_seq_=0;command_ns_=0;target_ns_=0;inference_ns_=0;
      inference_state_=0;inference_command_=0;target_=disabled_cmd();
      events_<<now<<","<<epoch_<<",recover,explicit\n";events_.flush();return response(id,true);
    }
    if(!fault_.empty())return response(id,false,"latched");
    if(op=="COMMAND") {
      uint64_t seq=0;int64_t source=0;double x,y,z;in>>seq>>source>>x>>y>>z;
      if(!in || !std::isfinite(x)||!std::isfinite(y)||!std::isfinite(z) || std::max({std::abs(x),std::abs(y),std::abs(z)})>1)latch("invalid_command",now);
      else if(seq<=command_seq_)latch("command_reordered",now);
      else if(source>now || now-source>budget("command"))latch("stale_command",now);
      else {command_seq_=seq;command_ns_=source;}
    } else if(op=="BEGIN") {
      uint64_t seq=0,state=0,command=0;in>>seq>>state>>command;
      auto snap=std::find_if(history_.begin(),history_.end(),[&](const auto& s){return s.generation==state;});
      if(!in || pending_ || seq<=inference_seq_)latch("invalid_inference_token",now);
      else if(snap==history_.end() || now-snap->received>budget("state"))latch("stale_state",now);
      else if(command!=command_seq_ || !command_seq_ || now-command_ns_>budget("command"))latch("stale_command",now);
      else {pending_=true;inference_seq_=seq;inference_state_=state;inference_command_=command;inference_ns_=now;}
    } else if(op=="TARGET") {
      uint64_t seq=0;in>>seq;
      std::vector<std::vector<float>> motors(20,std::vector<float>(6));
      for(auto& m:motors)for(auto& value:m)in>>value;
      if(!in)latch("invalid_target",now);
      else if(!pending_ || seq!=inference_seq_)latch("invalid_inference_token",now);
      else if(now-inference_ns_>budget("inference"))latch("inference_timeout",now);
      else {
        try {
          Cmd msg=encode(motors);
          bool fields=true,limits=true;
          for(int i=0;i<20;++i) {
            const auto& m=msg.motor_cmd()[i];
            if(i<12) {
              fields &= m.mode()==1 && m.dq()==0 && m.kp()==plan_["leg_kp"].as<float>() && m.kd()==plan_["leg_kd"].as<float>() && m.tau()==0;
#ifdef B2W_PD_TARGET_GUARD
              limits &= pd_guard_.target(i,m.q());
#else
              limits &= m.q()>=plan_["target_joint_ranges_rad"][i][0].as<float>() && m.q()<=plan_["target_joint_ranges_rad"][i][1].as<float>();
#endif
            } else if(i<16) {
              fields &= m.mode()==1 && m.q()==0 && m.kp()==0 && m.kd()==plan_["wheel_kd"].as<float>() && m.tau()==0;
#ifdef B2W_PD_TARGET_GUARD
              limits &= pd_guard_.target(i,m.dq());
#else
              limits &= std::abs(m.dq())<=plan_["wheel_target_limit_rad_s"].as<float>();
#endif
            } else fields &= m.mode()==0 && m.q()==2.146e9f && m.dq()==16000 && m.kp()==0 && m.kd()==0 && m.tau()==0;
          }
          if(!fields)latch("invalid_target_fields",now);
          else if(!limits)latch(
#ifdef B2W_PD_TARGET_GUARD
            "pd_target_limit",
#else
            "target_limit",
#endif
            now);
          else if(monotonic_ns()-inference_ns_>budget("inference"))latch("inference_timeout",monotonic_ns());
          else if(command_seq_!=inference_command_)latch("command_changed_during_inference",monotonic_ns());
          else {
            target_=msg;target_ns_=monotonic_ns();pending_=false;++target_generation_;
            targets_<<std::setprecision(9)<<now<<","<<epoch_<<","<<target_generation_<<","<<seq<<","<<inference_command_<<","<<inference_state_;
            for(const auto& m:motors)for(float value:m)targets_<<","<<value;targets_<<"\n";
          }
        } catch(const std::exception&) {latch("invalid_target",now);}
      }
    } else if(op=="ARM") {
      if(!command_seq_ || !target_ns_ || pending_ || now-last_advance_>budget("state") || now-command_ns_>budget("command") || now-target_ns_>budget("target"))
        return response(id,false,"arm_not_ready");
      armed_=true;
    } else return response(id,false,"unknown_operation");
    return response(id,fault_.empty(),fault_.empty()?"":"latched");
  }
  void publish() {
    std::lock_guard<std::mutex> lock(mutex_);int64_t start=monotonic_ns();check(start);
    bool disabled=!armed_ || !fault_.empty();bool ok=publisher_->Write(disabled?disabled_cmd():target_);
    int64_t end=monotonic_ns();
    if(last_publish_)max_interval_=std::max(max_interval_,start-last_publish_);last_publish_=start;++publish_count_;
    if(!fault_.empty() && disabled && ok && !first_disabled_)first_disabled_=end;
    last_disabled_=disabled;
    if(!ok)latch("publish_failed",end);
    publishes_<<start<<","<<end<<","<<generation_<<","<<last_tick_<<","<<epoch_<<","<<armed_<<","<<fault_<<","<<disabled<<","<<command_seq_<<","<<inference_seq_<<","<<target_generation_<<","<<ok<<"\n";
    if(publish_count_%250==0){publishes_.flush();targets_.flush();}
  }
};
int main(int argc,char** argv) {
  if(argc!=4)return 1;
  signal(SIGTERM,[](int){running=0;});signal(SIGINT,[](int){running=0;});
  try {
    YAML::Node plan=YAML::LoadFile(argv[2]);Watchdog watchdog(plan,argv[3]);int fd=rpc_socket(argv[1]);
    int64_t period=plan["publish_period_ns"].as<int64_t>(),deadline=monotonic_ns();
    while(running) {
      for(int n=0;n<32;++n) {
        char buffer[16384];sockaddr_un peer{};socklen_t length=sizeof(peer);
        ssize_t size=recvfrom(fd,buffer,sizeof(buffer),MSG_DONTWAIT,reinterpret_cast<sockaddr*>(&peer),&length);
        if(size<0)break;
        auto reply=watchdog.request(std::string(buffer,size));
        sendto(fd,reply.data(),reply.size(),MSG_DONTWAIT,reinterpret_cast<sockaddr*>(&peer),length);
      }
      int64_t now=monotonic_ns();
      if(now>=deadline){watchdog.publish();deadline+=period;if(now-deadline>period)deadline=now+period;}
      pollfd item{fd,POLLIN,0};poll(&item,1,std::max<int64_t>(0,(deadline-monotonic_ns()+999999)/1000000));
    }
    close(fd);
  } catch(const std::exception& error) {std::cerr<<error.what()<<"\n";return 2;}
  return 0;
}
