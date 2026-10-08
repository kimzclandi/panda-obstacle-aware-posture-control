# 实现决策记录

建立于 2026-10-04。下列为工程选择，不等于 proposal 已规定的算法，也不等于实验已通过。实际数值以每次实验保存的配置和依赖快照为准；修改选择时追加理由与影响，不回写旧实验。

## D001：最小运行环境

采用 Python 3.11.17 的项目独立 `.venv`，候选依赖为 PyBullet、NumPy/SciPy、Gymnasium、Stable-Baselines3/PyTorch、Matplotlib；安装并验证后锁定实际版本。最初考虑 Python 3.12，但 PyBullet 3.2.7 缺少所需的 cp312 wheel，因此改用独立 Python 3.11.17，避免把耗时源码构建当作默认前提。CPU + DIRECT 为首个运行模式。GPU 是否存在由环境审计记录；即使有 GPU，也不推定它会加速 PyBullet CPU 仿真或小 MLP PPO。正式预算由实测吞吐和 pilot wall time 推算。

理由：先减少图形、设备和训练并行带来的变量，完成物理执行闭环。GUI 与视频可后加，不替代 DIRECT 评估。

## D002：模型与工具点由名字和运动学核验

加载 PyBullet bundled `franka_panda/panda.urdf`、固定基座，七个 arm joints 为受控维度，手指保持固定目标。运行时读取 joint name、joint type、`qIndex/uIndex`、link name、限位和力矩/速度元数据，再建立 arm/finger/末端和 Jacobian 列映射。实际模型读取结果：arm joint indices 为 0–6，可动关节 indices 为 0–6、9、10；工具为 `panda_grasptarget`（link 11）原点。工具 link 与局部工具点仍必须在每次运行日志中写清；不把此版本的索引外推为所有 Panda 模型的事实。限位采用已加载 URDF 的数值，并不宣称等同于真机厂商规格。

有限差分诊断可以临时使用 `resetJointState` 计算数值导数；之后恢复初始化。正式 rollout 只通过电机与 `stepSimulation` 推进。诊断不计作物理可行 witness。

## D003：位置主任务采用阻尼逆，次级项单独构造严格零空间

主任务采用阻尼最小二乘，等价公式为 `J# = J.T @ inv(J @ J.T + lambda**2 * I)`；生产实现复用 SVD，并将奇异值变换为 `s/(s²+lambda²)`，不显式求逆。`lambda > 0` 限制小奇异值带来的命令放大，但引入任务速度偏差。

次级投影从完整 SVD `J = U @ S @ V.T` 构造 `N = V_null @ V_null.T`。在所选数值秩下，`J @ N` 应接近零；秩阈值和奇异值必须可检查。数值秩切换可能使投影变化，需监测平滑性。

不用 `I - J# @ J` 宣称严格零空间：当 `J#` 是阻尼逆时，该矩阵一般不满足严格投影条件。严格零空间也只描述当前线性化的理想关节速度，不能抵消电机误差、离散积分和饱和。

## D004：240 Hz 起步，控制命令经速度电机执行

初始仿真与控制频率均为 240 Hz，每次计算命令后调用仿真步进，并读取实际状态。速度、电机力矩和关节范围均受共享配置约束；手指电机以位置伺服维持各 0.02 m，记录实际偏移；不宣称手指刚性焊死。无障碍阶段 `u_secondary = 0`。

光滑直线参考使用平滑时间标定，明确起止速度和完整时长；轨迹时钟由仿真推进，不因误差或避障而暂停。是否需要更小步长、降低增益或调整时长，要通过 pilot 证据决定。比较控制器时统一修改共享参数。

## D005：记录三个层次，定位跟踪失败

保存解析主任务速度、投影后的次级速度、组合/限幅/执行命令，以及真实 `q_dot`。分别观察位置误差、`||J N u||`、速度饱和率与实际执行偏差。这样可区分运动学错误、投影问题、命令约束与电机响应。

所有控制器共享同一最终执行函数和安全判据。势场与 PPO 均不能得到额外 actuator 权限；RL 不能修改参考时间。

## D006：碰撞验证先于场景接受

障碍净空使用全臂、手与手指的碰撞形状到球形障碍物的几何距离。允许的结构邻接/固定连接接触与禁止自碰撞分开，排除清单和原因须可审查。初始 robot 自碰撞配置与测试结果由程序输出，不能仅凭“看起来没碰”确认。

