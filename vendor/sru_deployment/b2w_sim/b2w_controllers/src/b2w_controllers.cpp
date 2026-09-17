#include "b2w_controllers/b2w_controllers.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <functional>
#include <stdexcept>
#include <sstream>
#include <type_traits>

#include <rclcpp/executors/multi_threaded_executor.hpp>

namespace {
constexpr std::chrono::milliseconds kInferencePeriod{20};   // 50 Hz
constexpr std::chrono::milliseconds kPublishPeriod{5};      // 200 Hz

template <typename T>
T getOrDeclare(rclcpp::Node &node, const std::string &name, const T &default_value) {
    rclcpp::Parameter param;
    if (node.get_parameter(name, param)) {
        return param.get_parameter_value().get<T>();
    }
    return node.declare_parameter<T>(name, default_value);
}
}  // namespace

B2WControllers::B2WControllers(const rclcpp::NodeOptions &options)
    : Node("b2w_controllers", options),
      env_(ORT_LOGGING_LEVEL_WARNING, "onnx_policy"),
      allocator_(),
      session_(nullptr),
      joint_positions_(kNumJoints),
      joint_velocities_(kNumJoints),
      default_joint_positions_(kNumJoints),
      last_actions_(kNumJoints),
      reordered_actions_(kNumJoints),
      rotation_matrix_(Eigen::Matrix3d::Identity()),
      odometry_received_(false),
      odometry_warned_(false) {
    bool use_sim_time = getOrDeclare<bool>(*this, "use_sim_time", true);
    this->set_parameter(rclcpp::Parameter("use_sim_time", use_sim_time));

    loadParameters();
    resolvePolicyPath();

    try {
        Ort::SessionOptions session_options;
        session_options.SetIntraOpNumThreads(1);
        session_options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
        session_ = std::make_unique<Ort::Session>(env_, policy_path_.c_str(), session_options);
        RCLCPP_INFO(this->get_logger(), "Loaded policy from %s", policy_path_.string().c_str());
    } catch (const Ort::Exception &e) {
        RCLCPP_FATAL(this->get_logger(), "Failed to initialize ONNX session: %s", e.what());
        throw;
    }

    input_node_names_ = {"obs", "h_in", "c_in"};
    output_node_names_ = {"actions", "h_out", "c_out"};

    if (environment_config_.default_joint_positions.size() != kNumJoints) {
        throw std::runtime_error("Environment configuration default_joint_positions size mismatch");
    }
    default_joint_positions_ = Eigen::Map<Eigen::VectorXd>(
        environment_config_.default_joint_positions.data(),
        environment_config_.default_joint_positions.size());

    cmd_vel_ = geometry_msgs::msg::Twist();
    base_lin_vel_ = geometry_msgs::msg::Vector3();
    base_ang_vel_ = geometry_msgs::msg::Vector3();
    projected_gravity_ = Eigen::Vector3d(0.0, 0.0, -1.0);

    joint_positions_ = Eigen::VectorXd::Zero(kNumJoints);
    joint_velocities_ = Eigen::VectorXd::Zero(kNumJoints);
    last_actions_ = Eigen::VectorXd::Zero(kNumJoints);
    reordered_actions_ = default_joint_positions_;

    h_in_data_.assign(kHiddenSize, 0.0f);
    c_in_data_.assign(kHiddenSize, 0.0f);
    input_buffer_.fill(0.0f);

    initializeJointNamesAndTopics();
    setupSubscribers();
    setupPublishers();
    setupTimers();

    RCLCPP_INFO(this->get_logger(),
                "B2W Controllers node ready (environment profile: %s, base_position: [%.2f, %.2f, %.2f], base_orientation_rpy: [%.2f, %.2f, %.2f])",
                environment_profile_.c_str(),
                environment_config_.base_position_xyz[0], environment_config_.base_position_xyz[1],
                environment_config_.base_position_xyz[2],
                environment_config_.base_orientation_rpy[0], environment_config_.base_orientation_rpy[1],
                environment_config_.base_orientation_rpy[2]);
}

