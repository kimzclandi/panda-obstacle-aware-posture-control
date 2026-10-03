# 共享评估与冻结协议

本文件区分已实现的汇总机制与尚待正式冻结的实验设计。`analysis.py` 已实现失败保留、严格配对、条件连续比较和两种不确定性分离；该程序存在不代表正式场景、三 seed 训练或 held-out test 已完成。实际证据见 `progress.md` 及每次实验目录。

## 1. 场景先分割，后求 witness

场景规范应包含机器人/工具点与模型版本、初始七关节状态、球心和半径、固定轨迹起终点与时间规律、完整时长、物理步长、跟踪容差和共享执行器限制。先把规范序列化为稳定形式，例如排序键的 JSON；对不含运行结果、split 标签和 witness 的候选配置做 SHA-256。配置 hash 标识同一物理任务，不能通过改候选编号把同一任务复制到不同 split。

正式候选生成前固定生成器版本、采样分布、随机 seed、分割规则、比例和筛选预算，再进行与学习策略评价无关的可行性筛选。**当前受控研究的实际规则**见 `configs/study_protocol_v1.json`：train/validation 使用固定候选编号轮转，在 witness 求解前确定 split 和 simple/tight；test 使用另一个预先固定的独立生成 seed，生成任务只包含 test。物理配置 hash 用于跨来源查重与冻结，不用于分配 split。先前提出的 salted-hash 分配是未采用的方案，不能把它写成已实现功能。

保存所有候选的配置、分配、尝试方法与拒绝原因，接受场景的物理 hash 在冻结时独立重算。hash 查重只能阻止精确重复；本研究的初始姿态和布局仍来自同一生成分布，不是分布外泛化测试。相近起点/障碍布局的相关性须在解释置信区间时保留；不要把本研究的重复采样描述为对完全不同环境的泛化保证。

当前调试场景和任何已经用于观察表现、修正控制器、选择障碍范围的场景都属于 **development / pilot**。即使它们在代码中预分配了 `test` 标签，也不能据此宣布正式 held-out。正式 test 应在 pilot 后依据冻结规则重新生成，评估前封存清单与 hash；场景生成本身需要 witness 验证，但不能根据 PPO 或各控制器在该测试集上的相对表现再改任务难度。

接受场景必须有从相同初始状态、按相同时长与共享物理限制实际重放通过的 joint-motion witness。保存全部速度命令、关节/工具轨迹、容差与碰撞检查、物理配置及 replay 证据。离散 IK 解、状态重置序列或仅终点可达都不足以接受场景。没有找到 witness 的候选标记“尚未验证可行”，不能写成“已证明不可行”。witness 不进入策略 observation，也不隐式变为 imitation learning 数据。

为了审查筛选偏差，至少记录多个候选来源：tracker、不同势场参数以及预先固定的次级关节命令搜索等。对每种方法保存尝试次数、成功数、独有接受数和与其他方法的重叠，分 simple / tight 与 split 报告。只由某势场求出 witness 的场景会偏向该势场；多来源也不能证明无偏。formal test 筛选流程必须预先固定，候选失败记录保留。

## 2. 势场调参与 PPO 选模

三组控制器共享模型、初态、主任务跟踪器、参考时钟、速度/力矩限制、动作接口、所有可用几何信息和成功判据。PPO 七维有界次级 action 与势场次级命令都通过同一投影和最终限幅，不能通过不同控制频率或额外关节权限形成优势。

势场参数搜索和 checkpoint 选择只使用 validation；train 仅用于学习和训练诊断。当前受控研究已经预声明：势场使用固定 12 组网格，完整成功数优先，并列取最早网格索引；PPO 以成功率、较低碰撞率、完整执行率顺序排序，并列取最早受训 checkpoint。最终一次优化后的模型也进入 validation 选择；step zero 不参加选择。连续误差/平滑度不参与本次选模。其他更复杂的并列规则属于未采用方案，不能在查看 test 后补加。

保存每个 validation 候选的全部回合，不能只保存最优配置。PPO checkpoint 选择规则、评估频率、随机或确定性 action、训练 seed 列表和预算同样预先固定。test 不更新 observation/reward normalization 统计；若使用 `VecNormalize`，评估使用冻结训练统计并关闭更新。test 不参与 reward、容差、场景分布、网络结构或训练步数选择。