离线关节搜索可用于构造碰撞正例和 witness 候选，但动态 witness 必须从相同初始状态按相同时长和限制物理重放通过。

## D007：教学与工程并行

学生掌握状态仅通过回答与纠错确认。工具与代码已实现不标记为学生已掌握。首个单元聚焦坐标、Jacobian 和主次任务关系；后续按仿真、RL、实验与失败分析推进，主动回忆题不阻塞工程执行。

## D008：保持主任务 240 Hz，次级决策统一 60 Hz

阶段 1 原始配置继续作为无障碍工程回归。阶段 2/3 与 study 使用 `action_repeat=4`：tracker、APF、PPO 的次级动作均以 60 Hz 接口执行，物理与解析主跟踪保持 240 Hz。四个物理步内保持次级 action，但每步重新读取状态、计算 Jacobian 和主任务速度，并检查碰撞、限位和跟踪误差。

理由：减少次级特征/网络决策开销，同时保留逐物理步监控；不能把提高 RL 动作权限作为优势来源。最后一段可不足四步，参考时钟不等待 controller。Study 位置容差为 0.020 m、碰撞距离阈值 +1e-5 m、关节边界数值容差 1e-4 rad、统一 4 s 时域。它们是本研究冻结的实现选择，仍不是连续安全保证。

## D009：全臂 APF 使用几何距离梯度，并实际完成 validation 调参

新增 `secondary.py` 与 `robot.py` 几何方法，从 `getClosestPoints` 获取世界最近点和 B 指向 A 的法向；球障碍的关节距离梯度为 `n.T @ J_A`，自碰为 `n.T @ (J_A-J_B)`。固定基座 Jacobian 为零；查询包含 base、臂、hand 和左右 fingers，保留原 45 个自碰对与 10 个排除对。

点 Jacobian 必须使用从 URDF link 原点度量的局部点，不能把 COM 平移当作 link 原点。三个姿态的全碰撞 link 非原点材料点 Jacobian、球/自碰距离梯度及方向已通过数值差分；在线 controller 不重置或推进仿真。有限作用范围的逆距离场在 15 mm 距离 floor 处正则化，关节限位软区 0.3 rad、边界速度增益 0.4 rad/s；仍可能局部极小、抵消或在零空间投影后无有效避障方向。

研究调参预先声明 12 组 `obstacle_gain ∈ {.0001,.0004,.0016}`、`influence_distance ∈ {.08,.16}`、`self_gain ∈ {0,.00008}`，全部在同一 24 场景 validation 上实际执行，288 回合保留失败。按成功数最大、精确并列取最早 index 选 candidate 0：`.0001/.08/0`，23/24（simple 12/12、tight 11/12）。关闭该候选的自碰排斥项不关闭自碰检测；不根据 test 改用其他并列候选。

证据：[selected.json](../experiments/20261003T195747.519524Z_potential_validation_tuning/selected.json)、[完整原理与候选表](potential_field.md)。这只是固定有限网格下的选择，不声称穷尽传统控制器或达到全局最优。

## D010：场景接受基于三种物理 witness 的并集

新增 `scenes.py`。先用无障碍实际运动得到离线障碍放置参考，随后分别尝试 tracker、默认 APF 和一个有种子的随机常量次级命令；每个候选都有相同的初始姿态、参考时间、速度/力矩限制和成功判据。接受条件是至少一种完整成功，再将选中 witness 的逐物理步 motor targets 在新仿真中重放通过。几何放置可使用 reset，但 witness rollout 和 replay 必须使用执行器与 `stepSimulation`。

保留三个方法的结果、失败轨迹、候选配置、拒绝原因和选择记录。初始禁止碰撞拒绝；另预先要求初始球净空至少 1 mm；未找到 witness 记“尚未验证可行”。这不证明数学不可行。Witness 不作为 policy observation、reward 标签或模仿学习数据。

已完成 train 64/validation 24，两个 split 各自 simple/tight 对半；证据：[场景清单](../experiments/20261003T194210.629028Z_study_scenes/scenes.json)及[审计](../experiments/20261003T194210.629028Z_study_scenes/post_generation_audit.json)。88 场景的物理 witness/replay 均完整 960 步、961 状态，关节重放差为零。182 条实际候选记录中，88 接受、85 初始碰撞、1 初始 margin 不足、8 尚未验证可行；接受集含 8 个仅随机次级 witness 成功场景，因此不等同于“APF 成功场景集合”，但有限并集仍有选择偏差。

