# 项目进度与证据

更新时间：2026-10-04（Asia/Singapore）。实验目录用 UTC，因此本地 10 月 4 日凌晨的文件名为 20261003T19…Z；不是日期记录错误。

## 已完成并实际验收

**阶段 1 已通过当前开发配置的验收；阶段 2–4 未完成。** 已读取两页 proposal 与用户课程截图，无初始代码可复用；创建独立项目、main 分支、Python3.11.17环境。系统环境与选择依据见 [environment.md](environment.md)。用户确认截止2026-11-20 23:59、老师允许完整AI辅助无需特别标注、目前独自推进。

最终验收代码 commit：`9f68d0b`。完整入口：`env -u PYTHONPATH .venv/bin/python scripts/validate_stage1.py`。

验收记录：[gate_20261003T191419.044956Z/index.json](../experiments/gate_20261003T191419.044956Z/index.json)。每项 stdout/stderr 均保留。

| 验收项 | 实测结果 | 证据 |
|---|---|---|
| 关键风险测试 | 32 passed in 2.46s | [tests.stdout.txt](../experiments/gate_20261003T191419.044956Z/tests.stdout.txt) |
| 模型核验 | arm7，finger2，full Jacobian3×9；工具link11原点，取arm对应3×7 | [model.json](../experiments/20261003T191423.707824Z_stage1_tracker/model.json) |
| Jacobian中央差分 | 5姿态×2扰动步长；最大绝对差 6.34601e-05 m/rad，阈值2e-4 | [jacobian_check.json](../experiments/20261003T191423.707824Z_stage1_tracker/jacobian_check.json) |
| 非零次级投影诊断 | 最大‖JN‖=1.78e-16；阻尼complement最大‖JN‖=0.000428 | 同上；零动作rollout不是此项证据 |
| 物理跟踪 | 4s，约79.1mm直线，960次电机/物理步，961检查状态；success=True | [summary.json](../experiments/20261003T191423.707824Z_stage1_tracker/summary.json) |
| 跟踪误差 | max=0.023597mm，RMSE=0.020514mm；开发容差20mm | 同上及trajectory.npz |
| 碰撞/限位/饱和 | 全轨迹均无检测到违反；指令饱和率0 | 同上 |
| 几何与执行 | 最小检查自净空20.2077mm；手指最大漂移1.77e-07m | 同上 |
| 命令物理重放 | 完整通过；最大关节状态差0.0rad | [20261003T191426.311904Z_stage1_replay](../experiments/20261003T191426.311904Z_stage1_replay/summary.json) |
| 半步长敏感性 | 480Hz、1920步通过，max误差0.027703mm | [20261003T191428.786891Z_stage1_tracker](../experiments/20261003T191428.786891Z_stage1_tracker/summary.json) |
| 初始碰撞负向用例 | 预期失败正确保留：step=0、success=False、failure=collision | [20261003T191432.203866Z_stage1_tracker](../experiments/20261003T191432.203866Z_stage1_tracker/summary.json) |
| 环境安装/依赖 | bootstrap脚本成功，精确锁定31个外部包；Torch/SB3/Gym导入成功 | requirements.lock.txt，gate/environment日志 |

[误差和状态图](../experiments/20261003T191423.707824Z_stage1_tracker/tracking.png)；[TinyRenderer末帧](../experiments/20261003T191423.707824Z_stage1_tracker/final_frame.png)。所有原始状态、命令、碰撞距离与逐步计时在 trajectory.npz。状态N+1行，命令N行。没有checkpoint，因为没有训练；不生成冒充训练完成的模型。

当次完整rollout墙钟0.8959s，约1071.5 physics steps/s；平均决策0.8410ms（含状态/参考/几何检查/Jacobian/控制），平均电机提交+物理推进0.0859ms。不是PPO训练吞吐。初次约1131steps/s与本次差异属观测到的运行时间差，不作性能显著性结论。

## 验收边界

- 只有一个容易的无障碍development轨迹及诊断变体，不能作为三控制器对比或test成功率。无障碍witness由tracker产生，只证明这条轨迹；未接受任何正式障碍场景。
- 240Hz与480Hz都通过，但误差没有随步长减半单调降低。当前数据不足以把误差单独归因于积分步长，DLS偏差和速度电机离散响应仍存在。
- 45个自碰撞对检查、10个结构对排除，完整清单见collision_review。球与臂/手/左右手指阳性、非邻接自碰撞阳性已测；没有只按末端距离判碰撞。
- 离散每步检查不是连续安全证明。+10微米近接触带、1e-4rad限位数值容差、20mm跟踪容差是当前开发配置，尚未冻结正式评估参数。
- GUI参数已提供但未试开；只验证DIRECT和TinyRenderer静态图。未导出视频。
- PyTorch CPU安装与GPU驱动可用并存；没有实测CPU/GPU PPO对比，未启动数小时训练。

## 已遇到问题、修复与保留记录

