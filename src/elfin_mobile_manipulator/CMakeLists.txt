cmake_minimum_required(VERSION 3.8)
project(elfin_mobile_manipulator)

find_package(ament_cmake REQUIRED)

install(DIRECTORY config launch meshes urdf DESTINATION share/${PROJECT_NAME})
install(PROGRAMS scripts/swerve_drive scripts/keyboard_drive scripts/chassis_imu_raw DESTINATION lib/${PROJECT_NAME})
ament_package()