独立 generator seed 4490 的 [test 100 场景](../experiments/20261003T194217.720814Z_study_scenes/scenes.json)与 witness 已生成并保留。生成/完整性审计不用于比较最终控制器、调 APF/PPO 或改变难度。正式 test 比较在全部模型和输入完成 pretest freeze 后执行，现已完整完成；未据此反向调整场景分布。

## D011：55 维固定归一化 observation 与有限时域任务

新增 `env.py`，复用 `ControlTask`；55 维观测包含 q/qd、当前误差与参考速度、轨迹进度、未来 0.25/0.5/1.0 s 参考偏移、球心/半径/存在标记、上一实际电机命令、自碰/障碍全局净空、11 个碰撞 link 的球净空。维度、世界系、单位和固定缩放在 [rl_formulation.md](rl_formulation.md) 中定义。

采用固定变换而非 running mean/variance，validation/test 不更新归一化统计；policy 不读取 witness、策略标签或 test 信息。有限 horizon 的完成与任务安全失败使用 `terminated`；仅外部预算切断使用 `truncated`。跟踪超差永久失去成功资格但允许继续当前时钟。进度进入 observation；仍不声称低维特征精确包含所有模拟器内部状态。

Reward 逐物理步积分有界跟踪、净空和平滑项。完整成功加 20，任务失败减 `20 + 3.1 * 剩余秒数`，减少通过早失败跳过负运行项的诱因。当前 4 s 未折扣回报可保守检查成功下界 7.6、失败上界 −16，但不因此声称 PPO 必然成功或已穷尽 reward hacking。零动作、极端动作、振荡 probe、终止语义及保存加载已检查；未做独立无未来参考训练，不能将收益单独归因于 future-reference。

## D012：PPO 先 pilot 后有界三 seed 研究，CPU 单线程并发

短试验已完成环境检查、实际训练、模型保存/加载和独立 validation。基于实测 pilot 成本，预先声明 [study_protocol_v1.json](../configs/study_protocol_v1.json)：seed 144、145、146 各 98,304 policy decisions，每 12,288 步验证，64×64 MLP、SB3 PPO rollout 512、batch 64、epochs 10、固定学习率/奖励配置。预算不等于收敛证明。

三个研究进程现已完成，目录分别为 [seed144](../experiments/20261003T195813.023303Z_ppo_study_seed144/)、[seed145](../experiments/20261003T195813.017181Z_ppo_study_seed145/)、[seed146](../experiments/20261003T195813.082516Z_ppo_study_seed146/)，各实际完成 98,304 policy decisions、最后优化更新验证、保存/加载检查与独立 validation。选中步数分别为 61,440、12,288、49,152；独立加载验证成功数分别为 19/24、17/24、18/24。这是 validation 选模证据，与后续完整 held-out test 分别报告，不合并成功率分母。

三个进程均 CPU Torch 单线程，OMP/BLAS 线程为 1；这是同机三个独立 learner，并非分布式训练，也没有 CUDA 加速实测结论。学习墙钟含 callback validation 分别为 808.387、780.717、807.257 秒；扣除该验证后约 176–177 policy steps/s。三进程并发实际墙钟约 14 分钟，不能将各 run 墙钟求和当作项目 elapsed time。

训练入口只消费 train/validation，保存实际消费场景、数据/协议 hash、源码快照与 validation 历史。学习墙钟分别记录含 callback validation 和估计排除 validation 的范围；并发 seed 的 process wall time 不能相加冒充项目 elapsed time。

## D013：checkpoint 选择排除 step zero，纳入最后 optimizer update

选模只使用固定 validation 完整成功率，其次碰撞率低、完成率高；完全相同保留最早已训练 checkpoint。未训练 step zero 只作诊断，不能赢得选模。SB3 的 step callback 发生在 rollout 收集期间，先于当前 rollout 的优化；因此结束后必须额外执行 `final_after_update` 验证，即使 step 计数相同也不能跳过。

History 同时记录阶段与 optimizer epochs；最终模型保存/加载检查确定性 action 完全一致，选中模型在新环境中独立验证。早期 pilot 若使用修复前流程，另用 `scripts/revalidate_checkpoint.py` 保存独立补验证结果，不覆写历史冒充原本已完成。研究进程采用修正后的流程。

## D014：完整 pretest freeze 后才执行固定 test