1. Python3.12 binary-only安装PyBullet失败（no matching distribution）；改为本项目Python3.11.17，原探测环境保留在上层work/，未修改系统Python。
2. ROS PYTHONPATH导致首次pytest在收集前加载launch_testing、因缺少yaml失败；统一清除PYTHONPATH并关闭外部pytest插件自动加载。不是靠安装ROS依赖掩盖隔离问题。
3. 初版NaN可能绕过success与joint limit比较；增加numerical_failure锁存/非有限关节拒绝，并加入NaN/±Inf回归。原始异常数组优先存npz，JSON将未定义指标记null。
4. 初始碰撞时0步命令数组曾缺少二维形状保证；显式保留(0,7)，测试绘图和失败分母通过。
5. `getClosestPoints`不自动尊重setCollisionFilterPair排除，必须显式按45对查询；相隔两跳link5–link7确实可碰撞，不能泛化排除。阳性原始记录在collision_review_evidence.json。
6. 首两次实验在最终依赖隔离/源码commit前运行，仍原样保留。其source_snapshot/provenance记录当时状态；正式阶段1验收优先使用本页gate所指的commit版本。

## 下一步与阶段门

1. **阶段2**：实现全臂几何势场和关节限位次级项，与tracker同一接口；构造多种初始姿态/线段/球布局，先验证距离梯度方向。共同建立场景记录、候选来源、拒绝原因及多种witness候选方法；每个接受场景必须同时间/限制/容差物理重放。搜索失败标记尚未验证可行；检查只由单一baseline产生witness的偏差。
2. **阶段3**：在已验证可行场景上封装Gymnasium；逐一规定obs坐标/单位/归一化与action缩放；有限任务终点terminated、外部超时truncated；检查停止/震荡/自杀reward hacking。先env checker、短PPO、save/load/独立评估，测吞吐与实际训练预算，再决定正式规模。
3. **阶段4**：train/validation/test隔离；validation调baseline和选checkpoint；冻结场景/配置/选择规则；目标3seed×100相同held-out场景，按简单/紧布局报告。失败留分母，共同完成的连续指标标条件样本量，区分seed波动与场景采样不确定性。最后做≤10页个人报告、对比视频与答辩。

尚未实现项目Gym环境/势场/PPO/正式分割，因此没有把相关检查写成通过。优先保留三核心对照；时间不足先删弧线和额外消融。

## 教学与待确认

学习单元1的十道主动回忆题见learning_notes.md；**用户掌握尚未确认**。工程通过不等于用户已能推导或答辩。课程完整rubric权重、视频细节、报告参考文献是否计页、答辩形式和50%原创计量口径仍无完整材料；不阻塞下一阶段可逆工程。


## 2026-10-04 继续执行：阶段 2 / 3 pilot 已验收

用户表示已掌握第一单元，要求继续工程。记录为用户自述，不追加测验。

- 共享物理内核迁移至 `ControlTask`，阶段1轨迹与历史记录关节差为0；所有控制器重用同一每240Hz检查/电机执行，次级动作60Hz更新。
- 新增全臂、手、指和自碰几何势场、关节限位项；最近点Jacobians与距离梯度有FD验证。
- `experiments/20261003T192914.966719Z_scene_pilot/scenes.json`：train8、validation8，各简单/紧布局各4；25实际候选中16接受、9初始碰撞拒绝。每个接受场景独立物理重放通过；tracker/default-potential/fixed-random分别找到12/13/13个witness（有交集），不存在“只保留APF成功”条件。
- 12组势场参数只在validation上调参；`experiments/20261003T193106.814027Z_potential_validation_tuning/selected.json`选中 obstacle_gain=.0001 / influence=.08 / self_gain=0，8/8成功。默认参数不是调优结果。
- 55维固定观测Gym环境、terminated/truncated、逐物理步reward、失败锁存、SB3检查、保存/加载完成。
- 三个8192步pilot seed44/45/46已训练；共享新环境validation对照：tracker5/8、tuned potential8/8、PPO分别7/8、6/8、6/8。仅validation开发结果，不是held-out结论。
- 第一个pilot callback漏选最后一次optimizer更新的边界已修复；seed44在`experiments/20261003T193819.575957Z_final_checkpoint_audit/`追加独立验证，旧记录不回写，两候选同为7/8，沿用较早checkpoint。
- 三控制器及三个PPO seed的40条完整validation记录：`experiments/20261003T194313.983182Z_paired_evaluation/`，分析仅完整批次，失败留分母。
- 奖励诊断 `experiments/20261003T194031.739736Z_reward_probe/`：24回合、3类固定探针；失败无成功bonus，参考时钟正常，未折扣/折扣回报均无早失败高于成功；一个双方失败场景振荡未折扣回报略高0.00450，未彻底排除hacking。
- 当前89项测试通过（7.84秒）；不以32步单测模型冒充训练模型。
- 实测约187 policy steps/s；seed44训练43.71秒，含callback验证69.51秒。三seed百万步仅训练约4.45小时，尚未启动该规模。

### 当前正在执行的预算受控研究

预先声明 `configs/study_protocol_v1.json`：64 train、24 validation、100 test；3独立seed144/145/146各98,304步、每12,288步全量validation，包含训练后最后更新验证。纯训练约26分钟，加验证预计约40分钟；不声称达到收敛或PPO最优。

生成器规则已固定：train/validation seed4410、独立test seed4490；candidate序号轮转分割/难度，test单独seed；初始障碍净空至少1mm，全部接受场景保存原时长/限制下通过的witness。**不是hash分配split**；physical hash用于去重/防泄漏。test生成阶段只审计witness与文件完整性，不能反馈控制器成绩用于调参。两项生成当前运行中，尚未完成目标计数。

正式test评估前将冻结场景hash、源代码、势场参数与三个已选模型的hash；model/params在读取test内容前固定。最终报告/完整对照视频和答辩材料仍待实际测试后生成，不能把预定规模写成完成。