正式目标是三个独立训练 seed，每个策略与两条传统基线使用同一组至少 100 个固定 held-out 场景。基线无训练 seed，不必重复相同确定性 rollout 三次后把它们当独立样本。资源不足时报告实际 seed 数、场景数和预算，并明确未达 proposal 目标。

当前限定研究预算为 64 train、24 validation、100 test，三次独立训练各 98,304 policy decisions；这来自 pilot 成本估算，不能保证 PPO 收敛。执行前用 `scripts/freeze_study.py --trainval DATA --test DATA --potential SELECTED --model SEED BEST_MODEL`（三个 `--model`）`--output NEW_MANIFEST.json` 封存实际文件。冻结器先验证并固定模型与势场参数，才读取 test 的接受 witness 完整性；不执行 test 控制器或输出 test 方法优劣。

冻结必须核验 witness 源和 replay 的 config、summary、NPZ，而非只相信 `replay_passed`：N 个有界电机命令、N+1 个完整物理状态、未暂停参考时钟、真实初态、跟踪/关节/碰撞记录均一致。该检查是对已保存独立物理 replay 的证据核验，不能冒充再次执行 replay。原始文件、模型资产、依赖、参数、模型权重、源码及协议均保存 hash；dirty 工作树另存状态，commit 名字不代替源码 hash。test 入口在加载模型和场景前调用 `verify_frozen_inputs`，拒绝任何输入或代码与清单不一致的执行。

## 3. 逐回合记录和成功语义

输入 `episodes.json` 为非空 list，或包含 `episodes` list 的对象。批次对象用 `complete: false` 标记仍在写入或异常中断；分析器拒绝这些部分结果。正常批次结束后才写 `complete: true`，并提供 `expected_scenario_ids` 与 `expected_policies`（controller、training_seed 对象列表）以验证完整冻结名单。显式传入的独立 list 没有外部清单，分析器只能检查其中已经出现的策略之间是否配对。每行必须包含：

| 字段 | 含义 |
|---|---|
| `controller`, `training_seed` | 控制器名字；独立训练 seed，传统基线为 null/省略 |
| `scenario_id`, `split`, `difficulty` | 配置对应的固定场景 ID；分割；simple 或 tight |
| `success`, `completed` | JSON bool；完整成功；参考完整时域是否实际执行完 |
| `failure_reasons` | 锁存失败原因 list，包括 tracking_tolerance / collision / joint_limit / numerical_failure 等 |
| `completed_duration_s`, `requested_duration_s` | 实际执行前缀与规定完整时长，秒 |

连续字段包括 `max_position_error_m`、`rmse_position_m_on_executed_prefix`、`min_obstacle_clearance_m`、`command_squared_acceleration_integral_on_executed_prefix_rad2_s3`、`joint_step_saturation_fraction`、`decision_mean_ms`；缺失值用 null，不能填 0。汇总器拒绝 NaN/Infinity。

成功必须完整执行，且初始化与每个物理步后的检查均未触发失败。位置误差一旦越界，最终不能因恢复跟踪而变成成功；因此可以出现 `completed=True, success=False`。提前失败用实际前缀时长；完整执行检查允许 `1e-8 * max(1, duration)` 秒的浮点舍入误差，这只是记录一致性阈值，不是允许延长任务时间的控制权限。

正式报告还需写清物理检查频率、碰撞距离 epsilon、关节边界 epsilon 和跟踪容差。离散物理采样的全程通过只覆盖已检查时刻，不能证明步间连续安全。不同步长敏感性检查要作为附加实验单独列出。

## 4. 汇总、配对与不确定性

命令：

```bash
env -u PYTHONPATH .venv/bin/python -m panda_posture.analysis \
  --episodes experiments/<实际批次>/episodes.json \
  --out experiments/<新的分析目录>
```

输出目录必须不存在；程序保存原始输入副本、`summary.json`、`analysis_provenance.json` 和 `success_rates.png`。输入及分析源文件 SHA-256、NumPy 版本、bootstrap seed/次数均记录。分析结果不覆盖原始运行记录。

汇总按 `split × controller × training_seed × overall/simple/tight` 分组，不能混合 train、validation 和 test。主成功率分母是该组**所有评估回合**，包括 t=0 碰撞和提前结束。保存失败原因计数、碰撞率和实际执行时长；一个回合可有多个失败原因，因此原因计数之和不必等于失败回合数。