`freeze.py` / `scripts/freeze_study.py` 将核验 train/validation/test ID 与物理 hash 无重叠、所有 witness 数组与 summary 一致、同指令物理 replay 证据、数据/源码/依赖与执行配置一致、APF 全网格、三个模型训练步数/选模规则/最终更新验证/保存加载，然后绑定所有输入 hash。它是对已保存物理证据的完整性审计，不是再次独立运行全部仿真或防伪造的密码学证明。

三个模型已完成，完整 [pretest manifest](../experiments/study_pretest_freeze.json) 已通过并在 test 比较前保存；固定五策略各 100 场景、共 500 回合现已完整完成，全部失败保留。`batch evaluate --split test` 强制带 `--freeze`，在读取 test 配置和载入模型前验证所有被冻结文件与源码。`scripts/run_frozen_test.py --index study_index.json` 是冻结后的完整复评入口，每次另建目录。后续移动项目路径时，只能通过 `scripts/relocate_freeze.py` 创建并验证新的路径清单，保留原件；路径迁移不允许静默重写内容 hash。

## D015：配对分析和视频遵守不同证据边界

新增 `analysis.py`，完整性检查要求固定 controller/seed × scenario 矩阵与全部失败保留。主要比较为完整成功率；按 simple/tight 分层。配对 bootstrap 在场景内保持策略配对，总体分层重采样保持固定难度比例；它衡量固定策略下的场景抽样不确定性，跨三个独立训练 seed 的波动另列，不能把三 seed × 同一百场景当作三百独立场景。

连续指标只在所有被比较策略都执行满时域的共同场景上报告，并明确条件样本数；完成不自动等于成功。不得拿早碰撞的短前缀低误差或低平滑积分作为性能优势。计时分 state/几何/控制、次级特征+推理和 motor+physics；终点 state 采样进入 rollout 墙钟，不进入不存在的下一条 decision。

`scripts/render_comparison.py` 读取真实配对 run，使用保存的 motor targets 经 `ControlTask.advance` 与仿真步进重放，并逐状态核对 q；它不使用中途 reset。首次失败后 pane 冻结、显示 FAIL 和失败时刻；若源记录在跟踪失败后仍执行，后台继续物理重放仅用于一致性核对。最终选取两段 held-out case，六个 pane 的 q 重放差全部为 0；原速 4 秒 clips 已完整保留。`scripts/compose_demo.py` 合成的[最终视频](../deliverables/videos/final_demo_en.mp4)为 38 秒、30 fps、1140 帧、1536×722；完整解码和各段抽帧视觉 QA 通过，见[验证记录](../deliverables/videos/visual_review.json)。视频用于解释行为，不用于选择 checkpoint，也不替代 500 回合证据。

## D016：报告与依赖交付以完成证据为前置条件

锁文件已更新为 35 个外部包，加入视频与 PDF 生成依赖；CPU/DIRECT 的核心选择不变。[study_index.json](../study_index.json) 已完整记录训练、冻结、evaluation、report、demo 与交付验证路径。`scripts/build_report.py` 从该索引读取真实路径，要求完整 5 策略 × 100 test 回合、匹配 episodes hash 的分析、pretest freeze 和训练完成记录；这些前置校验现已实际通过。

[英文报告](../deliverables/report_en/final_report_en.pdf)实际生成 9 页，含参考文献，所有页面已渲染并通过视觉 QA；[中文结果解读](../deliverables/interpretation_zh.md)、[失败分析](failure_analysis.md)和[答辩准备](viva_guide_zh.md)均已完成。重建报告使用 `--out deliverables/NEW_DIRECTORY` 指定不存在的新目录，不能覆盖现有报告；新版本须重新视觉检查。报告遵守个人报告要求，不复制 proposal/早期报告文本；提交者仍需核对身份与个人反思，不虚构成员贡献。复用库/资产、许可证与 AI 辅助事实按课程材料与用户说明分开处理，不宣称已满足未明确计量口径的 50% 原创比例。

## D017：搬迁复现验证环境重建与物理结果，保留初次失败

[原目录交付验证](../experiments/20261003T201415.503267Z_delivery_validation/status.json)对三个选中模型在固定 validation 场景分别执行完整 960 步，240 次 visited observation 的保存/加载动作一致。[独立搬迁验证](../experiments/20261003T202857.594683Z_relocation_verification/summary.json)在同机另一目录创建全新 Python 3.11.17 与 `.venv`，安装 35 个锁定包并验证 26 个科研源码文件哈希；三个模型的完整 validation rollout 状态与命令数组均与原目录逐位相同，q/command 最大差为 0。计时数组不参与一致性声明；这不是另一台机器或不同操作系统的复现保证，也不是第二轮完整 test。

