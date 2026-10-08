# 项目进度与证据

更新时间：2026-10-04（Asia/Singapore）。UTC 实验目录时间比本地日期早一天属正常换算。历史阶段1/pilot记录保留于 [progress_history_stage1_to_pilot.md](progress_history_stage1_to_pilot.md)；原始实验和失败记录均未覆盖。

## GitHub 发布

2026-10-04 已上传至 [kimzclandi/panda-obstacle-aware-posture-control](https://github.com/kimzclandi/panda-obstacle-aware-posture-control)。最初以 private 发布；随后用户明确表示已征得同意并要求公开，现已改为 **public**，仓库与 Release 可公开查看和下载。原五次 Git 提交全部保留；`main` 另含发布文档更新，`v1.0.0` 指向完整实验包对应的原提交 `62d74a5`。

[Release v1.0.0](https://github.com/kimzclandi/panda-obstacle-aware-posture-control/releases/tag/v1.0.0) 已发布完整 ZIP（716,482,807 字节）、打包 receipt、独立英文 PDF、MP4 及 `SHA256SUMS`。GitHub 返回的五个附件字节数与 SHA-256 均与本地一致。完整 ZIP 的 SHA-256 为 `52c9a77d28a992bc1e03ba0465d47bcce1f4d3a55c7ff8e63c7af3e14b85958b`。

已从远程重新克隆并逐文件核对 281 个 tracked 文件，历史、tree 和 tag 对应关系正确；原科学输入冻结检查再次通过。本次只更新发布文档，没有重新训练或修改原始实验。Git checkout 不包含 experiments 和冻结安装元数据，冻结模型验证必须下载完整 Release ZIP 并按搬迁流程运行。此项是 GitHub 存档发布，未上传 Canvas。

## 当前完成范围

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

已完成核心三组对照、3训练seed和100固定held-out目标。未做弧线、无未来参考独立训练消融、长期收敛研究、GUI体验、实机、移动障碍或更广工作空间测试。可选扩展不冒充已完成。

结论只适用于有界witness搜索筛选后的分布，非全局安全/可行性/无偏总体证明；240Hz离散检查不保证步间连续无碰撞。位置只跟踪三维工具点，不控制朝向。

课程截止由用户确认2026-11-20 23:59；老师允许完整AI辅助，目前用户独自推进。完整rubric、Canvas显示时区、原创代码50%计量口径、视频时长/答辩格式仍没有完整材料。工程继续推进，不虚构这些规则或成员贡献。提交前需用户核对个人身份与反思文字；没有自动上传Canvas。

## 2026-10-09：公开阅读与复现入口维护

只读核验当前 GitHub 默认分支后，修复中文 README 的 12 处完整包专用实验链接，并同步复现说明，增加覆盖结果、协议、控制机制、运行入口与边界的英文 README。依赖标准库的导航检查通过：3 份维护入口、68 个本地链接、1 个 Markdown 锚点。Release 的 ZIP、PDF、视频、receipt 和 SHA256SUMS 五个链接均返回 HTTP 200；小型 receipt 与校验和相互一致。未下载大 ZIP、未重新验证包内全部 6,231 个文件。

本轮在 macOS 做文档检查，没有项目锁定的 Linux CPython 3.11.17 环境和冻结资产，未运行物理全套测试、模型交付验收、固定 500 回合或训练。既有全套测试包含 PPO 学习 smoke test；本轮不启动训练。新增 CI 仅守护导航，不替代此前研究验收，也不把历史 108 项测试写成本轮实测。
