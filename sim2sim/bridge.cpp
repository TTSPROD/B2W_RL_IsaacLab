// Headless harness of the pinned official Go2Bridge used for B2W (unitree_go).
// No vendor edits; run() and physics share one thread to avoid mjData races.
#include "unitree_sdk2_bridge.h"
#include <chrono>
#include <fstream>
#include <csignal>
#include <thread>
#include <iomanip>
volatile std::sig_atomic_t running=1;
int main(int argc,char** argv) {
  if(argc!=4) {std::cerr<<"bridge scene.xml duration_s telemetry.csv\n";return 1;}
  std::signal(SIGTERM,[](int){running=0;}); std::signal(SIGINT,[](int){running=0;});
  param::config.robot="b2w"; param::config.domain_id=1; param::config.interface="lo";
  param::config.use_joystick=0; param::config.print_scene_information=0;
  char error[1024]; auto* model=mj_loadXML(argv[1],nullptr,error,sizeof(error));
  if(!model) {std::cerr<<error<<"\n";return 2;}
  if(model->nu!=16 || model->nq!=23 || model->nv!=22) return 3;
  auto* data=mj_makeData(model);
  // reset keyframe authored by the harness from the checked policy contract.
  if(model->nkey!=1) return 4;
  mj_resetDataKeyframe(model,data,0); mj_forward(model,data);
  unitree::robot::ChannelFactory::Instance()->Init(1,"lo");
  std::ofstream log(argv[3]); log<<std::setprecision(17);
  log<<"time,x,y,z,vx,vy,vz,qw,qx,qy,qz,max_effort,tilt_rad,forbidden_force_n,joint_margin_rad,velocity_util\n";
  // Additional evidence for the physics audit; original CSV remains unchanged.
  std::ofstream detailed;
  int gyro_sensor=mj_name2id(model,mjOBJ_SENSOR,"imu_gyro");
  if(gyro_sensor<0)return 8;
  std::string detailed_path=std::string(argv[3])+".detailed.csv";
  detailed.open(detailed_path);detailed<<std::setprecision(17);
  detailed<<"monotonic_ns,time,body_vx,body_vy,body_vz,body_wx,body_wy,body_wz";
  for(int i=0;i<16;++i)for(const char* field:{"q","dq","tau","ctrl"})detailed<<",m"<<i<<"_"<<field;
  detailed<<"\n";
  int velocity_id=mj_name2id(model,mjOBJ_NUMERIC,"policy_velocity_limits");
  if(velocity_id<0 || model->numeric_size[velocity_id]!=16) return 7;
  const double* limits=model->numeric_data+model->numeric_adr[velocity_id];
  int floor=mj_name2id(model,mjOBJ_GEOM,"floor");
  int result=0;
  {
    Go2Bridge bridge(model,data);
    auto origin=std::chrono::steady_clock::now();
    double duration=std::stod(argv[2]);
    while(running && data->time<duration) {
      bridge.run();
      mj_step(model,data);
      double effort=0; for(int i=0;i<16;++i) effort=std::max(effort,std::abs(data->actuator_force[i]));
      if(!std::isfinite(data->qpos[2])) return 5;
      double tilt=acos(std::clamp(1-2*(data->qpos[4]*data->qpos[4]+data->qpos[5]*data->qpos[5]),-1.0,1.0));
      double forbidden=0, margin=1e9, velocity=0;
      for(int i=0;i<16;++i) {
        int joint=model->actuator_trnid[2*i];
        velocity=std::max(velocity,std::abs(data->qvel[model->jnt_dofadr[joint]])/limits[i]);
        if(i<12) {
          double q=data->qpos[model->jnt_qposadr[joint]];
          margin=std::min(margin,std::min(q-model->jnt_range[2*joint],model->jnt_range[2*joint+1]-q));
        }
      }
      for(int i=0;i<data->ncon;++i) {
        const auto& c=data->contact[i];
        if(c.geom1!=floor && c.geom2!=floor) continue;
        int other=c.geom1==floor?c.geom2:c.geom1;
        const char* name=mj_id2name(model,mjOBJ_BODY,model->geom_bodyid[other]);
        if(name && std::string(name).find("wheel")!=std::string::npos) continue;
        mjtNum force[6];mj_contactForce(model,data,i,force);
        forbidden=std::max(forbidden,std::abs(force[0]));
      }
      log<<data->time;
      for(int i=0;i<3;++i) log<<","<<data->qpos[i];
      for(int i=0;i<3;++i) log<<","<<data->qvel[i];
      for(int i=3;i<7;++i) log<<","<<data->qpos[i];
      log<<","<<effort<<","<<tilt<<","<<forbidden<<","<<margin<<","<<velocity<<"\n";
      mjtNum inverse[4]={data->qpos[3],-data->qpos[4],-data->qpos[5],-data->qpos[6]},body_velocity[3];
      mju_rotVecQuat(body_velocity,data->qvel,inverse);
      auto timestamp=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
      detailed<<timestamp<<","<<data->time;
      for(double value:body_velocity)detailed<<","<<value;
      // Gyro comes from the same local IMU sensor used by official DDS LowState.
      int gyro=model->sensor_adr[gyro_sensor];
      for(int i=0;i<3;++i)detailed<<","<<data->sensordata[gyro+i];
      for(int i=0;i<16;++i) {
        int joint=model->actuator_trnid[2*i];
        detailed<<","<<data->qpos[model->jnt_qposadr[joint]]<<","<<data->qvel[model->jnt_dofadr[joint]]
                <<","<<data->actuator_force[i]<<","<<data->ctrl[i];
      }
      detailed<<"\n";
      // No grace for unsafe. Model ranges/speeds are diagnostic simulator gates.
      if(tilt>M_PI/3 || data->qpos[2]<.35 || forbidden>1 || margin<-.001 || velocity>1.001) {
        std::cerr<<"SIM_UNSAFE time="<<data->time<<" tilt="<<tilt<<" contact="<<forbidden
          <<" margin="<<margin<<" velocity="<<velocity<<"\n";
        result=6;break;
      }
      std::this_thread::sleep_until(origin+std::chrono::duration_cast<std::chrono::steady_clock::duration>(std::chrono::duration<double>(data->time)));
    }
  }
  mj_deleteData(data);mj_deleteModel(model);return result;
}
