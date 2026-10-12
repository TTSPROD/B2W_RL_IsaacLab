#pragma once
#include <unitree/idl/go2/LowCmd_.hpp>
#include <unitree/idl/go2/LowState_.hpp>
#include <cmath>
#include <cstring>
#include <vector>
#include <stdexcept>
using Cmd = unitree_go::msg::dds_::LowCmd_;
using State = unitree_go::msg::dds_::LowState_;
template <typename Message> uint32_t crc(const Message& msg) {
  uint32_t result = 0xffffffff;
  const auto* bytes = reinterpret_cast<const unsigned char*>(&msg);
  for (size_t i=0; i<sizeof(Message)/4-1; ++i) {
    uint32_t word; std::memcpy(&word, bytes+4*i, 4);
    for (uint32_t bit=0x80000000; bit; bit>>=1) {
      bool high = result & 0x80000000;
      result <<= 1;
      if (high) result ^= 0x04c11db7;
      if (word & bit) result ^= 0x04c11db7;
    }
  }
  return result;
}
inline Cmd encode(const std::vector<std::vector<float>>& motors) {
  if (motors.size()!=20) throw std::invalid_argument("Expected all 20 motor slots");
  Cmd msg{}; msg.head()[0]=0xfe; msg.head()[1]=0xef; msg.level_flag()=0xff;
  for (size_t i=0; i<20; ++i) {
    if (motors[i].size()!=6) throw std::invalid_argument("mode,q,dq,kp,kd,tau required");
    for (float value:motors[i]) if (!std::isfinite(value)) throw std::invalid_argument("Nonfinite LowCmd");
    if (motors[i][0]!=0 && motors[i][0]!=1) throw std::invalid_argument("Invalid motor mode");
    auto& m=msg.motor_cmd()[i];
    m.mode()=static_cast<uint8_t>(motors[i][0]); m.q()=motors[i][1]; m.dq()=motors[i][2];
    m.kp()=motors[i][3]; m.kd()=motors[i][4]; m.tau()=motors[i][5];
  }
  msg.crc()=crc(msg); return msg;
}
inline Cmd disabled_cmd() {
  return encode(std::vector<std::vector<float>>(20,{0,2.146e9f,16000,0,0,0}));
}
inline bool is_disabled(const Cmd& cmd) {
  for (const auto& m:cmd.motor_cmd())
    if(m.mode()!=0 || m.kp()!=0 || m.kd()!=0 || m.tau()!=0 || m.q()!=2.146e9f || m.dq()!=16000) return false;
  return cmd.head()[0]==0xfe && cmd.head()[1]==0xef && cmd.crc()==crc(cmd);
}