void B2WControllers::loadParameters() {
    const std::vector<std::string> default_joint_names = {
        "FL_hip_joint", "FR_hip_joint", "RL_hip_joint", "RR_hip_joint",
        "FL_thigh_joint", "FR_thigh_joint", "RL_thigh_joint", "RR_thigh_joint",
        "FL_calf_joint", "FR_calf_joint", "RL_calf_joint", "RR_calf_joint",
        "FL_foot_joint", "FR_foot_joint", "RL_foot_joint", "RR_foot_joint"};

    const std::vector<std::string> default_joint_topics = {
        "/FL_hip_joint_position_cmd", "/FR_hip_joint_position_cmd",
        "/RL_hip_joint_position_cmd", "/RR_hip_joint_position_cmd",
        "/FL_thigh_joint_position_cmd", "/FR_thigh_joint_position_cmd",
        "/RL_thigh_joint_position_cmd", "/RR_thigh_joint_position_cmd",
        "/FL_calf_joint_position_cmd", "/FR_calf_joint_position_cmd",
        "/RL_calf_joint_position_cmd", "/RR_calf_joint_position_cmd",
        "/FL_foot_joint_velocity_cmd", "/FR_foot_joint_velocity_cmd",
        "/RL_foot_joint_velocity_cmd", "/RR_foot_joint_velocity_cmd"};

    const std::vector<int64_t> default_reorder = {
        0, 4, 8, 12, 1, 5, 9, 13, 2, 6, 10, 14, 3, 7, 11, 15};

    const std::vector<double> default_joint_positions = {
        0.0,  0.0,  0.0,  0.0,  // hips
        0.4,  0.4,  0.4,  0.4,  // thighs
       -1.3, -1.3, -1.3, -1.3,  // calves
        0.0,  0.0,  0.0,  0.0}; // feet

    policy_package_ = getOrDeclare<std::string>(*this, "policy.package", "b2w_controllers");
    policy_relative_path_ = getOrDeclare<std::string>(*this, "policy.relative_path", "policy/policy_force_new.onnx");
    policy_override_path_ = getOrDeclare<std::string>(*this, "policy.path", "");

    odometry_topic_ = getOrDeclare<std::string>(*this, "topics.odometry", "/dlio/odom_node/odom");
    velocity_topic_ = getOrDeclare<std::string>(*this, "topics.cmd_vel", "/path_manager/path_manager_ros/nav_vel");
    joint_state_topic_ = getOrDeclare<std::string>(*this, "topics.joint_state", "/joint_states");

    joint_names_ = getOrDeclare<std::vector<std::string>>(*this, "joint_model.names", default_joint_names);
    joint_topics_ = getOrDeclare<std::vector<std::string>>(*this, "joint_model.command_topics", default_joint_topics);
    auto reorder_param = getOrDeclare<std::vector<int64_t>>(*this, "joint_model.reorder_indices", default_reorder);
    auto default_positions_param = getOrDeclare<std::vector<double>>(*this, "joint_model.default_positions", default_joint_positions);

    if (joint_names_.size() != kNumJoints || joint_topics_.size() != kNumJoints ||
        reorder_param.size() != kNumJoints || default_positions_param.size() != kNumJoints) {
        throw std::runtime_error("Joint configuration parameter length mismatch with NUM_JOINTS");
    }

    reorder_indices_.assign(reorder_param.begin(), reorder_param.end());

    environment_profile_ = getOrDeclare<std::string>(*this, "environment.profile", "default");

    std::vector<double> base_position_default =
        getOrDeclare<std::vector<double>>(*this, "environment.base_position", std::vector<double>{0.0, 0.0, 0.0});
    std::vector<double> base_orientation_default =
        getOrDeclare<std::vector<double>>(*this, "environment.base_orientation_rpy", std::vector<double>{0.0, 0.0, 0.0});

    if (base_position_default.size() != 3 || base_orientation_default.size() != 3) {
        throw std::runtime_error("Environment base pose parameters must have exactly three elements");
    }

    std::vector<double> joint_position_override = default_positions_param;
    const std::string env_prefix = "environment.profiles." + environment_profile_;

    if (this->has_parameter(env_prefix + ".default_joint_positions")) {
        auto override = this->get_parameter(env_prefix + ".default_joint_positions").as_double_array();
        if (override.size() != kNumJoints) {
            throw std::runtime_error("Environment profile default_joint_positions size mismatch");
        }
        joint_position_override.assign(override.begin(), override.end());
    }

    std::vector<double> base_position_override = base_position_default;
    if (this->has_parameter(env_prefix + ".base_position")) {
        auto override = this->get_parameter(env_prefix + ".base_position").as_double_array();
        if (override.size() != 3) {
            throw std::runtime_error("Environment profile base_position size must be 3");
        }
        base_position_override.assign(override.begin(), override.end());
    }

    std::vector<double> base_orientation_override = base_orientation_default;
    if (this->has_parameter(env_prefix + ".base_orientation_rpy")) {
        auto override = this->get_parameter(env_prefix + ".base_orientation_rpy").as_double_array();
        if (override.size() != 3) {
            throw std::runtime_error("Environment profile base_orientation_rpy size must be 3");
        }
        base_orientation_override.assign(override.begin(), override.end());
    }

    environment_config_.default_joint_positions = joint_position_override;
    environment_config_.base_position_xyz = base_position_override;
    environment_config_.base_orientation_rpy = base_orientation_override;

    non_foot_joint_scale_ = getOrDeclare<double>(*this, "joint_model.scales.non_foot", 0.5);
    foot_joint_scale_ = getOrDeclare<double>(*this, "joint_model.scales.foot", 5.0);
    publish_joint_array_ = getOrDeclare<bool>(*this, "joint_model.publish_joint_array", true);
}

