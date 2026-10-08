# Learning Obstacle-Aware Posture Control for a Redundant Robotic Arm

> **GitHub checkout 与完整复现包不同。** 本仓库保存源码、配置、文档、报告、视频与 Git 历史；`experiments/`、虚拟环境和冻结的安装元数据不随 Git 上传。运行三个已训练模型、核验 witness 或重跑固定 500 回合，请从 [v1.1.0 Release](https://github.com/kimzclandi/panda-obstacle-aware-posture-control/releases/tag/v1.1.0) 下载完整复现 ZIP，核对 `SHA256SUMS`，解压后按下方 Quick verification 建环境并自动核验搬迁路径。下文 `experiments/` 路径仅在完整 ZIP 内有效。
>
> The Git repository contains source code and presentation deliverables. **Pretrained checkpoints and the immutable experimental evidence are in the full Release ZIP.** A source-only clone can run the basic diagnostics/tests after bootstrap; frozen model validation requires the complete archive and the relocation procedure. The v1.1.0 full archive preserves the verified local revision byte-for-byte: its receipt records base commit `4b003c5` plus the then-uncommitted files, and its manifest hashes bind the actual contents. The release tag identifies the subsequent publication commit. Distribution documentation has changed; the frozen scientific inputs have not.

**核心工程和首轮冻结研究已完成；当前版本为 2026-10-09 技术交付修订（v1.1.0）。** 新增训练退化分析、十页英文报告、障碍物标注视频和自动搬迁验证入口。个人署名/真实反思与其他实际组员的独立报告仍待本人确认。本版本通过 GitHub 分发，未提交任何课程平台；旧 v1.0.0 Release 保留。

本次结论：相同 100 个测试场景，APF 成功 92 次，高于 PPO 的 80、81、65 次；没有支持 RL 超过 APF。三个 PPO seed 各训练 98,304 policy steps，全部 188 个 train/validation/test 场景具有物理 witness；不声称 PPO 已收敛。

## Start here

- [英文技术报告，10 页](deliverables/final_20261009/report_en_v2/final_report_en.pdf)：完整方法、结果、讨论与证据，已逐页视觉检查。
- [中文结果解读](deliverables/final_20261009/interpretation_zh.md)与[成功率图](deliverables/final_20261009/report_en_v2/figures/success.png)：先理解研究结论和限制。
- [52 秒演示视频](deliverables/final_20261009/videos/final_demo_en_v2.mp4)：方法、两例真实物理重放、全部五策略结果和限制。
- [失败分析](docs/failure_analysis.md)、[中文答辩准备](docs/viva_guide_zh.md)、[完整复现与解压搬迁流程](docs/reproduction.md)。

| 同一固定 test 集 | Tracker | 调优 APF | PPO 144 | PPO 145 | PPO 146 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 完整成功数 / 100 | 70 | **92** | 80 | 81 | 65 |

完整分层、配对区间、共同完成条件指标与 seed 波动见`experiments/20261003T201319.444915Z_paired_evaluation/analysis/summary.json`（机器可读分析；完整 ZIP 内）。视频六个 pane 的物理重放关节差全部为 0；新版影片共 1560 帧、30 fps，已完整解码并抽帧视觉检查。视频不替代这 500 回合批量证据。归档发布状态及哈希见 ZIP 旁的 receipt。

## 获取当前源码与附件

```bash
git clone https://github.com/kimzclandi/panda-obstacle-aware-posture-control.git
cd panda-obstacle-aware-posture-control
```

源码 clone 适合阅读实现和运行不依赖冻结模型的基础检查。直接体验训练好的模型，请下载下面的完整 ZIP。仅需要轻量环境/demo 时，可选下载同一 Release 的 `Panda_Gym_Code_Report.zip`，按其独立 README 运行；它不是完整模型复现包。

本轮验收：108 项关键测试通过；最终 ZIP 的 6,434 个清单文件已核验，实际解压到本机新目录并建立项目独立环境后，三个模型各完成 960 物理步，状态和命令与原验证逐位一致。详见 [解压复跑记录](https://github.com/kimzclandi/panda-obstacle-aware-posture-control/releases/download/v1.1.0/Panda_Final_Project_20261009.verification.json)。这是同一 Linux 主机上的验证，不宣称其他电脑或跨平台已验证。

## 新电脑上的最短验证流程 / Quick verification

从 [v1.1.0 Assets](https://github.com/kimzclandi/panda-obstacle-aware-posture-control/releases/tag/v1.1.0) 下载 **Panda_Final_Project_20261009.zip**（750,132,146 字节）及 `SHA256SUMS`。GitHub 自动生成的 **Source code (zip/tar.gz)** 不包含模型和实验数据。核对 SHA-256 后解压完整 ZIP，进入 `panda-posture/`，运行：

```bash
bash scripts/bootstrap.sh
env -u PYTHONPATH OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python scripts/quickstart.py
```

The first command creates a project-local Python 3.11.17 environment with all pinned dependencies. The second verifies the frozen evidence and runs the three selected models on the same fixed validation scene. It creates a new relocation manifest automatically when needed and prints its path. It does not retrain, change the original freeze, or select a model using test results. A successful run ends with `"passed": true`; each policy must complete 960 physics steps. This is a functionality check, not a replacement for the 500-episode research evaluation.

Linux CPU / DIRECT is the verified target. Installation needs package access (or an existing package cache); no display or GPU is required. GUI is optional. Cross-platform or different-hardware bitwise identity is not claimed.

[Final 交付核对](docs/final_delivery_checklist.md)与[英文口述稿](deliverables/final_20261009/oral_script_en.md)。

## 交互运行：亲自看机械臂

本机完整项目和环境已验证后，可以直接运行：

```bash
env -u PYTHONPATH OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python scripts/live_demo.py
```

点击 PyBullet 窗口后按 **SPACE** 开始，默认运行 PPO seed 144 在固定 validation 场景的四秒轨迹。开始前或结束后按 **1 / 2 / 3** 切换 tracker / 调优 APF / PPO；结束后 **R** 创建新回合，再按 SPACE；**Q / Esc** 关闭。运行中不能用这些控制暂停参考时钟。蓝线是参考路径，绿线是实际工具轨迹；场景很短，重点观察机械臂姿态与球障碍的关系。

这是调用原控制器和 `stepSimulation` 的实际仿真，界面只添加显示与墙钟节奏。每次运行单独写入 `experiments/*_live_gui_demo/`；中断不记为成功，GUI 耗时不能当作正式性能计时。`--autostart --exit-after-run` 可完成一次自动 GUI smoke 后退出；`--scenario study-4490-0017` 或 `study-4490-0069` 可查看报告中已有的例子，个例不代替批量评估。

交互入口已纳入当前源码和 v1.1.0 完整 ZIP。原 v1.0.0 ZIP 保持不变，因此旧版本用户需要更新文件。项目搬迁后，先运行 quickstart，再把其打印的 `freeze_for_other_commands` 路径通过 `--freeze` 传给 GUI。需要本地图形显示；无显示环境继续使用 DIRECT 验证。

## 范围与成功定义

固定基座 Franka Panda；控制七个臂关节，两个手指各保持 0.02 m；四秒 quintic 时间规律的三维短直线位置轨迹；一个已知静态球障碍物。策略只能输出次级姿态调整，不能改变参考路径、轨迹时间或暂停时钟。不做末端朝向控制、视觉、抓取、实机、ROS 或分布式训练。

完整成功要求：初始态和每个物理步后均满足位置误差容差、无禁止碰撞、无关节限位违反。超差永久锁存；后来恢复不能重新成功。碰撞、限位和数值失效终止任务；跟踪超差不暂停参考时钟。失败保留在分母；连续指标的共同完成场景比较另报条件样本数。240 Hz 离散检查不证明步间连续安全。

[项目规格](docs/project_spec.md)、[实验进度](docs/progress.md)、[决策记录](docs/decisions.md)、[学习笔记](docs/learning_notes.md)。

## 环境与基础验收

在本目录执行。独立 **CPython 3.11.17**、CPU PyTorch、PyBullet DIRECT；本机 Python 3.12 的 PyBullet 二进制安装探测失败，因此不覆盖系统 Python，采用项目独立解释器与 `.venv`。

```bash
bash scripts/bootstrap.sh
```

[requirements.lock.txt](requirements.lock.txt) 锁定 **35 个外部包**。Bootstrap 使用公开 PyPI 获取普通依赖、Torch CPU 专属 `find-links` 获取 CPU wheel，已在全新项目环境安装通过；自动保留原冻结的五个 `src/panda_posture.egg-info/` 文件并审计 editable 安装产生的变化。不要从交付包删除这些元数据。GPU 驱动存在不代表 PyBullet 或本 PPO 使用 CUDA；系统 ROS 的 `PYTHONPATH` 在运行时明确清除。

```bash
# 三个已训练模型的固定 validation 功能验收；不重训练、不改选模
 env -u PYTHONPATH .venv/bin/python scripts/quickstart.py

# 阶段 1 完整可复现验收；每次创建独立 gate_<UTC>，不覆盖旧结果
 env -u PYTHONPATH .venv/bin/python scripts/validate_stage1.py

# 无障碍跟踪与数值诊断
 env -u PYTHONPATH .venv/bin/python -m panda_posture.evaluate --diagnostics

# 当前全部关键风险测试
 bash scripts/run_tests.sh -q

# 环境、依赖、GPU 元数据
 env -u PYTHONPATH .venv/bin/python scripts/check_environment.py

# 重放原始阶段 1 motor targets
 env -u PYTHONPATH .venv/bin/python -m panda_posture.evaluate \
   --replay experiments/20261003T191423.707824Z_stage1_tracker
```

`experiments/gate_20261003T191419.044956Z/index.json`（阶段 1 验收索引；完整 ZIP 内）记录当时 32 项测试、完整跟踪、命令重放、半步长检查与预期碰撞失败。该单一无障碍开发轨迹最大位置误差约 0.0236 mm，物理重放关节差为零；这些结果不能替代球障碍成功率或证明 RL 优势。当前新增风险测试以最新测试运行证据为准，不能把历史的 32 项写成当前全部测试数量。

可选 `--gui` 接口保留；主要验证 DIRECT/TinyRenderer。原目录`experiments/20261003T201415.503267Z_delivery_validation/status.json`（交付验收；完整 ZIP 内）与`experiments/20261003T202857.594683Z_relocation_verification/summary.json`（独立搬迁验收；完整 ZIP 内）均通过：全新环境中三个模型在固定 validation 场景各完成 960 个物理步，保存/加载动作一致；搬迁前后物理状态和命令数组逐位一致，q/command 最大差均为 0。此证据限于本机 Linux 新目录/新环境，不保证不同硬件或操作系统逐位重现；计时数组不纳入一致性声明。

## 当前研究输入与状态

[study_protocol_v1.json](configs/study_protocol_v1.json) 在本研究数据生成、训练与 test 比较之前声明数量、种子、预算、baseline 网格与选模规则；[study_base.json](configs/study_base.json)保存共享物理配置。

| 输入或步骤 | 实际证据与当前状态 |
| --- | --- |
| Train 64 / validation 24 | `experiments/20261003T194210.629028Z_study_scenes/scenes.json`（固定场景清单；完整 ZIP 内）；每个 split 的 simple/tight 各半；`experiments/20261003T194210.629028Z_study_scenes/post_generation_audit.json`（完整审计；完整 ZIP 内） |
| Test 100 | `experiments/20261003T194217.720814Z_study_scenes/scenes.json`（独立 seed 4490 场景清单；完整 ZIP 内）；witness 完整性证据与模型/输入 `experiments/study_pretest_freeze.json`（pretest freeze；完整 ZIP 内） 已通过；未用于调参或训练 |
| APF validation 选择 | `experiments/20261003T195747.519524Z_potential_validation_tuning/selected.json`（selected.json；完整 ZIP 内）；12 组 × 24 回合，选中 23/24，simple 12/12、tight 11/12；这是选参结果 |
| PPO seed 144 | `experiments/20261003T195813.023303Z_ppo_study_seed144/training_summary.json`（训练证据；完整 ZIP 内）；98,304 步完成，选中 61,440 步模型；独立 validation 19/24 |
| PPO seed 145 | `experiments/20261003T195813.017181Z_ppo_study_seed145/training_summary.json`（训练证据；完整 ZIP 内）；98,304 步完成，选中 12,288 步模型；独立 validation 17/24 |
| PPO seed 146 | `experiments/20261003T195813.082516Z_ppo_study_seed146/training_summary.json`（训练证据；完整 ZIP 内）；98,304 步完成，选中 49,152 步模型；独立 validation 18/24 |
| 最终交付 | [study_index.json](study_index.json) 已完整填写 evaluation/report/demo；固定 500 回合与原始证据保留；本修订提供十页技术报告、52 秒视频和稳定性诊断；个人报告身份/反思待确认 |

APF 选中 `obstacle_gain=.0001`、`influence_distance=.08 m`、`self_gain=0`；其余固定参数和完整候选结果见 [potential_field.md](docs/potential_field.md)。关闭选中候选的自碰势场项并不关闭自碰检测。该有限 validation 网格是本项目的调参范围，不声称传统方法已达到全局最优。

三个训练进程在同一 CPU 上并发，每个 Torch/BLAS 线程数为 1。它们是三个独立 learner，各有自己的随机种子、模型和日志，不是分布式 PPO。每个 seed 的学习墙钟含 callback validation 分别为 808.387、780.717、807.257 秒；扣除该验证后的吞吐约 176–177 policy steps/s。并发实际墙钟约 14 分钟，不能把三段时间相加当作项目 elapsed time。未测量 CUDA 收益，不声称收敛；训练只读取 train/validation，固定 observation 归一化不从 test 更新统计。

## 可复现研究命令

以下前两条重新生成新的独立场景目录，仅用于复现生成方法。不要将新生成的清单混入当前已声明研究；后续命令使用上表的固定清单。每个接受场景都要通过相同时长、执行器限制和跟踪容差下的物理 witness 与命令重放；未找到 witness 只记为“尚未验证可行”。

```bash
env -u PYTHONPATH OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python \
  -m panda_posture.scenes --base configs/study_base.json --study \
  --train-count 64 --validation-count 24 --candidate-budget 800 \
  --seed 4410 --initial-clearance-floor 0.001

env -u PYTHONPATH OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python \
  -m panda_posture.scenes --base configs/study_base.json --study \
  --test-count 100 --candidate-budget 800 --seed 4490 --initial-clearance-floor 0.001
```

设置当前研究路径；这些变量只方便命令复跑，不是系统环境配置。

```bash
STUDY_TRAINVAL=experiments/20261003T194210.629028Z_study_scenes/scenes.json
STUDY_TEST=experiments/20261003T194217.720814Z_study_scenes/scenes.json
STUDY_APF=experiments/20261003T195747.519524Z_potential_validation_tuning/selected.json
STUDY_RUN144=experiments/20261003T195813.023303Z_ppo_study_seed144
STUDY_RUN145=experiments/20261003T195813.017181Z_ppo_study_seed145
STUDY_RUN146=experiments/20261003T195813.082516Z_ppo_study_seed146
```

Baseline 调参与训练的真实入口如下。重新执行会产生新的实验目录；训练代码要求 study 的数量、seed、步数和验证频率与协议一致。复现全研究时 seed 依次取 144、145、146；首次练习可运行另一个 8192 步 pilot，但不能冒充当前研究完成。

```bash
env -u PYTHONPATH OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python \
  -m panda_posture.batch tune --dataset "$STUDY_TRAINVAL"

env -u PYTHONPATH OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python \
  -m panda_posture.train --dataset "$STUDY_TRAINVAL" \
  --steps 98304 --seed 144 --eval-every 12288 \
  --study-protocol configs/study_protocol_v1.json
```

最简完整复评入口如下，始终创建新的评估/分析目录，不覆盖原结果；直接从冻结清单取数据、baseline 与三个模型，要求全部输入 hash 一致。它重评估既有模型，不重新训练。

```bash
env -u PYTHONPATH OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python \
  scripts/run_frozen_test.py --index study_index.json
```

下面保留组成流程的冻结与评估入口。每个 run 必须具备 `training_summary.json`、保存/加载检查、最终 optimizer update 后的 validation 及独立加载验证。`freeze_study.py` 审计这些记录及 witness，冻结配置、源码、数据和模型 hash；缺失或不一致时拒绝继续。`best_model.zip` 是完整训练流程最终选中的版本。原 `experiments/study_pretest_freeze.json` 已存在，因此下面的冻结复跑使用新的输出名；后面的评估也要使用同一个新清单。

```bash
env -u PYTHONPATH .venv/bin/python scripts/freeze_study.py \
  --trainval "$STUDY_TRAINVAL" --test "$STUDY_TEST" --potential "$STUDY_APF" \
  --model 144 "$STUDY_RUN144/best_model.zip" \
  --model 145 "$STUDY_RUN145/best_model.zip" \
  --model 146 "$STUDY_RUN146/best_model.zip" \
  --output experiments/study_pretest_freeze_reproduction.json

env -u PYTHONPATH OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python \
  -m panda_posture.batch evaluate --dataset "$STUDY_TEST" --split test \
  --potential-params "$STUDY_APF" --freeze experiments/study_pretest_freeze_reproduction.json \
  --model 144 "$STUDY_RUN144/best_model.zip" \
  --model 145 "$STUDY_RUN145/best_model.zip" \
  --model 146 "$STUDY_RUN146/best_model.zip"
```

Test 入口必须带 `--freeze` 并核验输入 hash。解压到新 Linux 路径后，依照[搬迁流程](docs/reproduction.md)先 bootstrap 新环境，再创建 relocated freeze 并运行 `validate_delivery.py --freeze <new_manifest>`；完整复评可用 `run_frozen_test.py --index study_index.json --freeze <new_manifest>`。保留原始证据与冻结文件，不能通过改 JSON 或路径迁移绕过 hash 校验。

将 batch 命令实际打印的目录赋给 `STUDY_EVAL`，再运行分析和视频；下列占位值必须替换成真实输出与场景 ID。分析要求完整策略 × 场景集合，拒绝不完整分母。视频不改变评估或选择模型。

```bash
STUDY_EVAL='experiments/<actual_paired_evaluation_directory>'
STUDY_SCENARIO='<actual_scene_id_from_this_evaluation>'

env -u PYTHONPATH .venv/bin/python -m panda_posture.analysis \
  --episodes "$STUDY_EVAL/episodes.json" --out "$STUDY_EVAL/analysis"

env -u PYTHONPATH .venv/bin/python scripts/render_comparison.py \
  --evaluation "$STUDY_EVAL" --scenario "$STUDY_SCENARIO" --ppo-seed 144 \
  --output "$STUDY_EVAL/videos/comparison.mp4"
```

`study_index.json` 的报告依赖已齐全：完整 500 回合及分析、冻结模型、两段已验证的原速物理 case clips。当前报告位置由 study_index.json 指定，10 页逐页视觉 QA 已通过。重建必须使用**不存在的新目录**，不会覆盖当前报告；新生成 PDF 仍需重新逐页检查。

```bash
env -u PYTHONPATH .venv/bin/python scripts/build_final_report.py \
  --index study_index.json --out deliverables/NEW_DIRECTORY
```

## 核心实现与控制契约

| 模块 | 作用 |
| --- | --- |
| `robot.py` / `diagnostics.py` | 按名称发现 joint/link/DOF；工具点与全臂材料点 Jacobian；速度电机与手指伺服；45 个检查自碰对、10 个有理由的排除对 |
| `control.py` / `task.py` | 同一解析主跟踪器、SVD 次级投影、统一动作/速度界；逐物理步状态采样、碰撞与失败锁存 |
| `secondary.py` | 最近几何点及距离梯度的全臂 APF、关节限位项；参数与诊断；不访问 witness |
| `scenes.py` | train/validation/test 场景生成、ID/物理 hash、三种 witness 候选、实际命令重放、接受/拒绝审计 |
| `env.py` / `train.py` | 55 维固定归一化 observation、有限时域 reward、terminated/truncated；PPO、validation 选模和独立保存/加载 |
| `evaluate.py` / `batch.py` | 共享物理 rollout、单场景重放、12 组 validation 调参、冻结检查后的配对评估 |
| `freeze.py` / `analysis.py` | 输入/证据/源码冻结；失败保留、分层与配对统计、共同完成条件比较、seed 波动与场景不确定性分离 |
| `artifacts.py` / `metrics.py` | 独立 run 目录、配置/源码/依赖快照、成功语义与指标 |
| `scripts/` / `tests/` | 环境与阶段验收、reward probe、冻结迁移、物理视频和报告构建；关键风险测试 |

`q:(7,)` 为 rad；工具位置 `x:(3,)` 在世界系、单位 m；位置 `J:(3,7)` 为 m/rad。模型完整 Jacobian 有 9 个可动 DOF 列，按元数据提取 7 个臂关节列。工具为 `panda_grasptarget` link 原点；全臂势场使用各自几何点，不能将 COM 原点误作 URDF link 原点。

主任务为 `J_dls @ (v_ref + Kp*(x_ref-x))`，次级为 `N @ u_secondary`。`N` 从 SVD 数值零空间基独立构造，不能把阻尼逆的 `I-J_dls@J` 说成严格零空间。动作 `(7,)` 先限幅至 `[-1,1]`、缩放为 rad/s，再投影、与主任务相加并经过共享速度限制。几何投影正确也不保证物理跟踪或安全，故保存投影泄漏、裁剪扰动、实际速度、碰撞与跟踪误差。

Study 物理/主跟踪为 **240 Hz**，三组次级控制统一 **60 Hz**（`action_repeat=4`）；每个物理步重算主跟踪并检查安全。原阶段 1 的 240 Hz 零动作开发配置继续保留。`resetJointState` 仅用于初始化、数值诊断和离线几何候选放置；所有正式 rollout、witness 和视频状态推进均经电机与 `stepSimulation`。

[RL 契约](docs/rl_formulation.md)详细说明 55 维特征、单位/归一化、未来 0.25/0.5/1 秒参考、奖励、失败锁存与终止语义。未来参考是已知任务信息；未独立训练无未来参考消融，因此不将任何增益单独归因于它。

## 输出、计时与结论边界

每个 run 创建独立 `experiments/<UTC>_<kind>/`，保存配置、来源与源码快照；场景/评估保存逐回合配置、summary 和 trajectory，训练保存模型与 validation 历史。不同类型的 run 不保证有相同文件，不能用不存在的图表或 checkpoint 证明已完成步骤。UTC 目录时间比新加坡本地日期早一天时并非记录错误。

`trajectory.npz` 有 N+1 行状态、N 行命令；命令 k 连接状态 k 与 k+1。上一“执行命令”指实际提交给电机的限幅速度目标，不等于 raw action 或测得速度。共享 study 阈值为位置误差 ≤ 0.020 m；几何距离 ≤ +1e-5 m 视作碰撞；关节限位使用 URDF 与额外 1e-4 rad 数值容差。手指由伺服保持而非刚性焊接，漂移仍记录。

在线 `decision` 包括状态/参考/几何安全检查、Jacobian/主控制与摊到物理步的次级计算；`secondary` 是每 60 Hz 决策的特征+APF 或特征+PPO 推理；`step` 是电机提交及物理推进。终点状态采样只进入 rollout 墙钟，不进入后续不存在的 command decision。加载、渲染和写盘不计在线控制成本。训练墙钟另记录含/不含 callback validation 的范围；不同 seed 并发耗时不能直接相加当作项目实际墙钟。

Witness 筛选是 tracker、默认 APF 与一个随机常量次级候选的有限并集；它证明接受场景存在一条在本契约下成功的实际运动，但存在筛选偏差，也不证明搜索失败场景不可行。最终结论只针对这种已冻结的 witness-filtered 分布与有限训练预算。失败短前缀与完整轨迹不混合宣称更小误差或更平滑；三训练 seed 波动和配对测试场景采样不确定性分别报告。

复用库、Panda 资产和许可证见 [attribution.md](docs/attribution.md) 与 `docs/third_party/`。
