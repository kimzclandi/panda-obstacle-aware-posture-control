# Learning Obstacle-Aware Posture Control for a Redundant Robotic Arm

NUS ME5418 Group 44。当前交付是 **阶段 1 的可复现闭环**：Panda 模型核验、解析位置跟踪、全臂/手部碰撞诊断、物理电机执行、命令重放与风险测试。势场调优、动态障碍场景集、Gymnasium 项目环境、PPO 训练、正式测试、最终报告与视频尚未完成。安装了 RL 库不代表已经训练。

## 范围与成功定义

固定基座 Panda，控制七个臂关节，手指保持每个 0.02 m；短而平滑的三维直线位置轨迹，未来扩展为一个已知静态球障碍物。策略不能改变路径或参考时钟。不控制末端朝向，不做视觉、抓取、实机或 ROS。

完整轨迹成功要求：在初始态和每个物理步后，位置误差始终不超过容差、无禁止碰撞、无关节限位违反。错误锁存，最后回到路径不能消除先前失败。碰撞/限位/数值失效可提前结束，失败回合保留分母。离散检查不能证明步间连续安全。

详见 [项目规格](docs/project_spec.md)、[课程提交要求](docs/course_requirements.md)、[当前证据和下一步](docs/progress.md)、[学习笔记](docs/learning_notes.md)。用户确认截止为 **2026-11-20 23:59**；当前用户独自推进，老师允许完整 AI 辅助。

## 安装与复跑

在本目录执行。项目使用 **CPython 3.11.17**；本机 3.12 对 PyBullet 3.2.7 没有适用的预编译 wheel。安装脚本仅创建本项目的 `.bootstrap/`、`.python/`、`.venv/`，不替换系统 Python 或其他项目环境。

```bash
bash scripts/bootstrap.sh
```

精确版本见 `requirements.lock.txt`。Torch 使用 CPU wheel；电脑 GPU 驱动可用与 CPU wheel 的 `torch.cuda.is_available() == False` 不矛盾。本机系统注入了 ROS Python 3.12 的 `PYTHONPATH`，因此命令明确移除它；项目不依赖 ROS。

```bash
# 包含关键测试、Jacobian、完整跟踪、命令重放、半步长检查和预期失败检查
# 每次生成独立 experiments/gate_<UTC>/，不会覆盖旧结果
 env -u PYTHONPATH .venv/bin/python scripts/validate_stage1.py

# 单独跟踪：CPU + PyBullet DIRECT
 env -u PYTHONPATH .venv/bin/python -m panda_posture.evaluate --diagnostics

# 关键测试
 bash scripts/run_tests.sh -q

# 当前机器环境、依赖与 GPU 记录
 env -u PYTHONPATH .venv/bin/python scripts/check_environment.py
```

将控制台输出中的实际 run 目录填入下面命令，可在新仿真中重放同一组速度电机目标。必须使用与原始 run 相同的配置；失败或不完整轨迹会被拒绝作为 witness。

```bash
 env -u PYTHONPATH .venv/bin/python -m panda_posture.evaluate \
   --replay experiments/<actual_run_id>
```

可选 `--gui` 打开 PyBullet GUI；当前只验证了 DIRECT 和 TinyRenderer 静态帧，未验证 GUI。本轮没有导出演示视频。运行采用仿真时钟、尽快执行，GUI 播放速度不是参考轨迹时长的证据。

## 核心实现

- `src/panda_posture/robot.py`：读 joint/link 名字与自由度映射，固定基座，七关节速度电机与力矩约束，手指位置伺服；显式检查 45 个自碰撞对，排除 10 对相邻/固定结构。球障碍几何查询覆盖基座、臂、手掌和手指。
- `control.py`：世界坐标位置主任务，quintic 时间规律直线，阻尼最小二乘主任务 + SVD 正交零空间次级项，统一限幅接口。
- `evaluate.py`：共享物理 rollout、逐步失败锁存、时序记录、重放和图表。
- `diagnostics.py`：五个姿态、两种步长的有限差分；非零次级命令的独立投影检查。
- `metrics.py`：成功语义和不丢失失败回合的汇总。
- `artifacts.py`：每次实验配置、源码快照、源码 hash、Git 状态、Python 和实际依赖。
- `tests/test_core.py`：针对 Jacobian、碰撞、限位、动作、成功判定、执行接口的风险测试。
- `configs/`、`scripts/`、`docs/`、`experiments/`：配置、复跑入口、长期上下文、不可覆盖实验。

