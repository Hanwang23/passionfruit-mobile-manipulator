#!/usr/bin/python3

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    RegisterEventHandler,
    Shutdown,
)
from launch.conditions import UnlessCondition
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
import xacro
import yaml


def start_after_success(event, label, *actions):
    if event.returncode:
        return [Shutdown(reason=f"{label} exited with code {event.returncode}")]
    return list(actions)


def generate_launch_description():
    gazebo_path = Path(get_package_share_directory("gazebo_ros"))
    simulation_path = Path(get_package_share_directory("elfin3_ros2_gazebo"))
    moveit_path = Path(get_package_share_directory("elfin3_ros2_moveit2"))
    config_path = moveit_path / "config"
    sim_time = {"use_sim_time": LaunchConfiguration("use_sim_time")}

    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(gazebo_path / "launch" / "gazebo.launch.py")),
        launch_arguments={
            "world": str(simulation_path / "worlds" / "elfin3.world"),
            "server_required": "true",
        }.items(),
    )
    urdf = xacro.process_file(
        str(simulation_path / "urdf" / "elfin3.urdf.xacro"),
        mappings={"use_fake_hardware": "false", "use_real_hardware": "false"},
    )
    robot_description = {"robot_description": urdf.toxml()}
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        output="screen",
        parameters=[robot_description, sim_time],
    )
    spawn_entity = Node(
        package="gazebo_ros",
        executable="spawn_entity.py",
        arguments=["-topic", "robot_description", "-entity", "elfin3", "-z", "0.1"],
        output="screen",
    )
    controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "elfin_arm_controller",
            "--controller-manager",
            "/controller_manager",
            "--controller-manager-timeout",
            "30",
        ],
        output="screen",
    )

    robot_description_semantic = {
        "robot_description_semantic": (config_path / "elfin3.srdf").read_text(encoding="utf-8")
    }
    robot_description_kinematics = {
        "robot_description_kinematics": yaml.safe_load(
            (config_path / "kinematics.yaml").read_text(encoding="utf-8")
        )
    }
    ompl = yaml.safe_load((config_path / "ompl_planning.yaml").read_text(encoding="utf-8"))
    ompl.update(
        {
            "planning_plugin": "ompl_interface/OMPLPlanner",
            "request_adapters": " ".join(
                (
                    "default_planner_request_adapters/AddTimeOptimalParameterization",
                    "default_planner_request_adapters/FixWorkspaceBounds",
                    "default_planner_request_adapters/FixStartStateBounds",
                    "default_planner_request_adapters/FixStartStateCollision",
                    "default_planner_request_adapters/FixStartStatePathConstraints",
                )
            ),
            "start_state_max_bounds_error": 0.1,
        }
    )
    planning = {
        "planning_pipelines": ["ompl"],
        "default_planning_pipeline": "ompl",
        "ompl": ompl,
    }
    controller_config = yaml.safe_load(
        (config_path / "elfin_controllers.yaml").read_text(encoding="utf-8")
    )
    moveit_parameters = [
        robot_description,
        robot_description_semantic,
        robot_description_kinematics,
        planning,
        sim_time,
    ]
    move_group = Node(
        package="moveit_ros_move_group",
        executable="move_group",
        output="screen",
        parameters=[
            *moveit_parameters,
            {
                "moveit_simple_controller_manager": controller_config,
                "moveit_controller_manager": controller_config["moveit_controller_manager"],
                "moveit_manage_controllers": True,
                "trajectory_execution": controller_config["trajectory_execution"],
                "publish_planning_scene": True,
                "publish_geometry_updates": True,
                "publish_state_updates": True,
                "publish_transforms_updates": True,
            },
        ],
    )
    rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="rviz2",
        output="log",
        arguments=["-d", str(moveit_path / "launch" / "elfin3_moveit2.rviz")],
        parameters=moveit_parameters,
        condition=UnlessCondition(LaunchConfiguration("rviz_file")),
    )
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "rviz_file", default_value="false", description="Set true to skip RViz."
            ),
            DeclareLaunchArgument("use_sim_time", default_value="true"),
            RegisterEventHandler(
                OnProcessExit(
                    target_action=spawn_entity,
                    on_exit=lambda event, _: start_after_success(
                        event, "E03 spawn", controller_spawner
                    ),
                )
            ),
            RegisterEventHandler(
                OnProcessExit(
                    target_action=controller_spawner,
                    on_exit=lambda event, _: start_after_success(
                        event, "E03 controller spawner", move_group, rviz
                    ),
                )
            ),
            gazebo,
            robot_state_publisher,
            spawn_entity,
        ]
    )
