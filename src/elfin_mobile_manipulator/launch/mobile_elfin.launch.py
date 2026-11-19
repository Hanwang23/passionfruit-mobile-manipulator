#!/usr/bin/python3

from pathlib import Path
from xml.etree import ElementTree

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, RegisterEventHandler, Shutdown
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import xacro
import yaml


ARM_CONFIG_PACKAGE = "elfin3_ros2_moveit2"
MOBILE_PACKAGE = "elfin_mobile_manipulator"
ROBOT_NAME = "ranger_mini_elfin3"


def read_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def after_success(event, label, *actions):
    if event.returncode:
        return [Shutdown(reason=f"{label} exited with code {event.returncode}")]
    return list(actions)


def add_gemini_frames(robot):
    description = Path(get_package_share_directory("orbbec_description"))
    camera_file = description / "urdf" / "gemini_335_L_336_L.urdf.xacro"
    camera = ElementTree.fromstring(xacro.process_file(str(camera_file)).toxml())
    # The 336L STEP assembly supplies the only physical camera link. Reuse
    # the vendor joints and add frame-only links for the sensor coordinates.
    for link in camera.findall("link"):
        if link.get("name") != "camera_link":
            ElementTree.SubElement(robot, "link", link.attrib)
    robot.extend(camera.findall("joint"))


def moveit_parameters(arm_config, base_config, robot_description):
    semantic = ElementTree.parse(arm_config / "elfin3.srdf").getroot()
    semantic.set("name", ROBOT_NAME)
    for controller in ("steering_controller", "wheel_controller"):
        for joint in base_config[controller]["ros__parameters"]["joints"]:
            ElementTree.SubElement(semantic, "passive_joint", {"name": joint})
    # Keep the mast and camera in collision checks against the moving arm.
    for first, second in (
        ("base_link", "elfin_base"),
        ("base_link", "gemini_336l_mast_link"),
        ("gemini_336l_mast_link", "camera_link"),
    ):
        ElementTree.SubElement(semantic, "disable_collisions", {
            "link1": first, "link2": second, "reason": "Adjacent",
        })

    ompl = read_yaml(arm_config / "ompl_planning.yaml")
    ompl.update({
        "planning_plugin": "ompl_interface/OMPLPlanner",
        "request_adapters": " ".join([
            "default_planner_request_adapters/AddTimeOptimalParameterization",
            "default_planner_request_adapters/FixWorkspaceBounds",
            "default_planner_request_adapters/FixStartStateBounds",
            "default_planner_request_adapters/FixStartStateCollision",
            "default_planner_request_adapters/FixStartStatePathConstraints",
        ]),
        "start_state_max_bounds_error": 0.1,
    })
    return {
        **robot_description,
        "robot_description_semantic": ElementTree.tostring(semantic, encoding="unicode"),
        "robot_description_kinematics": read_yaml(arm_config / "kinematics.yaml"),
        "planning_pipelines": ["ompl"],
        "default_planning_pipeline": "ompl",
        "ompl": ompl,
        "use_sim_time": True,
    }


def generate_launch_description():
    mobile = Path(get_package_share_directory(MOBILE_PACKAGE))
    arm_moveit = Path(get_package_share_directory(ARM_CONFIG_PACKAGE))
    arm_gazebo = Path(get_package_share_directory("elfin3_ros2_gazebo"))
    gazebo_share = Path(get_package_share_directory("gazebo_ros"))
    base_controller_file = mobile / "config" / "base_controllers.yaml"
    geometry = read_yaml(mobile / "config" / "base_geometry.yaml")

    urdf = xacro.process_file(
        str(mobile / "urdf" / "ranger_mini_elfin3.urdf.xacro"),
        mappings={
            "use_real_hardware": "false",
            "use_fake_hardware": "false",
            "mount_parent": "arm_mount_link",
            "additional_controller_config": str(base_controller_file),
        },
    )
    robot = ElementTree.fromstring(urdf.toxml())
    add_gemini_frames(robot)
    robot_description = {"robot_description": ElementTree.tostring(robot, encoding="unicode")}
    arm_config = arm_moveit / "config"
    shared_moveit = moveit_parameters(arm_config, read_yaml(base_controller_file), robot_description)
    arm_controllers = read_yaml(arm_config / "elfin_controllers.yaml")

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(gazebo_share / "launch" / "gazebo.launch.py")),
        launch_arguments={
            "world": str(arm_gazebo / "worlds" / "elfin3.world"),
            "server_required": "true",
        }.items(),
    )
    state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[robot_description, {"use_sim_time": True, "publish_frequency": 60.0}],
        output="screen",
    )
    imu_raw = Node(
        package=MOBILE_PACKAGE,
        executable="chassis_imu_raw",
        parameters=[{"use_sim_time": True}],
        output="screen",
    )
    spawn = Node(
        package="gazebo_ros",
        executable="spawn_entity.py",
        arguments=["-topic", "robot_description", "-entity", ROBOT_NAME, "-z", "0.005"],
        output="screen",
    )
    controllers = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "elfin_arm_controller", "steering_controller", "wheel_controller",
            "joint_state_broadcaster", "--controller-manager-timeout", "30",
        ],
        output="screen",
    )
    drive = Node(
        package=MOBILE_PACKAGE,
        executable="swerve_drive",
        parameters=[
            {"use_sim_time": True},
            {name: geometry[name] for name in ("wheelbase", "track", "wheel_radius")},
        ],
        output="screen",
        on_exit=[Shutdown(reason="Mobile chassis controller exited")],
    )
    move_group = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        parameters=[
            shared_moveit,
            {
                "moveit_simple_controller_manager": arm_controllers,
                "moveit_controller_manager": arm_controllers["moveit_controller_manager"],
                "moveit_manage_controllers": True,
                "trajectory_execution": arm_controllers["trajectory_execution"],
                "publish_robot_description_semantic": True,
                "publish_planning_scene": True,
                "publish_geometry_updates": True,
                "publish_state_updates": True,
                "publish_transforms_updates": True,
            },
        ],
        output="screen",
    )
    rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        arguments=[
            "-d", str(mobile / "config" / "mobile_elfin.rviz"),
            "-f", "odom", "-t", "Ranger Mini 3.0 + E03 + Gemini 336L",
        ],
        parameters=[shared_moveit],
        condition=IfCondition(LaunchConfiguration("rviz")),
        output="log",
    )
    return LaunchDescription([
        DeclareLaunchArgument("rviz", default_value="true"),
        RegisterEventHandler(OnProcessExit(
            target_action=spawn,
            on_exit=lambda event, _: after_success(event, "Mobile robot spawn", controllers),
        )),
        RegisterEventHandler(OnProcessExit(
            target_action=controllers,
            on_exit=lambda event, _: after_success(
                event, "Controller spawner", drive, move_group, rviz
            ),
        )),
        gazebo, state_publisher, imu_raw, spawn,
    ])