void B2WControllers::resolvePolicyPath() {
    if (!policy_override_path_.empty()) {
        policy_path_ = std::filesystem::path(policy_override_path_);
    } else {
        std::string package_share;
        try {
            package_share = ament_index_cpp::get_package_share_directory(policy_package_);
        } catch (const std::exception &e) {
            std::ostringstream oss;
            oss << "Unable to find package '" << policy_package_ << "' for policy lookup: " << e.what();
            throw std::runtime_error(oss.str());
        }
        policy_path_ = std::filesystem::path(package_share) / policy_relative_path_;
    }

    if (!std::filesystem::exists(policy_path_)) {
        std::ostringstream oss;
        oss << "Policy file not found: " << policy_path_.string();
        throw std::runtime_error(oss.str());
    }
}

void B2WControllers::initializeJointNamesAndTopics() {
    if (joint_names_.size() != joint_topics_.size()) {
        throw std::runtime_error("joint_names_ and joint_topics_ size mismatch");
    }

    for (size_t i = 0; i < joint_names_.size(); ++i) {
        const auto &name = joint_names_[i];
        const auto &topic = joint_topics_[i];
        joint_pubs_[name] = this->create_publisher<std_msgs::msg::Float64>(topic, rclcpp::QoS(10));
        joint_commands_[name] = environment_config_.default_joint_positions[i];
    }

    joint_command_buffer_ = environment_config_.default_joint_positions;
}

void B2WControllers::setupSubscribers() {
    odometry_sub_ = this->create_subscription<nav_msgs::msg::Odometry>(
        odometry_topic_, rclcpp::QoS(10),
        std::bind(&B2WControllers::odometryCallback, this, std::placeholders::_1));

    velocity_sub_ = this->create_subscription<geometry_msgs::msg::Twist>(
        velocity_topic_, rclcpp::QoS(10),
        std::bind(&B2WControllers::velocityCallback, this, std::placeholders::_1));

    joint_state_sub_ = this->create_subscription<sensor_msgs::msg::JointState>(
        joint_state_topic_, rclcpp::QoS(50),
        std::bind(&B2WControllers::jointStateCallback, this, std::placeholders::_1));
}

void B2WControllers::setupPublishers() {
    action_pub_ = this->create_publisher<std_msgs::msg::Float64MultiArray>("/joint_commands", 10);
    network_input_debug_pub_ = this->create_publisher<std_msgs::msg::Float64MultiArray>("/network_input_debug", 10);
}

void B2WControllers::setupTimers() {
    inference_group_ = this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
    pub_group_ = this->create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);

    timer_ = this->create_wall_timer(
        kInferencePeriod,
        std::bind(&B2WControllers::inference, this),
        inference_group_);

    timer_pub_ = this->create_wall_timer(
        kPublishPeriod,
        std::bind(&B2WControllers::publishJointCommands, this),
        pub_group_);
}

void B2WControllers::odometryCallback(const nav_msgs::msg::Odometry::SharedPtr msg) {
    {
        std::lock_guard<std::mutex> lock(odometry_mutex_);
        base_lin_vel_ = msg->twist.twist.linear;
        base_ang_vel_ = msg->twist.twist.angular;

        Eigen::Quaterniond quat(
            msg->pose.pose.orientation.w,
            msg->pose.pose.orientation.x,
            msg->pose.pose.orientation.y,
            msg->pose.pose.orientation.z);

        rotation_matrix_ = quat.toRotationMatrix();
    }

    if (!odometry_received_) {
        odometry_received_ = true;
        RCLCPP_INFO(this->get_logger(), "Odometry data received, starting inference.");
    }

    processOdometry();
}