在每个 split 内，所有实际出现的 controller + seed 都必须有同一场景集合；缺失配对、重复回合、同 ID 出现在不同 split、难度或规定时长冲突时直接报错。提供 `expected_scenario_ids` 与 `expected_policies` 后，即使某个场景或控制器整体缺席也会被拒绝；没有 manifest 的输入无法推断整体缺席，正式批次必须保存并校验该清单。输入只有一个控制器可做单组汇总，但不会生成不存在的配对比较。

每个固定策略的成功率给出 95% Wilson interval。它描述在所选可行场景分布下的场景抽样不确定性；独立同分布假设、筛选和分层设计影响解释。对于人为调整过的 pilot，它只是描述性参考，不能当正式总体泛化结论。Wilson 方法参见 [NIST 比例置信区间说明](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm)。

两策略比较对同一 scenario ID 的成功指标作差 `B − A`，使用固定 seed 的 10,000 次 paired percentile bootstrap：同一重采样索引同时作用于 A 与 B。**overall 比较额外保持难度分层**：每次在各 difficulty 内有放回抽取原有的 `n_h` 对，再按固定 `n_h/n` 权重求差值；正式 100 场景对应每次 50 simple + 50 tight，不能让 bootstrap 改变已固定的难度配比。单个 difficulty 的比较使用普通配对重采样。输出记录分层样本数与权重规则。保存双方都成功、仅 A 成功、仅 B 成功、双方都失败的计数。不能独立重采样两控制器破坏配对。小样本、全一致或零离散度时区间可能退化，这不证明总体差值精确为零。配对与 percentile 定义参见 [SciPy bootstrap 官方文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html)。该项目实现直接重采样成功差值，未复制 SciPy 实现。

多个训练 seed 的结果分别保留，并额外给均值、样本标准差、最小/最大成功率；单 seed 的样本标准差为 null。训练 seed 的波动不能与 Wilson 场景区间混为一谈，也不能把 `3 × 100` 个相互共享场景的结果当作 300 个独立 Bernoulli 样本。若正式采用固定比例的难度分层，overall 区间是便于报告的近似；应同时给分层结果，不假装随机混合总体的严格区间。配对分析属于描述性区间，当前没有多重比较校正或预注册显著性检验。

## 5. 连续指标只能作有样本数的条件比较

对每一对策略，以及同 split 中所有策略，先取**共同实际完成完整时域**的 scenario 集合；不要求 success=True。若完整执行但曾超差，必须保留在这个条件集合。对每个连续指标，如果任一策略缺失该值，再对该指标使用所有策略共同有值的子集，报告样本数和排除数量，不计算不配对的均值。

输出明确标注 `conditional_on_common_full_horizon_completion`、`n_common_completed`、场景 ID 和每个 metric 的 `n_matched_metric`。集合为空则均值为 null。此时原本叫 `...on_executed_prefix` 的指标覆盖完整时域，才可比较误差或平滑度。总体成功率仍使用全部场景；条件连续指标不能解释为所有任务上的平均表现。

决策时间需由实际 evaluator 定义测量范围。应区分状态/特征构造、网络推理、跟踪与投影计算、碰撞检查、日志准备、电机提交与物理步进，另外报告总 rollout 墙钟和训练总耗时。不要把只含 MLP forward 的时间与包含全套几何计算的势场耗时直接比较。汇总器只传递 `decision_mean_ms`，不能从一个数字反推包含哪些步骤；最终报告必须引用该批次记录的计时契约。

## 6. 冻结前检查

1. 每个接受场景有完整物理 witness 和独立 replay 证据，拒绝记录完整。
2. 场景配置 hash 与 train/validation/test manifest 不相交，父场景相关性已审查。
3. validation 参数搜索和 checkpoint 选择规则已经固定，test 尚未用于相对表现调试。
4. 模型、依赖、主任务、执行限制、容差、检查频率、计时边界和种子写入配置。
5. 评估入口核对完整控制器名单与全部场景；分析拒绝缺失/重复配对。
6. 报告接受 RL 未超过势场的结果；未训练无 future-reference 对照时不作该特征的单独因果归因。
7. 视频挑选规则明确，展示失败示例；视频不能替代固定批量评估。

这些是工程验收条件，不是课程 rubric 或已完成实验结果。原始失败数据和旧版本输出始终保留。
