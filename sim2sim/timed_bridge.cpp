// Same DC bridge and physics/safety; telemetry stays in preallocated memory
// until physics and DDS publication have stopped. No disk IO in the loop.
#include "dc_bridge.hpp"
#include <chrono>
#include <fstream>
#include <csignal>
#include <thread>
#include <iomanip>
#include <vector>
#include <array>
#include <sys/resource.h>
#include <time.h>

volatile std::sig_atomic_t running=1;
static int64_t ns(clockid_t clock) {timespec t;clock_gettime(clock,&t);return int64_t(t.tv_sec)*1000000000+t.tv_nsec;}
struct Sample {
  int64_t timestamp,begin,cpu_begin,bridge_wall,bridge_cpu,step_wall,step_cpu,capture_wall,capture_cpu;
  long minflt,nvcsw,nivcsw;
  std::array<double,16> basic;
  std::array<double,6> body;
  std::array<double,64> motors;
};
int main(int argc,char** argv) {
  if(argc!=4)return 1;
  std::signal(SIGTERM,[](int){running=0;});std::signal(SIGINT,[](int){running=0;});
  param::config.robot="b2w";param::config.domain_id=1;param::config.interface="lo";
  param::config.use_joystick=0;param::config.print_scene_information=0;
  char error[1024];auto* model=mj_loadXML(argv[1],nullptr,error,sizeof(error));
  if(!model){std::cerr<<error<<"\n";return 2;}
  if(model->nu!=16 || model->nq!=23 || model->nv!=22 || model->nkey!=1)return 3;
  auto* data=mj_makeData(model);mj_resetDataKeyframe(model,data,0);mj_forward(model,data);
  int velocity_id=mj_name2id(model,mjOBJ_NUMERIC,"policy_velocity_limits"),gyro=mj_name2id(model,mjOBJ_SENSOR,"imu_gyro");
  if(velocity_id<0 || model->numeric_size[velocity_id]!=16 || gyro<0)return 7;
  const double* limits=model->numeric_data+model->numeric_adr[velocity_id];
  const int floor=mj_name2id(model,mjOBJ_GEOM,"floor");
  double duration=std::stod(argv[2]);
  if(!std::isfinite(duration) || duration<=0 || duration>60)return 9;
  // Value-initialization touches pages before the real-time section.
  std::vector<Sample> records(size_t(std::ceil(duration/model->opt.timestep))+16);
  size_t count=0;int result=0;
  unitree::robot::ChannelFactory::Instance()->Init(1,"lo");
  {
    DCMotorBridge bridge(model,data);auto origin=std::chrono::steady_clock::now();
    while(running && data->time<duration) {
      if(count==records.size()){result=9;break;}
      auto& s=records[count];rusage before{},after{};getrusage(RUSAGE_THREAD,&before);
      s.begin=ns(CLOCK_MONOTONIC);s.cpu_begin=ns(CLOCK_THREAD_CPUTIME_ID);
      bridge.run();auto bridge_end=ns(CLOCK_MONOTONIC),bridge_cpu=ns(CLOCK_THREAD_CPUTIME_ID);
      mj_step(model,data);s.timestamp=ns(CLOCK_MONOTONIC);auto step_cpu=ns(CLOCK_THREAD_CPUTIME_ID);
      s.bridge_wall=bridge_end-s.begin;s.bridge_cpu=bridge_cpu-s.cpu_begin;
      s.step_wall=s.timestamp-bridge_end;s.step_cpu=step_cpu-bridge_cpu;
      double effort=0,forbidden=0,margin=1e9,velocity=0;
      bool finite=true;
      for(int i=0;i<16;++i) {
        int joint=model->actuator_trnid[2*i];double q=data->qpos[model->jnt_qposadr[joint]],dq=data->qvel[model->jnt_dofadr[joint]];
        double tau=data->actuator_force[i];effort=std::max(effort,std::abs(tau));
        finite &= std::isfinite(q) && std::isfinite(dq) && std::isfinite(tau);
        velocity=std::max(velocity,std::abs(dq)/limits[i]);
        if(i<12)margin=std::min(margin,std::min(q-model->jnt_range[2*joint],model->jnt_range[2*joint+1]-q));
        s.motors[4*i]=q;s.motors[4*i+1]=dq;s.motors[4*i+2]=tau;s.motors[4*i+3]=data->ctrl[i];
      }
      double tilt=std::acos(std::clamp(1-2*(data->qpos[4]*data->qpos[4]+data->qpos[5]*data->qpos[5]),-1.,1.));
      for(int i=0;i<data->ncon;++i) {
        const auto& c=data->contact[i];if(c.geom1!=floor && c.geom2!=floor)continue;
        int other=c.geom1==floor?c.geom2:c.geom1;const char* name=mj_id2name(model,mjOBJ_BODY,model->geom_bodyid[other]);
        if(name && std::string(name).find("wheel")!=std::string::npos)continue;
        mjtNum force[6];mj_contactForce(model,data,i,force);forbidden=std::max(forbidden,std::abs(force[0]));
      }
      s.basic[0]=data->time;
      for(int i=0;i<3;++i){s.basic[1+i]=data->qpos[i];s.basic[4+i]=data->qvel[i];finite &= std::isfinite(data->qpos[i]);}
      for(int i=0;i<4;++i){s.basic[7+i]=data->qpos[3+i];finite &= std::isfinite(data->qpos[3+i]);}
      s.basic[11]=effort;s.basic[12]=tilt;s.basic[13]=forbidden;s.basic[14]=margin;s.basic[15]=velocity;
      mjtNum inverse[4]={data->qpos[3],-data->qpos[4],-data->qpos[5],-data->qpos[6]},body_velocity[3];
      mju_rotVecQuat(body_velocity,data->qvel,inverse);
      for(int i=0;i<3;++i){s.body[i]=body_velocity[i];s.body[3+i]=data->sensordata[model->sensor_adr[gyro]+i];}
      s.capture_wall=ns(CLOCK_MONOTONIC)-s.timestamp;s.capture_cpu=ns(CLOCK_THREAD_CPUTIME_ID)-step_cpu;
      getrusage(RUSAGE_THREAD,&after);s.minflt=after.ru_minflt-before.ru_minflt;s.nvcsw=after.ru_nvcsw-before.ru_nvcsw;s.nivcsw=after.ru_nivcsw-before.ru_nivcsw;
      ++count;
      if(!finite){result=5;break;}
      if(tilt>M_PI/3 || data->qpos[2]<.35 || forbidden>1 || margin<-.001 || velocity>1.001){result=6;break;}
      std::this_thread::sleep_until(origin+std::chrono::duration_cast<std::chrono::steady_clock::duration>(std::chrono::duration<double>(data->time)));
    }
  }
  // Serialization runs after bridge destruction; no telemetry drop/overwrite.
  std::ofstream basic(argv[3]),detail(std::string(argv[3])+".detailed.csv"),timing(std::string(argv[3])+".timing.csv");
  basic<<std::setprecision(17);detail<<std::setprecision(17);
  basic<<"time,x,y,z,vx,vy,vz,qw,qx,qy,qz,max_effort,tilt_rad,forbidden_force_n,joint_margin_rad,velocity_util\n";
  detail<<"monotonic_ns,time,body_vx,body_vy,body_vz,body_wx,body_wy,body_wz";
  for(int i=0;i<16;++i)for(const char* f:{"q","dq","tau","ctrl"})detail<<",m"<<i<<"_"<<f;detail<<"\n";
  timing<<"begin_ns,sample_ns,cpu_begin_ns,bridge_wall_ns,bridge_cpu_ns,step_wall_ns,step_cpu_ns,capture_wall_ns,capture_cpu_ns,minor_faults,voluntary_switches,involuntary_switches\n";
  for(size_t i=0;i<count;++i) {
    const auto& s=records[i];for(int j=0;j<16;++j){if(j)basic<<",";basic<<s.basic[j];}basic<<"\n";
    detail<<s.timestamp<<","<<s.basic[0];for(auto x:s.body)detail<<","<<x;for(auto x:s.motors)detail<<","<<x;detail<<"\n";
    timing<<s.begin<<","<<s.timestamp<<","<<s.cpu_begin<<","<<s.bridge_wall<<","<<s.bridge_cpu<<","<<s.step_wall<<","<<s.step_cpu
      <<","<<s.capture_wall<<","<<s.capture_cpu<<","<<s.minflt<<","<<s.nvcsw<<","<<s.nivcsw<<"\n";
  }
  basic.flush();detail.flush();timing.flush();
  if(!basic || !detail || !timing)result=10;
  std::ofstream summary(std::string(argv[3])+".capture.json");
  summary<<"{\"captured\":"<<count<<",\"capacity\":"<<records.size()<<",\"drops\":0,\"disk_io_in_physics_loop\":false,\"result\":"<<result<<"}\n";
  mj_deleteData(data);mj_deleteModel(model);return result;
}
