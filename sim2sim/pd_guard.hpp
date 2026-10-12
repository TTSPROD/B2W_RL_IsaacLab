#pragma once
#include "sdk2_io.hpp"
#include <yaml-cpp/yaml.h>
#include <array>
#include <algorithm>
#include <optional>

struct StateLimitViolation {
  std::string reason,quantity;int slot;double value,lower,upper;
};
class Sim2simPDGuard {
  std::array<std::array<double,2>,12> actual_q_,pd_q_;
  std::array<std::array<double,2>,4> pd_dq_;
  std::array<double,16> actual_speed_;
  double position_tolerance_,velocity_tolerance_,tilt_limit_;
  template<size_t N> static void ranges(const YAML::Node& node,std::array<std::array<double,2>,N>& out) {
    if(!node.IsSequence() || node.size()!=N)throw std::invalid_argument("Wrong range count");
    for(size_t i=0;i<N;++i) {
      if(node[i].size()!=2)throw std::invalid_argument("Range pair required");
      out[i]={node[i][0].as<double>(),node[i][1].as<double>()};
      if(!std::isfinite(out[i][0]) || !std::isfinite(out[i][1]) || out[i][0]>=out[i][1])
        throw std::invalid_argument("Invalid range");
    }
  }
public:
  explicit Sim2simPDGuard(const YAML::Node& plan) {
    if(plan["schema"].as<std::string>()!="b2w_sim2sim_pd_reference_guard_v1"
      || plan["hardware_enabled"].as<bool>() || plan["domain"].as<int>()!=1
      || plan["interface"].as<std::string>()!="lo")throw std::invalid_argument("Simulator PD profile required");
    ranges(plan["actual_joint_ranges_rad"],actual_q_);ranges(plan["pd_joint_target_ranges_rad"],pd_q_);
    ranges(plan["pd_wheel_target_ranges_rad_s"],pd_dq_);
    if(plan["actual_velocity_limits_rad_s"].size()!=16)throw std::invalid_argument("16 speed limits required");
    for(int i=0;i<16;++i) {
      actual_speed_[i]=plan["actual_velocity_limits_rad_s"][i].as<double>();
      if(!std::isfinite(actual_speed_[i]) || actual_speed_[i]<=0)throw std::invalid_argument("Invalid speed limit");
    }
    position_tolerance_=plan["actual_position_tolerance_rad"].as<double>();
    velocity_tolerance_=plan["actual_velocity_relative_tolerance"].as<double>();
    tilt_limit_=plan["actual_tilt_limit_rad"].as<double>();
    if(position_tolerance_!=.001 || velocity_tolerance_!=.001 || std::abs(tilt_limit_-std::acos(-1.)/3)>1e-12)
      throw std::invalid_argument("Existing physical safety thresholds required");
    for(auto r:pd_q_)if(r[0]!=-100 || r[1]!=100)throw std::invalid_argument("Isaac PD reference envelope required");
    for(auto r:pd_dq_)if(r[0]!=-100 || r[1]!=100)throw std::invalid_argument("Isaac PD reference envelope required");
  }
  bool target(int slot,double value) const {
    const auto& range=slot<12?pd_q_[slot]:pd_dq_[slot-12];
    return std::isfinite(value) && value>=range[0] && value<=range[1];
  }
  std::optional<StateLimitViolation> state(const State& msg) const {
    for(int i=0;i<16;++i) {
      const auto& m=msg.motor_state()[i];
      if(i<12 && (m.q()<actual_q_[i][0]-position_tolerance_ || m.q()>actual_q_[i][1]+position_tolerance_))
        return StateLimitViolation{"actual_joint_position","q_rad",i,m.q(),actual_q_[i][0]-position_tolerance_,actual_q_[i][1]+position_tolerance_};
      double limit=actual_speed_[i]*(1+velocity_tolerance_);
      if(std::abs(m.dq())>limit)return StateLimitViolation{"actual_joint_velocity","dq_rad_s",i,m.dq(),-limit,limit};
    }
    const auto& q=msg.imu_state().quaternion();
    double tilt=std::acos(std::clamp(1.-2.*(double(q[1])*q[1]+double(q[2])*q[2]),-1.,1.));
    if(tilt>tilt_limit_)return StateLimitViolation{"actual_tilt","tilt_rad",-1,tilt,0,tilt_limit_};
    return std::nullopt;
  }
};
