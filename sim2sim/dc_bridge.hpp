// Experimental leg-only actuator factor; the pinned bridge remains unchanged.
#pragma once
#include "unitree_sdk2_bridge.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>

class DCMotorBridge : public Go2Bridge {
  const mjtNum *effort_, *saturation_, *velocity_;
  const mjtNum* numeric(const char* name) {
    int id=mj_name2id(mj_model_,mjOBJ_NUMERIC,name);
    if(id<0 || mj_model_->numeric_size[id]!=12)throw std::runtime_error(name);
    const auto* values=mj_model_->numeric_data+mj_model_->numeric_adr[id];
    for(int i=0;i<12;++i)if(!std::isfinite(values[i]) || values[i]<=0)throw std::runtime_error(name);
    return values;
  }
public:
  DCMotorBridge(mjModel* model,mjData* data):Go2Bridge(model,data) {
    effort_=numeric("dc_effort_limits");saturation_=numeric("dc_saturation_efforts");
    velocity_=numeric("dc_velocity_limits");
    for(int i=0;i<12;++i)
      if(!model->actuator_ctrllimited[i] || model->actuator_ctrlrange[2*i]!=-effort_[i]
          || model->actuator_ctrlrange[2*i+1]!=effort_[i])throw std::runtime_error("DC caps mismatch");
  }
  void run() override {
    Go2Bridge::run(); // Retain official state publication and sensor semantics.
    // Recompute from one locked LowCmd snapshot: a DDS arrival cannot mix modes
    // from a new message with PD torque from an older one. Wheels keep PD law.
    std::lock_guard<std::mutex> lock(lowcmd->mutex_);
    for(int i=0;i<16;++i) {
      const auto& m=lowcmd->msg_.motor_cmd()[i];
      if(m.mode()!=1 || (m.kp()==0 && m.kd()==0 && m.tau()==0)) {
        mj_data_->ctrl[i]=0;continue; // Disabled must not cause overspeed braking.
      }
      double dq=mj_data_->sensordata[16+i];
      double requested=m.tau()+m.kp()*(m.q()-mj_data_->sensordata[i])+m.kd()*(m.dq()-dq);
      if(i<12) {
        double speed=std::clamp(dq,-velocity_[i]*(1+effort_[i]/saturation_[i]),
                                  velocity_[i]*(1+effort_[i]/saturation_[i]));
        double upper=std::min(effort_[i],saturation_[i]*(1-speed/velocity_[i]));
        double lower=std::max(-effort_[i],saturation_[i]*(-1-speed/velocity_[i]));
        requested=std::clamp(requested,lower,upper);
      }
      mj_data_->ctrl[i]=requested;
    }
  }
};
