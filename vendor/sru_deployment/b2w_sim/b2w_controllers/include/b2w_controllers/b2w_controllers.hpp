#ifndef B2W_CONTROLLERS_HPP
#define B2W_CONTROLLERS_HPP

#include "rclcpp/rclcpp.hpp"
#include "nav_msgs/msg/odometry.hpp"
#include "geometry_msgs/msg/twist.hpp"
#include "sensor_msgs/msg/joint_state.hpp"
#include "std_msgs/msg/float64_multi_array.hpp"
#include <std_msgs/msg/float64.hpp>

#include "tf2/LinearMath/Quaternion.h"
#include "tf2/LinearMath/Matrix3x3.h"
#include <tf2_geometry_msgs/tf2_geometry_msgs.hpp>
#include <ament_index_cpp/get_package_share_directory.hpp>
#include <onnxruntime_cxx_api.h>
#include <eigen3/Eigen/Dense>

#include <array>
#include <filesystem>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

class B2WControllers : public rclcpp::Node {
public:
    explicit B2WControllers(const rclcpp::NodeOptions &options = rclcpp::NodeOptions());

private:
    static constexpr int kNumJoints = 16;
    static constexpr int kInputSize = 60;
    static constexpr int kHiddenSize = 256;

    struct EnvironmentConfig {
        std::vector<double> default_joint_positions;
        std::vector<double> base_position_xyz;
        std::vector<double> base_orientation_rpy;
    };

    // Parameter helpers
    void loadParameters();
    void resolvePolicyPath();

    // Initialization methods
    void initializeJointNamesAndTopics();
    void setupSubscribers();
    void setupPublishers();
    void setupTimers();

    // Callback functions
    void odometryCallback(const nav_msgs::msg::Odometry::SharedPtr msg);
    void velocityCallback(const geometry_msgs::msg::Twist::SharedPtr msg);
    void jointStateCallback(const sensor_msgs::msg::JointState::SharedPtr msg);
    void processOdometry();

    // Processing methods
    void inference(); 
    void processActions();
    void publishDebugData();
    void publishJointCommands();

    rclcpp::CallbackGroup::SharedPtr inference_group_;
    rclcpp::CallbackGroup::SharedPtr pub_group_;

    // ROS components
    rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odometry_sub_;
    rclcpp::Subscription<geometry_msgs::msg::Twist>::SharedPtr velocity_sub_;
    rclcpp::Subscription<sensor_msgs::msg::JointState>::SharedPtr joint_state_sub_;

    rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr action_pub_;
    rclcpp::Publisher<std_msgs::msg::Float64MultiArray>::SharedPtr network_input_debug_pub_;
    std::map<std::string, rclcpp::Publisher<std_msgs::msg::Float64>::SharedPtr> joint_pubs_;
    

    rclcpp::TimerBase::SharedPtr timer_;
    rclcpp::TimerBase::SharedPtr timer_pub_;

    std::vector<std::string> joint_names_;
    std::vector<std::string> joint_topics_;

    std::map<std::string, double> joint_commands_;
    std::vector<double> joint_command_buffer_;

    // ONNX components
    Ort::Env env_;
    Ort::AllocatorWithDefaultOptions allocator_;
    std::unique_ptr<Ort::Session> session_;
    std::vector<const char *> input_node_names_;
    std::vector<const char *> output_node_names_;

    // Variables to store data
    geometry_msgs::msg::Vector3 base_lin_vel_;
    geometry_msgs::msg::Vector3 base_ang_vel_;
    Eigen::Vector3d projected_gravity_;
    geometry_msgs::msg::Twist cmd_vel_;

    Eigen::VectorXd joint_positions_;
    Eigen::VectorXd joint_velocities_;
    Eigen::VectorXd default_joint_positions_;

    Eigen::VectorXd last_actions_;
    Eigen::VectorXd reordered_actions_;

    Eigen::Matrix3d rotation_matrix_;
    bool odometry_received_;
    bool odometry_warned_;
    std::mutex odometry_mutex_;
    std::mutex joint_state_mutex_;
    std::mutex command_mutex_;

    std::vector<float> h_in_data_;   // Hidden state data buffer
    std::vector<float> c_in_data_;   // Cell state data buffer
    std::array<float, kInputSize> input_buffer_;

    // Runtime configuration
    std::string policy_package_;
    std::string policy_relative_path_;
    std::string policy_override_path_;
    std::filesystem::path policy_path_;

    std::string odometry_topic_;
    std::string velocity_topic_;
    std::string joint_state_topic_;

    std::vector<int> reorder_indices_;

    double non_foot_joint_scale_;
    double foot_joint_scale_;

    std::string environment_profile_;
    EnvironmentConfig environment_config_;

    bool publish_joint_array_;
};


#endif // B2W_CONTROLLERS_HPP