void B2WControllers::velocityCallback(const geometry_msgs::msg::Twist::SharedPtr msg) {
    std::lock_guard<std::mutex> lock(odometry_mutex_);
    cmd_vel_ = *msg;
}

void B2WControllers::jointStateCallback(const sensor_msgs::msg::JointState::SharedPtr msg) {
    if (msg->position.size() < kNumJoints || msg->velocity.size() < kNumJoints) {
        RCLCPP_WARN_THROTTLE(this->get_logger(), *this->get_clock(), 2000,
                             "Received joint state with insufficient data");
        return;
    }

    {
        std::lock_guard<std::mutex> lock(joint_state_mutex_);
        for (int i = 0; i < kNumJoints; ++i) {
            int src_index = reorder_indices_[i];
            if (src_index < 0 || src_index >= static_cast<int>(msg->position.size()) ||
                src_index >= static_cast<int>(msg->velocity.size())) {
            RCLCPP_ERROR_THROTTLE(this->get_logger(), *this->get_clock(), 5000,
                                  "Reorder index %d out of range", src_index);
            return;
        }
            joint_positions_[i] = msg->position[src_index];
            joint_velocities_[i] = msg->velocity[src_index];
    }
    }
}

void B2WControllers::processOdometry() {
    if (!odometry_received_) {
        return;
    }

    Eigen::Vector3d gravity(0, 0, -1.0);
    {
        std::lock_guard<std::mutex> lock(odometry_mutex_);
        projected_gravity_ = rotation_matrix_.transpose() * gravity;
    }
}

void B2WControllers::inference() {
    if (!odometry_received_) {
        if (!odometry_warned_) {
            RCLCPP_WARN(this->get_logger(), "No odometry data received yet.");
            odometry_warned_ = true;
        }
        return;
    }

    if (!session_) {
        RCLCPP_ERROR_THROTTLE(this->get_logger(), *this->get_clock(), 2000, "ONNX session is not initialized");
        return;
    }

    geometry_msgs::msg::Vector3 base_lin_vel_local;
    geometry_msgs::msg::Vector3 base_ang_vel_local;
    Eigen::Vector3d projected_gravity_local;
    geometry_msgs::msg::Twist cmd_vel_local;

    {
        std::lock_guard<std::mutex> lock(odometry_mutex_);
        base_lin_vel_local = base_lin_vel_;
        base_ang_vel_local = base_ang_vel_;
        projected_gravity_local = projected_gravity_;
        cmd_vel_local = cmd_vel_;
    }

    Eigen::VectorXd joint_positions_local;
    Eigen::VectorXd joint_velocities_local;
    {
        std::lock_guard<std::mutex> lock(joint_state_mutex_);
        joint_positions_local = joint_positions_;
        joint_velocities_local = joint_velocities_;
    }

    input_buffer_[0] = base_lin_vel_local.x;
    input_buffer_[1] = base_lin_vel_local.y;
    input_buffer_[2] = base_lin_vel_local.z;

    input_buffer_[3] = base_ang_vel_local.x;
    input_buffer_[4] = base_ang_vel_local.y;
    input_buffer_[5] = base_ang_vel_local.z;

    input_buffer_[6] = projected_gravity_local.x();
    input_buffer_[7] = projected_gravity_local.y();
    input_buffer_[8] = projected_gravity_local.z();

    input_buffer_[9] = cmd_vel_local.linear.x;
    input_buffer_[10] = cmd_vel_local.linear.y;
    input_buffer_[11] = cmd_vel_local.angular.z;

    for (Eigen::Index i = 0; i < joint_positions_local.size(); ++i) {
        double wrapped_position = joint_positions_local[i] - default_joint_positions_[i];
        wrapped_position = std::fmod(wrapped_position + 2 * M_PI, 4 * M_PI);
        if (wrapped_position < 0) {
            wrapped_position += 4 * M_PI;
        }
        wrapped_position -= 2 * M_PI;
        input_buffer_[12 + i] = static_cast<float>(wrapped_position);

        input_buffer_[28 + i] = static_cast<float>(joint_velocities_local[i]);
        input_buffer_[44 + i] = static_cast<float>(last_actions_[i]);
    }

    std::array<int64_t, 2> obs_shape = {1, kInputSize};
    std::array<int64_t, 3> hidden_shape = {1, 1, kHiddenSize};

    Ort::MemoryInfo memory_info = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);

    Ort::Value obs_tensor = Ort::Value::CreateTensor<float>(memory_info, input_buffer_.data(), input_buffer_.size(),
                                                            obs_shape.data(), obs_shape.size());

    Ort::Value h_in_tensor = Ort::Value::CreateTensor<float>(memory_info, h_in_data_.data(), h_in_data_.size(),
                                                             hidden_shape.data(), hidden_shape.size());

    Ort::Value c_in_tensor = Ort::Value::CreateTensor<float>(memory_info, c_in_data_.data(), c_in_data_.size(),
                                                             hidden_shape.data(), hidden_shape.size());

    std::vector<Ort::Value> input_tensors;
    input_tensors.reserve(3);
    input_tensors.push_back(std::move(obs_tensor));
    input_tensors.push_back(std::move(h_in_tensor));
    input_tensors.push_back(std::move(c_in_tensor));

    auto inference_start = std::chrono::steady_clock::now();

    try {
        auto output_tensors = session_->Run(Ort::RunOptions{nullptr}, input_node_names_.data(),
                                            input_tensors.data(), input_tensors.size(),
                                            output_node_names_.data(), output_node_names_.size());

        auto *actions_data = output_tensors[0].GetTensorMutableData<float>();
        auto *h_out_data = output_tensors[1].GetTensorMutableData<float>();
        auto *c_out_data = output_tensors[2].GetTensorMutableData<float>();

        std::copy(h_out_data, h_out_data + h_in_data_.size(), h_in_data_.begin());
        std::copy(c_out_data, c_out_data + c_in_data_.size(), c_in_data_.begin());

        Eigen::Map<Eigen::VectorXf> actions_map(actions_data, kNumJoints);
        last_actions_ = actions_map.cast<double>();
    } catch (const Ort::Exception &e) {
        RCLCPP_ERROR(this->get_logger(), "ONNX Runtime error: %s", e.what());
        return;
    }

    auto inference_end = std::chrono::steady_clock::now();
    const double inference_ms = std::chrono::duration<double, std::milli>(inference_end - inference_start).count();
    RCLCPP_DEBUG_THROTTLE(this->get_logger(), *this->get_clock(), 2000,
                          "Inference loop completed in %.3f ms", inference_ms);

    processActions();
    publishDebugData();
}

