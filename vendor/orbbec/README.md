# Orbbec Gemini 336L V1.0

`Gemini_336L_CAD_Files.zip` 是奥比中光官网下载的原始压缩包，含 2024-05-17 版 STEP 装配及 DWG、PDF 工程图。`Gemini_336L_V1.0_drawing.pdf` 是包内 PDF 的原件副本。[奥比中光 CAD 下载页](https://doc.orbbec.com/documentation/Orbbec%20Gemini%20330%20Series%20Documentation/Download%20CAD%20Files%20%28Gemini%20330%20Series%29)

| 原始文件 | SHA-256 |
| --- | --- |
| `Gemini_336L_CAD_Files.zip` | `094235fa016ee6cade534277523370eb8a157c2e4bed4ba3b143398c39696677` |
| `[3D][STP]Gemini 336L Asm with FOV_20240517.stp` | `411c6ea8f9ef54bae1642a30e5591862d56f6a216803b5689ab85fdb88a4ec7b` |

`export_gemini_336l_meshes.py` 使用 Open CASCADE 将 STEP 的实体按原装配位置导出为毫米制 STL。视觉网格包含 STEP 实体装配，碰撞网格取原版外壳和前窗。导出脚本使用 `cadquery-ocp-novtk==8.0.1.1.0`，参数为 STEP 路径和 STL 输出目录。Gazebo 通过 URDF 的刚体变换和毫米至米的单位缩放安装网格。

`run_e03.sh mobile` 加载本地 CAD 网格，并从官方 `orbbec_description` 的 `gemini_335_L_336_L.urdf.xacro` 读取厂家名义 TF。相机沿底盘正前方平视，安装俯仰角为 0°，彩色光心距名义地面 1.46 m。后支架基于 95 mm 间距的双 M4 安装孔，仿真惯量根据厂家标称 135 g 和外廓计算。[Orbbec ROS 2 描述文件](https://github.com/orbbec/OrbbecSDK_ROS2/blob/v2-main/orbbec_description/urdf/gemini_335_L_336_L.urdf.xacro) · [厂家规格](https://www.orbbec.com/products/stereo-vision-camera/gemini-336l/)

`run_e03.sh gemini336l` 调用原版 `orbbec_camera/gemini_330_series.launch.py`，默认 ROS 域为 64。本项目用 ROS 2 Humble 的 `orbbec_camera`、`orbbec_camera_msgs` 和 `orbbec_description` 2.9.3 发行包验证。启动脚本支持系统 ROS 安装和工作区的 `.orbbec_ros2` 本地运行环境。官方 USB 权限规则位于驱动包的 `share/orbbec_camera/udev/99-obsensor-libusb.rules`。[Orbbec ROS 2 设备及启动文件表](https://github.com/orbbec/OrbbecSDK_ROS2/blob/v2-main/README.MD#launch-files)