`q` 为 `(7,)` rad，`x` 为世界系 `(3,)` m，`J` 为 `(3,7)` m/rad，次级动作 `(7,)` 归一化至 [-1,1] 后缩放为 rad/s。工具点是 `panda_grasptarget` link 原点；模型完整 Jacobian 有 9 列，按可动 DOF 映射提取臂关节列。

主任务 `q_dot_primary = J_dls @ (v_ref + Kp*(x_ref-x))`；次级 `N @ u_secondary`，其中 `N` 由 SVD 的数值零空间构造。阻尼逆的 `I-J_dls@J` 一般不是严格零空间投影。任何投影都不保证安全；裁剪、离散化、电机响应和奇异位形仍需测量。

正式 rollout **没有用 resetJointState 推进**。状态重置只用于初始状态和离线诊断。无障碍命令重放是阶段 1 的动态证据，不是阶段 2 障碍场景集已建立的证明。

## 输出含义与测量边界

每个 `experiments/<UTC>_<kind>/` 保存 `config.json`、`provenance.json`、`source_snapshot.tar.gz`、`model.json`、`summary.json`、`trajectory.npz`、`tracking.png`、`final_frame.png`；带 diagnostics 时另有 `jacobian_check.json`。分析不要覆盖这些目录。

`trajectory.npz` 的状态数组有 N+1 行（包含 t=0），命令数组 N 行，命令 k 执行于状态 k 到 k+1。记录位置、速度、实际电机力矩、参考点、误差、手指、几何净空、原始/主/次/投影/限幅命令、饱和、投影泄漏、裁剪扰动、奇异值与时间。上一“执行命令”指实际提交给电机的限幅目标，不能与测得速度混为一谈。

当前开发配置：240 Hz，4 s，位移 (0.060, 0.045, 0.025) m，位置容差 0.020 m；碰撞距离 ≤ +1e-5 m 视作失败（含保守近接触带）；关节上下界来自加载的 URDF，额外数值容差 1e-4 rad。查询距离上限 2 m；无障碍净空为 null。手指保持不是刚性焊死，要看实际漂移。

连续指标按已执行前缀报告并明确命名，不能用早失败回合的低 RMSE 宣称更好。未来跨控制器连续比较只对共同完成场景计算并报告样本数。当前单一 development 场景不构成泛化成功率或 RL 优越证据。

决策计时包含状态/参考、碰撞/限位、日志准备、Jacobian 与控制；步进计时包含电机命令和物理推进；rollout 墙钟包含循环日志，不含加载、渲染和写盘。这里没有网络推理，也不是 PPO 训练吞吐。

## 阶段门与后续结构

1. 模型/跟踪：以 `validate_stage1.py` 和人工审查作为当前验收证据。
2. 球障碍 + 公平势场：完整几何距离/梯度、限位次级项、共享评估；多种 witness 生成候选且每个接受场景物理重放，记录拒绝原因与筛选偏差；搜索失败标为尚未验证可行。
3. Gymnasium/PPO：明确特征/归一化和终止语义，环境检查，短训练、保存/加载、独立评估和吞吐估计后才扩大。有限轨迹终点属于任务终止；外部预算/时间限制属于截断。
4. 冻结评估/交付：仅 validation 选势场参数与 checkpoint，test 不更新统计；目标 3 个独立训练 seed × 至少 100 个相同固定场景；保留失败和条件指标，最后制作个人报告、视频及答辩材料。资源不足如实报告缩减范围。

阶段 2/3 的代码会围绕已验证的共享接口加入，不用空壳训练命令冒充可用功能。最先解决场景难度与 witness 偏差，随后测实际 PPO 成本。当前没有启动正式训练。

复用代码、模型资产与许可证见 [attribution.md](docs/attribution.md) 和 `docs/third_party/`。AI 辅助允许使用；“至少 50% 原创”的具体计量口径未确认，不用代码行数宣称达标。
