# 项目进度与证据

更新时间：2026-10-09（Asia/Singapore）。UTC 实验目录时间比本地日期早一天属正常换算。历史阶段1/pilot记录保留于 [progress_history_stage1_to_pilot.md](progress_history_stage1_to_pilot.md)；原始实验和失败记录均未覆盖。

## GitHub 发布

2026-10-04 公开介绍隐私清理：About、main README、Release 正文已移除学校/课程/组号及提交信息，已匿名读取远程核验；提交 `4b003c5`。本次关键测试 108 passed in 8.21 s，三模型固定 validation 复核通过，证据 `experiments/20261003T212128.165230Z_delivery_validation/`。科研源码和原 Release 附件字节未改。此项仅是介绍清理；附件、其他文档和旧 Git 历史仍包含原标识，全面脱敏范围已向用户另行询问。之前交互 GUI 的未提交工作保留，未混入本次已发布的 README 隐私提交。

2026-10-04 已上传至 [kimzclandi/panda-obstacle-aware-posture-control](https://github.com/kimzclandi/panda-obstacle-aware-posture-control)。最初以 private 发布；随后用户明确表示已征得同意并要求公开，现已改为 **public**，仓库与 Release 可公开查看和下载。原五次 Git 提交全部保留；`main` 另含发布文档更新，`v1.0.0` 指向完整实验包对应的原提交 `62d74a5`。

[Release v1.0.0](https://github.com/kimzclandi/panda-obstacle-aware-posture-control/releases/tag/v1.0.0) 已发布完整 ZIP（716,482,807 字节）、打包 receipt、独立英文 PDF、MP4 及 `SHA256SUMS`。GitHub 返回的五个附件字节数与 SHA-256 均与本地一致。完整 ZIP 的 SHA-256 为 `52c9a77d28a992bc1e03ba0465d47bcce1f4d3a55c7ff8e63c7af3e14b85958b`。

已从远程重新克隆并逐文件核对 281 个 tracked 文件，历史、tree 和 tag 对应关系正确；原科学输入冻结检查再次通过。本次只更新发布文档，没有重新训练或修改原始实验。Git checkout 不包含 experiments 和冻结安装元数据，冻结模型验证必须下载完整 Release ZIP 并按搬迁流程运行。此项是 GitHub 存档发布，未上传 Canvas。

## 当前完成范围

2026-10-04 用户要求当场运行后，重新执行关键测试得到 **108 passed in 7.59 s**；[新三模型 validation smoke](../experiments/20261003T211156.893860Z_delivery_validation/status.json) 全部成功，各 960 个物理步、240 次重载动作一致。新增 [交互 GUI 入口](../scripts/live_demo.py)，复用冻结控制器与物理执行：本机 X11/NVIDIA OpenGL GUI 中，[PPO 144](../experiments/20261003T211457.391146Z_live_gui_demo/rollout/summary.json) 与 [APF](../experiments/20261003T211640.892363Z_live_gui_demo/rollout/summary.json) 均完成固定 validation 场景的四秒 960 步；最大位置误差分别 0.0398811 mm、0.0355840 mm，无碰撞/限位失败。GUI 只是交互展示，未重新比较 test 或改选模型；显示等待不作为决策耗时证据。另有两个 DIRECT 包装层检查（目录 211439/211514）验证完整运行与主动中断失败语义，不能算作 GUI 验证。原 v1.0.0 ZIP 未改；2026-10-09 核对确认交互入口仍为本地未提交文件，之前“随 main 发布”的描述已纠正。

**阶段1–4的预算受控研究、英文报告、中文解读、演示视频和答辩材料已完成。** 三个独立seed各训练98,304policy steps；64 train、24 validation、100 test均有完整物理witness；5policy×100test=500/500回合完成。结果没有达到“RL超过APF”：APF92%，PPO80%/81%/65%，tracker70%。该负结果如实保留，不在看过test之后改预算或模型。

- 总入口：[study_index.json](../study_index.json)，包含固定场景、选参/训练run、freeze、评估和交付路径。
- 英文报告：[final_report_en.pdf](../deliverables/report_en/final_report_en.pdf)，**9页**含参考文献，逐页渲染与视觉QA通过；[来源记录](../deliverables/report_en/report_provenance.json)。个人报告草稿仍需提交者核对身份与个人反思。
- [中文解读](../deliverables/interpretation_zh.md)、[答辩材料](viva_guide_zh.md)、[失败分析](failure_analysis.md)。用户自述已掌握，未追加阻塞测验，不虚构独立掌握核验。
- [英语演示视频](../deliverables/videos/final_demo_en.mp4)：38s、30fps、1536×722、1140frames；无音频。两段物理replay共6pane全部q差0，结果卡保留所有失败；[视觉QA](../deliverables/videos/visual_review.json)。

## 冻结测试结论

[原始500回合](../experiments/20261003T201319.444915Z_paired_evaluation/episodes.json)；[统计汇总](../experiments/20261003T201319.444915Z_paired_evaluation/analysis/summary.json)。每个策略使用同一100场景，simple/tight各50。

| 控制器 | Overall | Simple | Tight | 碰撞 / 限位失败 |
|---|---:|---:|---:|---:|
| Tracker | 70/100 | 49/50 | 21/50 | 30 / 0 |
| Tuned APF | 92/100 | 50/50 | 42/50 | 8 / 0 |
| PPO 144 | 80/100 | 43/50 | 37/50 | 20 / 0 |
| PPO 145 | 81/100 | 44/50 | 37/50 | 19 / 0 |
| PPO 146 | 65/100 | 35/50 | 30/50 | 32 / 3 |

相对APF的分层paired bootstrap差值区间（95%，10000重采样）为−12pp [−21,−3]、−11pp [−20,−2]、−27pp [−38,−17]。跨训练seed均值75.33%、样本SD8.96pp单独报告，不把相同100场景当300独立场景。

五策略共同完成样本n=45，RMSE/净空/平滑度条件比较，不将早失败前缀混入完整路径平均。全部执行前缀最大位置误差0.498mm，max投影泄漏2.6851e−16m/s，无最终电机目标速度饱和或跟踪超差失败；不能推断未执行后缀。三个限位失败都是seed146持续向panda_joint6上界运动，详细因果边界见failure_analysis。

## 数据与模型链

- [train64/val24](../experiments/20261003T194210.629028Z_study_scenes/scenes.json)，SHA256 `4a164c1b3792f67e637cf3516c69c3b9a77f9a1d42d27896f3c21b7a4211a55f`。182候选记录，88接受、85初始碰撞、1初始margin、8未验证可行；全部960命令/961状态witness和实际replay通过。
- [test100](../experiments/20261003T194217.720814Z_study_scenes/scenes.json)，SHA256 `cea56e113faf3621cc3026e5fda807512295400a9072248847d32ac9dda2ad70`。186候选记录，100接受、75初始碰撞、3初始margin、8未验证可行。
- [APF调参](../experiments/20261003T195747.519524Z_potential_validation_tuning/selected.json)：12组×24val，选candidate0 (gain.0001/influence.08/selfgain0)，23/24。并列按最早index，不看test。
- [PPO144](../experiments/20261003T195813.023303Z_ppo_study_seed144/training_summary.json)：选61,440，val19/24；[PPO145](../experiments/20261003T195813.017181Z_ppo_study_seed145/training_summary.json)：选12,288，val17/24；[PPO146](../experiments/20261003T195813.082516Z_ppo_study_seed146/training_summary.json)：选49,152，val18/24。均完成98,304，并检查最后optimizer更新、保存/加载和独立val。
- [pretest freeze](../experiments/study_pretest_freeze.json)在所有正式test比较前固定模型、参数、科学代码/配置、数据和witness哈希；训练和生成核心没有在test之后修改。
- 各seed学习含callback val约13.47/13.01/13.45分钟，CPU1thread并发，约14分钟并发墙钟。无GPU性能结论；没有启动三seed百万步的数小时训练。

## 可复现验收

[原目录交付验证](../experiments/20261003T201415.503267Z_delivery_validation/status.json)：固定val首场study-4410-0005，3模型各960物理步成功，240次visited observation的原/重载模型动作逐位相同。

[新目录搬迁验收](../experiments/20261003T202857.594683Z_relocation_verification/summary.json)：新Python3.11.17、独立.venv重装35锁定包，全26科研source哈希一致，relocated manifest通过；3模型val rollout状态和命令与原目录逐位相同。此项是同机新目录/环境复现，**不是第二台机器或跨平台保证**，也不是另跑500test。

新环境bootstrap初次失败的真实原因：PyTorch附加索引覆盖普通包而缺少锁定charset-normalizer版本。改为PyPI+Torch专用官方find-links，锁文件不变。editable安装重写冻结egg-info/SOURCES.txt，脚本事先核验并保留/恢复原字节，记录变更审计，不改科研源码。初始失败和修复日志保留在搬迁验收目录。

完整风险测试最新 **108 passed**；PDF9页逐页无裁切/重叠/缺字；视频原速、元数据和帧数验证通过。最终归档工具仅在所有输入/报告/视频校验和ZIP CRC通过后发布；发布状态与ZIP哈希以压缩包旁的receipt为准。

## 已完成与未完成的边界

已完成核心三组对照、3训练seed和100固定held-out目标，以及本机 GUI 交互入口和有界实跑验证。未做弧线、无未来参考独立训练消融、长期收敛研究、实机、移动障碍或更广工作空间测试。可选扩展不冒充已完成。

结论只适用于有界witness搜索筛选后的分布，非全局安全/可行性/无偏总体证明；240Hz离散检查不保证步间连续无碰撞。位置只跟踪三维工具点，不控制朝向。

课程截止由用户确认2026-11-20 23:59；老师允许完整AI辅助，目前用户独自推进。完整rubric、Canvas显示时区、原创代码50%计量口径、视频时长/答辩格式仍没有完整材料。工程继续推进，不虚构这些规则或成员贡献。提交前需用户核对个人身份与反思文字；没有自动上传Canvas。


## 2026-10-09：Gym Code and Report 阶段交付已准备，未提交

交付：[Panda_Gym_Code_Report.zip](../../gym-code-report-20261009/Panda_Gym_Code_Report.zip)，4,774,215 字节，78 项，SHA-256 `4bdbf29298e3037e6cd712661e11beef47bb84a69981961091ec0664959e81a0`。包含带注释代码、两页英文共用报告、environment.yml、README、可视化 demo、测试和证据；[中文说明](../../gym-code-report-20261009/交付说明_中文.txt)单独提供。归档 CRC/逐项哈希通过；报告两页均已渲染检查。

全新独立 conda-compatible 环境安装成功（micromamba 2.9.0、Python 3.11.17、Ubuntu 24.04.4 x86_64），最终 environment.yml 在第二个空环境实装通过，pip check 无冲突。[解压复跑证据](../../gym-code-report-20261009/panda-gym/evidence/relocation-verification.json)：9 passed（测试子进程墙钟约 3.01 s）；zero 有渲染约 7.38 s、random 无渲染约 1.36 s，时间口径不同，不据此比较控制器速度。

同一个固定 validation 场景的两种演示均960物理步/961检查状态完整成功：zero 最大误差0.024043 mm/最小球净空13.221081 mm；seed44 random 0.058236 mm/10.160397 mm。这两个回合仅验证环境运行，不是新成功率实验。解压副本的 q、qd、位置、参考、命令、误差、动作、观测、reward 与原预览逐位一致；witness 同限制物理 replay 测试通过。

未测试其他电脑、Windows/macOS 或可选浏览器自动打开。环境阶段实际截止日待确认；用户明确不代提交，因此没有 Canvas 上传、GitHub 推送或其他对外提交。原有未提交 GUI 变更保留，没有改变已冻结研究证据或最终大包。


## 2026-10-09：开始 final 结果审阅，独立复现训练后期退化

用户已将阶段包发给队友，队友复跑尚未收到证据。下一项个人工作是[结果解释与反思草稿](final_next_work.md)，工程继续推进，不等待队友或答题。

新增 [scripts/audit_learning_stability.py](../scripts/audit_learning_stability.py)，检查三 seed 共30条 validation checkpoint记录、历史选模规则与模型SHA；每条回合清单均24个相同validation场景，全部失败保留。seed144/145/146 的 selected 成功数分别19/17/18，最后更新模型18/1/17，分母均24；不能与test成功率混用。

[本次证据](../experiments/20261008T215230.514261Z_learning_stability_review/summary.json)：独立加载 seed145 final_model，实际重跑24个validation回合，成功1、碰撞8、限位15，与历史最终验证的成功/完成/原因/步数一致，误差、净空、回报差小于1e-10。新存24条轨迹确认joint2下界12次、joint6上界3次；这些限位回合均无最终电机速度裁剪，已执行前缀最大误差不超过约0.1030mm。历史最终验证没有保存逐步轨迹，因此未宣称新旧npz逐位一致。49个历史输入的前后哈希相同。

[训练稳定性审阅](learning_stability_review.md)包含新图、表、英文讨论段落和推理边界，尚未插入旧9页PDF。该诊断支持“较晚模型可能退化”，不识别唯一优化原因，不支持无条件延长训练。此次没有训练、test复评、改选模型或覆盖原报告/阶段ZIP。顺带纠正答辩文档中“没有正式测试案例”的过时句子，以及README将本地未提交GUI入口描述为已发布的问题。没有GitHub推送或Canvas提交。


## 2026-10-09：final 技术交付修订与搬迁验证

用户授权继续优化并完成final技术要求。当前 study_index 指向新十页英文技术报告、中文逐页解读、英文口述稿与52秒标注视频；旧报告/视频/研究保持。新增scripts/build_final_report.py、render_final_comparison.py、compose_final_demo.py、quickstart.py。未改冻结科学代码、阈值、模型选择、原500回合或阶段ZIP。

[验收证据](../experiments/20261008T222511.498438Z_final_delivery_review/summary.json)：108项风险测试8.57秒全部通过；原目录与新目录项目独立环境各验证三个模型，每模型960物理步、240个观测上保存/加载动作一致。35包从本地复制缓存安装，新环境复用3.11.17解释器；不冒称另一台电脑或此次重新验证联网bootstrap。搬迁q、qd、x、xref、command、error、time逐位相同，q/command最大差0。

报告10页（含参考文献）全部渲染审阅；最终版渲染与审阅版十页PNG逐字节一致。视频1560帧/30fps/52秒全解码，8张文字卡与两个物理片段首中末帧均检查；6个窗口完整关节重放差0。新增障碍箭头和颜色图例，第一个案例调整相机消除球体遮挡，不改变物理执行。

保留并纠正了报告过早读取第二视频、首次11页排版、只读uv缓存和外置venv冻结资产路径不匹配的尝试；都未标通过。完整本地ZIP状态以旁置receipt为准；[剩余事项](final_delivery_checklist.md)是个人署名/真实反思、其他参与成员的独立报告及未取得的课程细则。没有GitHub推送、Canvas提交、新训练或新test选模。


## 2026-10-09：授权将本地修订同步 GitHub

用户在技术交付验收后明确要求同步今天的完成内容，目标为既有公开仓库 kimzclandi/panda-obstacle-aware-posture-control。同步源码、十页英文报告、52秒标注视频、中文解读/英文口述稿、训练稳定性诊断和自动搬迁运行入口；完整ZIP及轻量环境阶段包经独立v1.1.0 Release分发。默认main在同步前与本地原HEAD一致；远程独立开发分支保留，不强制推送或改写历史。

完整ZIP保持前次实际解压验证过的原字节，SHA256为`4e417e3ae147c51fc7bcd3b82d6aede94c6defe0391a7729362ac09d1be3e7ae`。源码commit与ZIP生成时的provenance区别在Release正文说明。附件核验以Release资产SHA256和旁置发布receipt为证；该分发授权不等于课程平台提交，也不补全尚待本人核对的个人报告内容。


### GitHub 同步验收完成

[v1.1.0](https://github.com/kimzclandi/panda-obstacle-aware-posture-control/releases/tag/v1.1.0) 已公开并设为latest，发布tag指向`d301cdb9661a85c9f2a440e4e82d5064f4735ea8`。完整复现ZIP、receipt、解压验证、英文PDF、MP4、中文解读、英文口述稿、轻量环境ZIP和SHA256SUMS共九个附件，GitHub服务器端大小与SHA256全部匹配。

[发布核验记录](github_sync_20261009.json)：新克隆323个文件逐字节匹配、工作树干净；未登录API读取、校验和下载以及750,132,146字节完整ZIP下载入口HEAD均通过。README/About/Release介绍未检出学校、课程或组号标识；v1.0.0的所有附件ID、大小与digest保持不变。报告个人核对事项和不代提交课程平台的边界保持。此后仅增加这份发布记录，不改变release tag、模型或附件。


## 2026-10-09：本地运行入口与演示标注优化（未同步 GitHub）

最新用户要求暂不改动 GitHub。本轮本地增加 project_runtime 标准库预检、三个入口的自动搬迁处理、GUI 的红色球体标注/引线/颜色图例和中性标题。新增 12 项风险检查，覆盖缺少完整数据、错误解释器、依赖不匹配、路径越界/符号链接、搬迁失败不可回退，以及无科学依赖的 CLI 帮助。全部 **120 项测试通过，8.55 秒**。

证据目录：[local_entrypoint_review](../experiments/20261008T231154.964475Z_local_entrypoint_review/summary.json)。实际检查：

- 原目录 quickstart：三个选中 PPO 模型各完成同一固定 validation 场景 960 个物理步，并通过保存/加载动作检查。
- 另一个完整项目副本自动搬迁后重复三模型验证，均成功。时间、关节位置/速度、工具位置/参考/误差、原始/执行命令、饱和与投影泄漏十组数组，和修改前记录、原目录新记录逐位一致。三个模型该场景最大误差分别约 0.03988、0.03368、0.03299 mm；此为功能验收，不是新 test 成功率。
- 搬迁后的 GUI 输入也经完整冻结检查解析成功，无需手工指定 --freeze。没有打开原生 GUI。
- 演示循环通过独立 DIRECT 诊断（连接替换、取消显示等待）：Tracker/APF/PPO 各执行 960 物理步，十组数组与原通用 rollout 逐位一致。一次主动中断只执行 4 个物理步，记录 incomplete/failed 和 user_interrupted_demo，未误计成功。障碍标签调用及无课程标题均检查；实际 GUI 布局尚未目视验收。详见同目录 demo_direct_review.json 和保留的验证脚本。
- 1,265 个受保护文件前后 SHA256 不变，包括冻结科学输入、所绑定证据、最终报告/视频和发布 ZIP。ZIP SHA256 仍为 4e417e3ae147c51fc7bcd3b82d6aede94c6defe0391a7729362ac09d1be3e7ae。

搬迁检查复用了此前已安装验证的本地依赖副本，不声称又完成一次全新安装或跨电脑测试。验证编排曾使用错误的 review 指针，以及在准备路径前提前导入内部 runtime，均在物理执行前失败；更正记录保存在证据目录，未标作通过。既有 500 回合结果、模型选择与研究结论不变；本轮未开始训练、复评 test、修改 Git 历史或访问 GitHub。

后续可继续验收原生 GUI 的标注位置；算法改进应针对 PPO 训练稳定性另开 train/validation 实验，而非修改冻结测试集。个人报告真实反思/署名等既有待办仍保留。


## 2026-10-09：原生演示验收与独立学习率短实验

继续只在本地优化。已完成上一轮待办的原生 GUI 显示检查，并首次执行一个预先声明的学习率单因素诊断；原模型、原正式研究、最终报告/视频、已发布 ZIP 与 GitHub 保持不变。

**演示**：[最终截图与核验](../experiments/20261009T002646.585396Z_native_gui_review/visual_review.json)。实拍发现红球标签覆盖净空文字，将标签移到球侧面后重新拍摄 ready/completed，文字与引线清楚。默认 validation 的 PPO144 完成 960 物理步，十组状态/命令数组与旧 DIRECT 验证逐位相同。窗口自动关闭。首次三个截图定位尝试未运行轨迹：本机窗口管理器给客户窗口与外框同名，原按标题/数量判断失败；失败记录保留，最终使用 WM_STATE 定位。此前重叠标签截图也保留，未标为显示验收通过。

**训练诊断**：[详细英文附录与中文解读](learning_rate_diagnostic.md)，[实测汇总](../experiments/20261009T002444.484308Z_learning_rate_diagnostic/summary.json)。从同一历史选中 seed145 checkpoint 开始，原学习率 3e-4 与较低学习率 1e-4 各续训 12,288 decisions，continuation seed9145。相同初始 policy/optimizer 指纹、相同第一段 rollout 的六组数组；原 64 train/24 validation、不读 test 结果。先存计划再训练，固定最终端点，无追加预算或新模型选择。

| validation 成功数 | 共同起点 | 原学习率 | 较低学习率 |
| --- | ---: | ---: | ---: |
| 开始 | 17/24 | — | — |
| 新增 6,144 步后 | — | 17/24 | 16/24 |
| 新增 12,288 步后 | — | 15/24 | 17/24 |

最终两组失败均为碰撞（9 与 7），无关节限位失败；两者共同成功 14，仅较低学习率成功 3，仅原学习率成功 1，共同失败 6。较低学习率相对起点失去一个成功场景、得到另一个，不能写成每个场景都保住或已经超越起点。平均更新 approximate KL 为 0.01240/0.00558，共同观测上的策略均值 L2 drift 为 0.9866/0.5733；这是本次稳定性迹象，不识别历史长期退化的唯一原因。

总计初始验证加两组续训约 268.5 秒；训练吞吐（扣除 callback 验证，含特征/仿真/优化/日志）约 170/149 decisions/s。保存/加载在全部 4,803 个共同 probe 观测上动作一致。五次 validation 共 120 回合只是重复 24 场景，不是 120 个独立 held-out 样本。完整逐回合记录、轨迹、模型、训练日志、源快照与对照图已保存；首版图纵轴过长，保留原图并在 analysis_v2 修正，最终图已目视检查。

[工程核验](../experiments/20261009T002444.484308Z_learning_rate_diagnostic/engineering_verification.json)：当前 **128 项测试通过，7.97 秒**。本轮 29 个直接受保护输入、跨轮 1,265 个原始/最终交付文件哈希未变。用户两次“继续”期间原训练后台完成，恢复时只读取已有进程结果，没有重复启动。

下一优先级：固定同一方案、额外 continuation seed 验证趋势是否重复；未得到跨 seed 证据前不称学习率优化已稳定有效。正式泛化改进仍需新未见测试集。个人署名/真实反思等原有待办继续保留。


## v1.2.0 发布准备：工程改进和探索诊断

用户明确授权把已取得成果的优化发布 GitHub。本次发布统一启动/搬迁入口、原生 GUI 标注修复、12,288 步 × 两组学习率诊断、针对性测试及结果解读。公开 deliverables/updates_v1.2.0 提供逐字节复制的图像/诊断摘要和来源哈希；完整版保留全部原始记录。原冻结研究、选中模型和个人报告待办不变。

发布准备时远程 main 与本地基准 6b1e64c 一致；不修改其他分支或旧 Release。计划新建 v1.2.0 完整复跑包，并以其真实源代码提交、内容清单与实际解压检查作为分发证据。发布完成与否以随后添加的 GitHub 核验记录和在线 Release 为准，不把准备状态写成已经上传。


### v1.2.0 GitHub 发布与公开下载核验完成

用户说明断电并明确要求重试。恢复时已确认远程仍在旧提交、没有新 Release，且本地四个待上传附件哈希完好；随后成功推送 source commit `f2b8d66e6937c7765a71cb23c65fa19b646e1171` 与 v1.2.0 标签。新版本于 2026-10-09 00:55:42 UTC 公开并设为 latest：[v1.2.0 Release](https://github.com/kimzclandi/panda-obstacle-aware-posture-control/releases/tag/v1.2.0)。

[发布核验记录](github_sync_v1.2.0.json)：重新克隆的 340 个跟踪文件与发布提交逐字节一致；完整包 813,940,182 字节，6,728 个清单文件全部通过哈希核验，实际解压后新建项目环境、从离线缓存安装 35 个锁定依赖。解压环境 128 项测试通过，三个模型各完成 960 物理步，十组数组与原验证逐位一致。初次安装的默认 uv 缓存只读失败已保留，改用工作区缓存后成功；不冒称跨电脑或在线安装复验。

Release 四个附件的服务器大小/SHA256 匹配；三个小附件经未登录实际下载核验，完整 ZIP 的匿名 HEAD 返回 200。README、About 和 Release 介绍未检出学校/课程/组号标识；原始证据与历史仍保留，不声称整体匿名化。v1.0.0/v1.1.0 所有旧附件的 ID、大小与 digest 未变。ZIP SHA256：`573ca2440d7e80bef4ca464941a77a3124aca83d8512dd33e74e81de57f4ea1c`。

本段及发布记录是在分发完成后添加的文档；Release tag 和归档继续指向 f2b8d66 原发布内容，不为增加核验记录重打包或改写标签。未提交课程平台，探索诊断没有替代原正式模型或结论。
