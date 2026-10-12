#include "dc_bridge.hpp"
#define Go2Bridge DCMotorBridge
#define main grid_main
#include "actuator_probe.cpp"
#undef main
#undef Go2Bridge

int main(int argc,char** argv) {
  int result=grid_main(argc,argv);if(result)return result;
  char error[1024];auto* model=mj_loadXML(argv[1],nullptr,error,sizeof(error));
  if(!model)return 2;
  auto* data=mj_makeData(model);mj_resetDataKeyframe(model,data,0);
  std::ofstream out(std::string(argv[2])+".disabled.csv");out<<std::setprecision(17);
  out<<"mode,zero_gains,speed_ratio,slot,ctrl,force\n";
  {
    DCMotorBridge bridge(model,data);
    for(int mode:{0,1,2})for(double speed:{-2.5,-1.5,0.,1.5,2.5}) {
      for(int i=0;i<16;++i) {
        int joint=model->actuator_trnid[2*i];
        data->qvel[model->jnt_dofadr[joint]]=speed*(i>=12?50:(i%3==2?14:23));
      }
      mj_forward(model,data);
      {
        std::lock_guard<std::mutex> lock(bridge.lowcmd->mutex_);
        for(int i=0;i<16;++i) {
          auto& m=bridge.lowcmd->msg_.motor_cmd()[i];m.mode()=mode;
          m.q()=2.146e9;m.dq()=16000;m.tau()=0;
          m.kp()=mode==1?0:160;m.kd()=mode==1?0:5;
        }
      }
      bridge.run();mj_fwdActuation(model,data);
      for(int i=0;i<16;++i) {
        out<<mode<<","<<(mode==1)<<","<<speed<<","<<i<<","<<data->ctrl[i]<<","<<data->actuator_force[i]<<"\n";
        if(data->ctrl[i]!=0 || data->actuator_force[i]!=0)return 5;
      }
    }
  }
  mj_deleteData(data);mj_deleteModel(model);return 0;
}
