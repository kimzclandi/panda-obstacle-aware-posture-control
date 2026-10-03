# 环境事实与选择依据

2026-10-04 首次检查：原工作目录 `/home/linjun/Documents/Codex/2026-10-04/nus-me5418-machine-learning-in-robotics` 只有空的 work/outputs 目录，没有 Git 仓库、AGENTS.md、代码或课程材料；检查到的祖先目录也没有 AGENTS.md。没有既有分支或未提交修改可覆盖。proposal 在用户明确给出的 `/home/linjun/桌面/Group44_Proposal.pdf`，复制到本项目 docs/；未猜测 macOS 路径。后续两张课程截图另存 docs/course_materials/。

当前项目单独初始化在 `outputs/panda-posture/`，本地 Git main 分支，无远端。AGENTS.md 是本轮新建的工作约定，不能当成原有课程规则。

| 检查 | 实测事实 |
|---|---|
| Linux | Ubuntu 24.04.4 LTS, x86_64 |
| CPU | AMD Ryzen 7 5800H，8 核 / 16 逻辑线程 |
| 内存 | 约 15 GiB；首次可用约 11 GiB |
| 磁盘 | 所在卷约 839 GiB 可用（首次检查） |
| 系统 Python | 3.12.3，系统 pip 24.0 |
| 已有环境 | 当前未激活 VIRTUAL_ENV/CONDA_PREFIX，项目无已有虚拟环境；未对用户整盘环境做穷举 |
| GPU | NVIDIA GeForce RTX 3060 Laptop GPU，6 GiB，驱动 595.84；nvidia-smi 可用 |
| 显示 | DISPLAY=:1；GUI 未验证，DIRECT/TinyRenderer 已实际使用 |
| 项目 Python | 3.11.17，独立 .python + .venv |
| RL 库 | Torch 2.14.1+cpu、SB3 2.9.0、Gymnasium 1.3.0 导入成功；尚无项目 PPO 训练 |

PyBullet 3.2.7 的 Python3.12 binary-only 安装失败，返回 no matching distribution；改用 Python3.11 wheel 后加载成功。NumPy2.4.6、SciPy1.17.1、Matplotlib3.11.2 与完整依赖保存在 requirements.lock.txt；这些是实装版本而非最初设想。

系统预设 `PYTHONPATH=/opt/ros/jazzy/lib/python3.12/site-packages` 会穿透 venv。初次普通 pytest 在收集前被 ROS launch_testing 插件干扰，缺少 yaml；不是本项目测试断言失败。复跑使用 `env -u PYTHONPATH`，测试再禁用外部插件自动加载。最终 provenance 仅枚举本 venv 的 packages。早期实验不覆盖，仍保留当时原始快照。

选择 CPU + DIRECT 是减少变量的工程决定。CPU Torch wheel 的 CUDA 不可用是安装选择，不是驱动故障。小型 MLP PPO 官方也推荐以 CPU 为起点，但本项目的训练选择仍须以后续 pilot wall time 为依据：[SB3 PPO 文档](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html)。PyBullet 的 CPU 步进不会因为安装 CUDA 自动变成 GPU 仿真。

首个完整 960-step tracker rollout 实测约0.85秒、1131 physics steps/s（含几何检查、控制、Python日志；不含加载渲染写盘）。这是单场景仿真吞吐，不是 PPO 的训练吞吐。按同样成本粗算100万步约15分钟仅可用于量级判断，尚未包含障碍几何增加、episode reset、网络训练和验证；不能据此批准数小时正式训练。最终 gate 的当次实测数值以其 summary 为准。

运行 `env -u PYTHONPATH .venv/bin/python scripts/check_environment.py` 会生成独立环境 JSON，保存系统命令结果、时间与本地版本，不导出任意环境变量或凭据。
