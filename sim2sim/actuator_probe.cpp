// Instantaneous law audit: pinned Go2Bridge::run and MuJoCo actuation.
// No integration, no LowCmd publisher, and simulator domain 1 / lo only.
#include "unitree_sdk2_bridge.h"
#include <fstream>
#include <iomanip>
#include <mutex>
#include <cmath>
#include <algorithm>

int main(int argc, char** argv) {
  if(argc!=3)return 1;
  param::config.robot="b2w";param::config.domain_id=1;param::config.interface="lo";
  param::config.use_joystick=0;param::config.print_scene_information=0;
  char error[1024];auto* model=mj_loadXML(argv[1],nullptr,error,sizeof(error));
  if(!model){std::cerr<<error<<"\n";return 2;}
  if(model->nu!=16)return 3;
  auto* data=mj_makeData(model);mj_resetDataKeyframe(model,data,0);mj_forward(model,data);
  unitree::robot::ChannelFactory::Instance()->Init(1,"lo");
  std::ofstream out(argv[2]);out<<std::setprecision(17);
  out<<"sample,slot,speed_ratio,request_ratio,q,dq,q_target,dq_target,kp,kd,tau_ff,bridge_ctrl,mujoco_force\n";
  const double limits[16]={200,200,320,200,200,320,200,200,320,200,200,320,20,20,20,20};
  const double speeds[16]={23,23,14,23,23,14,23,23,14,23,23,14,50,50,50,50};
  int sample=0;
  {
    Go2Bridge bridge(model,data);
    for(double velocity:{-2.5,-2.,-1.5,-1.,-.5,0.,.5,1.,1.5,2.,2.5})
      for(double request:{-2.,-1.,-.5,0.,.5,1.,2.}) {
        for(int i=0;i<16;++i) {
          int joint=model->actuator_trnid[2*i];
          data->qvel[model->jnt_dofadr[joint]]=velocity*speeds[i];
        }
        mj_forward(model,data);
        {
          std::lock_guard<std::mutex> lock(bridge.lowcmd->mutex_);
          for(int i=0;i<16;++i) {
            auto& m=bridge.lowcmd->msg_.motor_cmd()[i];
            m.mode()=1;m.tau()=0;
            // Choose targets producing the requested torque including damping.
            m.kp()=i<12?160:0;m.kd()=i<12?5:1;
            m.q()=i<12?data->sensordata[i]+(request*limits[i]+5*data->sensordata[16+i])/160:0;
            m.dq()=i<12?0:data->sensordata[16+i]+request*limits[i];
          }
        }
        bridge.run();mj_fwdActuation(model,data);
        for(int i=0;i<16;++i) {
          const auto& m=bridge.lowcmd->msg_.motor_cmd()[i];
          if(!std::isfinite(data->ctrl[i]) || !std::isfinite(data->actuator_force[i]))return 4;
          out<<sample<<","<<i<<","<<velocity<<","<<request<<","<<data->sensordata[i]
             <<","<<data->sensordata[16+i]<<","<<m.q()<<","<<m.dq()<<","<<m.kp()<<","<<m.kd()
             <<","<<m.tau()<<","<<data->ctrl[i]<<","<<data->actuator_force[i]<<"\n";
        }
        ++sample;
      }
  }
  mj_deleteData(data);mj_deleteModel(model);return 0;
}
