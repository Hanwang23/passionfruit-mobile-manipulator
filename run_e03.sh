#!/usr/bin/env bash
set -eo pipefail

workspace="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
workspace_key="$(printf '%s' "$workspace" | sha256sum | cut -c1-12)"
cache_dir="$HOME/.cache/elfin_humble"
workspace_alias="$cache_dir/$workspace_key"
build_dir="$cache_dir/$workspace_key-build"

# Use ASCII paths for ROSIDL generation and the Gazebo launcher.
mkdir -p -- "$cache_dir"
if [[ ! -e "$workspace_alias" && ! -L "$workspace_alias" ]]; then
    ln -sT -- "$workspace" "$workspace_alias"
fi
if [[ "$(realpath -- "$workspace_alias")" != "$workspace" ]]; then
    printf 'Workspace link points to another directory: %s\n' "$workspace_alias" >&2
    exit 1
fi

# Use the ROS Humble underlay and its system Python in this process.
unset AMENT_PREFIX_PATH CMAKE_PREFIX_PATH COLCON_PREFIX_PATH LD_LIBRARY_PATH PYTHONPATH
export PATH=/usr/bin:/bin
export PYTHONNOUSERSITE=1
source /opt/ros/humble/setup.bash

case "${1:-}" in
    mobile|mobile-cli|gemini336l)
        orbbec_ros="$workspace_alias/.orbbec_ros2/opt/ros/humble"
        if [[ -d "$orbbec_ros/share/orbbec_description" ]]; then
            export AMENT_PREFIX_PATH="$orbbec_ros${AMENT_PREFIX_PATH:+:$AMENT_PREFIX_PATH}"
            export LD_LIBRARY_PATH="$orbbec_ros/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
            export PYTHONPATH="$orbbec_ros/local/lib/python3.10/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
        fi
        ;;
esac

if [[ "${1:-}" == gemini336l ]]; then
    shift
    export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-64}"
    exec ros2 launch orbbec_camera gemini_330_series.launch.py "$@"
fi

if [[ "${1:-}" == build ]]; then
    shift
    cd -- "$cache_dir"
    export MAKEFLAGS="${MAKEFLAGS:--j2}"
    exec colcon --log-base "$workspace_alias/log" build \
        --base-paths "$workspace_alias/src" \
        --build-base "$build_dir" \
        --install-base "$workspace_alias/install" \
        --parallel-workers 2 "$@" \
        --cmake-args -DBUILD_TESTING=OFF -DCMAKE_BUILD_TYPE=Release \
        -DPython3_EXECUTABLE=/usr/bin/python3
fi

if [[ ! -r "$workspace_alias/install/local_setup.bash" ]]; then
    printf 'Build the E03 workspace first with %s build.\n' "$0" >&2
    exit 1
fi
source "$workspace_alias/install/local_setup.bash"

classic="$workspace_alias/.gazebo_classic"
if [[ -x "$classic/usr/bin/gzserver" ]]; then
    classic_ros="$classic/opt/ros/humble"
    classic_lib="$classic/usr/lib/x86_64-linux-gnu"
    classic_plugins="$classic_lib/gazebo-11/plugins"
    classic_share="$classic/usr/share/gazebo-11"
    export PATH="$classic/usr/bin:$PATH"
    export LD_LIBRARY_PATH="$classic_lib:$classic_plugins:$classic/usr/lib:$classic_ros/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    export AMENT_PREFIX_PATH="$classic_ros${AMENT_PREFIX_PATH:+:$AMENT_PREFIX_PATH}"
    export PYTHONPATH="$classic_ros/local/lib/python3.10/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
    export GAZEBO_RESOURCE_PATH="$classic_share"
    export GAZEBO_MODEL_PATH="$classic_share/models"
    export GAZEBO_PLUGIN_PATH="$classic_plugins:$classic_ros/lib"
    export SDF_PATH="$classic/usr/share/sdformat9"
elif command -v gzserver >/dev/null && [[ -r /usr/share/gazebo/setup.sh ]]; then
    # Retain the launcher's own master port selection when it was unset.
    configured_master="${GAZEBO_MASTER_URI:-}"
    source /usr/share/gazebo/setup.sh
    if [[ -z "$configured_master" ]]; then
        unset GAZEBO_MASTER_URI
    fi
else
    printf 'Install Gazebo Classic and the ROS 2 Humble Gazebo packages.\n' >&2
    exit 1
fi
export GAZEBO_MODEL_DATABASE_URI=''

if [[ "${1:-}" == mobile || "${1:-}" == mobile-cli || "${1:-}" == teleop ]]; then
    mode="$1"
    shift
    export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-62}"
    export ROS_LOCALHOST_ONLY=1
    export GAZEBO_MASTER_URI="${GAZEBO_MASTER_URI:-http://127.0.0.1:11356}"
    # Gazebo Classic also discovers the scene through Ignition Transport.
    export IGN_PARTITION="${IGN_PARTITION:-elfin_mobile_${ROS_DOMAIN_ID}}"
    if [[ "$mode" == mobile-cli ]]; then
        if (( $# == 0 )); then
            printf 'Usage: %s mobile-cli COMMAND [ARG ...]\n' "$0" >&2
            exit 2
        fi
        exec "$@"
    fi
    if [[ "$mode" == teleop ]]; then
        exec ros2 run elfin_mobile_manipulator keyboard_drive "$@"
    fi
    exec ros2 launch elfin_mobile_manipulator mobile_elfin.launch.py "$@"
fi

exec ros2 launch elfin3_ros2_moveit2 elfin3.launch.py "$@"