初次新环境安装真实失败：附加 PyTorch 索引的优先规则使普通依赖无法取得锁定版本。Bootstrap 改为公开 PyPI 主索引加 Torch CPU 专属 `find-links`，不修改锁定版本。editable 安装会重写 `src/panda_posture.egg-info/SOURCES.txt`；bootstrap 先核验并保留五个被冻结元数据文件，安装后恢复原字节并保存变化审计。交付包必须保留这些文件，不能把环境安装产生的元数据变化误认成科研内容变更或绕过 freeze。

完整[解压搬迁流程](reproduction.md)依次重建环境、创建 relocated freeze、运行 `scripts/validate_delivery.py --index study_index.json --freeze <new_manifest>`，需要完整复评时再运行 `scripts/run_frozen_test.py`。原 freeze、安装初次失败和修复日志保留。归档工具在报告、视频、分析和冻结内容验证通过后构建清单并检查 ZIP CRC，成功后才发布新文件；本记录不把打包工具存在写成 ZIP 已发布。

## D018：保留负结果与诊断边界，不在 test 后补调参

完整固定 test 的成功数为 tracker 70/100、调优 APF 92/100、PPO 144/145/146 分别 80/100、81/100、65/100。本预算与已冻结 witness-filtered 分布下没有支持 RL 超过 APF；全部分层结果、配对区间与共同完成条件指标见[analysis/summary.json](../experiments/20261003T201319.444915Z_paired_evaluation/analysis/summary.json)。跨训练 seed 波动与固定策略下的场景采样区间分别报告，不能将同一百个场景当作三百个独立样本。

[失败分析](failure_analysis.md)核对 seed 146 的三个关节限位失败：均为 `panda_joint6` 接近上界时持续向外运动，一个物理步后越界；这些回合没有最终电机速度饱和，投影泄漏为数值精度量级。记录不能证明网络内部原因，也不能将良好的位置跟踪等同于安全。未根据这些 test 失败重新训练、改变奖励或添加限位过滤器后继续沿用同一 held-out 结论。

## 当前已确定与仍待完成

本研究的场景分布、三类数量、物理步长/时域/容差、PPO observation/reward/网络与训练预算已预先声明；APF 已由 validation 选定。它们不能依据 test 表现再调整后继续沿用同一 held-out 声称。阶段 1–4 的有界研究与交付材料已完成；弧线、无未来参考独立训练消融、更长训练和跨机器复现未执行。

已完成：三个 study run、最终选模/独立验证、正式 pretest freeze、500 回合 test、分析、9 页英文报告、中文解读、38 秒视频、失败分析、答辩材料与新环境搬迁验证。最终 ZIP 的实际发布以压缩包和 receipt 为准；未自动上传 Canvas。课程要求见 [course_requirements.md](course_requirements.md)：用户确认截止 2026-11-20 23:59（Canvas 显示时区未核验），完整 rubric、视频细节和原创比例口径仍待材料确认，不以工程选择替代。


## D019：Git 源码与完整实验 Release 分开发布

用户要求上传到 GitHub；账号经 GitHub 连接器核验为 `kimzclandi`。新建 `panda-obstacle-aware-posture-control` 私有仓库，保留现有 Git 历史，不自动授权外部协作者。Git 保存源码、配置、文档和现有报告/视频；忽略环境及大体积原始实验。完整 716,482,807 字节 ZIP 用作 Release 附件，SHA-256 为 `52c9a77d28a992bc1e03ba0465d47bcce1f4d3a55c7ff8e63c7af3e14b85958b`，其内容与提交 `62d74a5` 对应，保留模型、全部失败与冻结元数据。README 明确 clone 与完整复现包的区别；不把只有代码的 checkout 宣称为具备冻结复评所需数据。发布文档变化不修改已冻结源码、配置、权重或原始 ZIP。实际上传成功与远程核验结果另记发布 receipt。

2026-10-04 后续更新：用户明确要求先公开，并表示已征得同意；据此将同一仓库改为 public。原 private 发布记录作为历史保留，当前可见性以此更新和 GitHub 设置为准；完整 Release 同时可公开访问。