void B2WControllers::processActions() {
    reordered_actions_ = last_actions_;
    reordered_actions_.segment(0, 12) *= non_foot_joint_scale_;
    reordered_actions_.segment(12, 4) *= foot_joint_scale_;
    reordered_actions_ = reordered_actions_ + default_joint_positions_;

    std::lock_guard<std::mutex> lock(command_mutex_);
    for (size_t i = 0; i < joint_names_.size(); ++i) {
        joint_commands_[joint_names_[i]] = reordered_actions_[i];
        joint_command_buffer_[i] = reordered_actions_[i];
    }
}

void B2WControllers::publishDebugData() {
    if (network_input_debug_pub_->get_subscription_count() == 0 &&
        network_input_debug_pub_->get_intra_process_subscription_count() == 0) {
        return;
    }

    std_msgs::msg::Float64MultiArray debug_msg;
    debug_msg.data.reserve(input_buffer_.size());
    for (float value : input_buffer_) {
        debug_msg.data.push_back(static_cast<double>(value));
    }
    network_input_debug_pub_->publish(debug_msg);
}

void B2WControllers::publishJointCommands() {
    std::vector<double> joint_snapshot;
    {
        std::lock_guard<std::mutex> lock(command_mutex_);
        joint_snapshot = joint_command_buffer_;
    }

    for (size_t i = 0; i < joint_names_.size(); ++i) {
        std_msgs::msg::Float64 msg;
        msg.data = joint_snapshot[i];
        joint_pubs_[joint_names_[i]]->publish(msg);
    }

    if (publish_joint_array_ &&
        (action_pub_->get_subscription_count() > 0 ||
         action_pub_->get_intra_process_subscription_count() > 0)) {
        std_msgs::msg::Float64MultiArray aggregate_msg;
        aggregate_msg.data.assign(joint_snapshot.begin(), joint_snapshot.end());
        action_pub_->publish(aggregate_msg);
    }
}

int main(int argc, char **argv) {
    try {
        rclcpp::init(argc, argv);
        auto options = rclcpp::NodeOptions().automatically_declare_parameters_from_overrides(true);
        auto node = std::make_shared<B2WControllers>(options);

        rclcpp::executors::MultiThreadedExecutor exec(rclcpp::ExecutorOptions(), 2);
        exec.add_node(node);
        exec.spin();
        rclcpp::shutdown();
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "Fatal error: " << e.what() << std::endl;
        return 1;
    }
}
