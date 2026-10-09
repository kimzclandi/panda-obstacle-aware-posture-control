# 训练稳定性审阅：选中的模型与训练最后的模型

2026-10-09。此次只审阅历史 train/validation 记录，并独立加载 seed 145 的最终 checkpoint，在原 24 个 validation 场景实际执行。没有训练、修改控制器、改变选模、访问 test 回合结果或覆盖历史实验。原测试结论保持不变。

证据：[汇总与逐限位案例](../experiments/20261008T215230.514261Z_learning_stability_review/summary.json)、[全部验证检查点 CSV](../experiments/20261008T215230.514261Z_learning_stability_review/validation_history.csv)、[输入哈希](../experiments/20261008T215230.514261Z_learning_stability_review/input_sha256.json)。49 个历史输入在分析前后哈希一致。新代码和实际依赖保存在本次 run 的 provenance 与 source snapshot。

## 1. 已确认的事实

每个格子都以同一组 24 个 validation 场景为分母；不是 test 成功率。

| PPO seed | 未训练初始策略 | 选中检查点步数 | 选中模型 | 最后更新后模型（98,304 步） |
| --- | ---: | ---: | ---: | ---: |
| 144 | 17/24 | 61,440 | 19/24 | 18/24 |
| 145 | 17/24 | 12,288 | 17/24 | 1/24 |
| 146 | 17/24 | 49,152 | 18/24 | 17/24 |

初始策略未训练，按原协议不能参加模型选择。三个选中检查点都符合原始词典序规则：成功率优先、碰撞率次之、完成率再次之，完全并列时取最早已训练模型。最后一次优化后的模型也参加了原验证。此次重新计算只是核对历史规则，没有替换 checkpoint。

![验证成功数与训练步数](../experiments/20261008T215230.514261Z_learning_stability_review/validation_stability.png)

圆点是在当次 rollout 收集期间、该次优化更新前测得的检查点；星号是最后一次优化完成后的模型；方框是历史选中模型。24 个场景重复用于选模，不把曲线点当成独立样本，也不把选中峰值当作无偏泛化估计。

seed 145 的验证成功数从选中时 17/24 逐渐下降，在 86,016 步为 3/24，最后为 1/24。三个 seed 的初始策略都是 17/24，但其网络和轨迹不因此相同；成功数相同不证明没发生学习。

## 2. 对 seed 145 最后模型的独立复跑

从磁盘加载 final_model.zip，核对它与历史 training_summary 中的 SHA-256；在相同模型、初态、轨迹时间和执行器约束下实际重跑 24 个 validation 回合。成功、完成、失败原因和步数与原记录一致；最大误差、最小障碍净空、回报与原记录的绝对差均小于 1e-10。历史最终验证没有存逐步 npz；本次另存了全部 24 条轨迹，因此不声称和不存在的旧逐步数组逐位比较。

最终分解：**成功 1、碰撞失败 8、关节限位失败 15**，没有遗漏失败分母。

| 新轨迹检查到的限位类型 | 回合数 |
| --- | ---: |
| panda_joint2 越过下界及数值容差 | 12 |
| panda_joint6 越过上界及数值容差 | 3 |

15 次限位均在首次采样到越界时终止，逐回合时间、前后关节角、执行命令和上下界见 summary.json。它们在已执行前缀中均未出现最终电机速度目标裁剪；最大工具位置误差的最大值约 0.1030 mm，最大投影泄漏约 3.95e-16 m/s。小工具误差和小零空间泄漏并不能使关节限位失败变成成功。这些误差只属于失败前缀，不用来宣称完整轨迹性能更好。

此处的 12+3 限位失败属于 **seed 145 的最后模型在 validation 上的表现**，不能与既有 test 中 **选中的 seed 146 模型的三次 joint6 失败**混淆。两个模型、数据集和比较目的不同。

## 3. 可以写入报告的结论与仍待验证的解释

直接支持：固定这套超参数、预算和验证集时，继续训练没有使所有 seed 持续改善；seed 145 明显退化。仅交付训练最后的模型会丢失原 validation 选择保留下来的较好模型。工程运行完成、模型可加载、训练稳定和达到收敛是不同结论。

尚不能确认：具体由学习率、PPO 更新幅度、动作分布、有限场景覆盖、奖励权重或它们的相互作用造成。独立重跑复现了行为与失败类型，并没有识别优化过程的唯一原因。不能因为看到 test 上 PPO 落后，就把原因一概归为“训练步数少”。

以下实测分析已纳入 2026-10-09 final 技术报告第 7 页；它不代替个人反思：

> Validation performance was not monotonic with training. The selected checkpoints succeeded in 19/24, 17/24 and 18/24 scenes for seeds 144, 145 and 146, whereas their final updated models succeeded in 18/24, 1/24 and 17/24. An independent replay of seed 145's final checkpoint reproduced one success, eight collision failures and fifteen joint-limit failures. Twelve limit failures crossed the lower bound of panda_joint2 and three crossed the upper bound of panda_joint6. This deterioration motivates distinguishing a validation-selected checkpoint from the last training checkpoint. It does not establish insufficient training, a particular optimization mechanism, or a guaranteed benefit from extending the budget. All these comparisons reuse the selection validation set and are descriptive diagnostics, not additional held-out estimates.

## 4. 是否立即增加训练

当前优先完成结果解释和定稿。此审阅不支持无条件延长相同训练来期待稳定改善。若后续开展学习稳定性改进，应先声明一个具体假设、只改变一个主要因素、使用 train/validation 做有限预算诊断并保存新输出。已有 test 已被观察；要对改进后的方法作新的独立泛化结论，需要另行预先冻结新方案和未见测试集。当前不启动长训练，也不把新假设写成已验证结果。

可复跑本次诊断（创建新实验目录；24 个 validation 回合，无训练）：

```bash
env -u PYTHONPATH OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python scripts/audit_learning_stability.py
```

后续更新：已另立计划并完成[学习率短诊断](learning_rate_diagnostic.md)。两组从同一已选模型续训各 12,288 步，最终 validation 15/24 与 17/24，起点17/24；较低学习率的策略变化更小，但尚不能识别这里记录的长期退化原因。原审阅证据、模型选择和正式测试保持不变。