## D020：交互展示复用冻结控制器，只添加显示节奏

用户要求打开实际仿真。`scripts/live_demo.py` 先核验冻结输入，再复用 `ControlTask`、PPOController 和选定 APF；默认固定 validation 首场景。SPACE 仅在开始前启动任务；运行时参考时间仍由固定物理步递增，不能暂停。控制器切换和 R 重开只允许在开始前或终止后，重开才创建新的初始化状态。终止后保留显示而不再推进仿真，中断记录为不成功；实际轨迹另存，不改变原始 500 回合。等待/渲染墙钟不作控制性能比较。原 v1.0.0 归档不变，入口和使用说明在 main 新增；本机 GUI 实跑证据记入 progress。


## D021：公开介绍清理与原始证据脱敏分开记录

用户要求去除公开介绍中的身份关联信息。先验证现有关键测试、固定模型加载与执行，再只发布 About、README 和 Release 正文的介绍修改；原科学输入及交付附件字节不变。已指出文件内容和历史提交仍可包含原标识，未将介绍清理表述为完整匿名化。若扩大处理范围，需要保留本地原始证据，并为公开派生版本重新建立一致的元数据与校验记录。


## D022：Gym C&R 单独做轻量可运行交付（2026-10-09）

根据新阶段截图制作独立派生包，不改冻结科研核心或原始最终归档。六个 core 文件逐字节复制，保留 SHA-256；选用原 validation 场景 study-4410-0005 及实际 replay witness。仅添加 RGB 可视化和 deterministic info 适配器，剔除 wall-clock profiling 字段以满足 Gymnasium 确定性检查；动作、reward、物理执行不变。默认 CPU DIRECT，不需 Torch、模型或完整研究目录。

新建项目内 micromamba 环境，从实际安装导出精确 Linux environment.yml，再用该最终文件创建另一个空环境。打包后解压到独立目录，9 项检查通过；zero/random 两种 rollout 的十组物理/观测/动作/reward 数组与包内预览逐位相同。两页英文小组报告单独写作，中文解读作为用户核对材料。只生成本地文件，不发布或提交。


## D023：先审阅学习稳定性，再决定是否补训练（2026-10-09）

下一项工作从validation历史与选模完整性入手。seed145选中检查点17/24，而训练最后1/24，独立加载/物理复跑重复该结果；15次关节限位、8次碰撞的失败类型已有新轨迹证据。以此提出报告中的训练稳定性讨论，不把“训练不足”写成未经验证的唯一原因。保留原三模型、场景、阈值及测试结论。后续若有改进实验，另立train/validation诊断方案；对改进方法作新的held-out结论需新未见test。当前不启动长训练。

保留旧报告和归档，新增讨论材料而不直接覆盖已审阅PDF；个人反思由真实经历提供，不虚构队友分工或掌握情况。用户要求不代提交继续有效。


## D024：final 优化先完成证据表达与搬迁运行（2026-10-09）

在原冻结研究上新增十页技术报告、52秒标注视频与自动搬迁验证，不为追求RL胜出延长同一退化训练或回看test调参。报告明确selected/last checkpoint，视频显示真实障碍/时钟/失败时刻；相机角度只是显示选择，保持原电机重放序列。新增quickstart从明确protocol路径推导原根目录，随后仍经过完整冻结校验；不编辑旧绝对路径证据。

个人身份和真实个人反思尚未收到，技术部分继续完成；不虚构个人贡献或假装其他成员独立报告齐全。旧报告、旧Release、旧阶段包及原失败回合保留，当前入口由study_index声明。生成本地完整ZIP与清单，不代提交或推送。


## D025：用户授权同步今天的 GitHub 更新（2026-10-09）

用户明确要求将今天完成的内容同步至既有公开仓库，因此此前“不更新GitHub”的限制对这次发布已被后续授权取代；不代提交课程平台的要求仍有效。默认main与本地原HEAD一致，另有独立开发分支；本次不改动该分支。提交当前已验证的源码/文档/媒体，完整750,132,146字节ZIP以v1.1.0 Release附件分发，保留v1.0.0。

已验证ZIP不重新打包，保留其基准commit与当时未提交工作树的真实provenance，不能将新发布commit反填进旧证据。Release说明解释tag与ZIP内容清单的关系。新首页、About和Release介绍继续避免学校/课程/组号标识；这延续此前介绍清理的范围，不将含历史原始证据的完整包冒称完全匿名化。
