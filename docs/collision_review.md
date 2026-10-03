# Panda collision review — 2026-10-04

本文件是独立碰撞诊断，**不是控制器 rollout、动态可行 witness 或成功率实验**。诊断允许使用 `resetJointState` 指定测试姿态；正式执行必须由 motor 与 `stepSimulation` 推进。

## 实际模型与检查范围

已在项目 `.venv` 中实测 PyBullet **3.2.7**。使用安装包中的 `pybullet_data/franka_panda/panda.urdf`，SHA-256 为 `9c27cf846302e26a1d3a44ccfd4dd2dbba89cccc9f17b96b6bd1f8bceedd1ff0`。实际 `getJointInfo` 与 collision-shape 信息完整保存在 [collision_review_evidence.json](collision_review_evidence.json)。生产代码应按名称解析，不能把以下诊断索引直接当成其他 URDF 的通用索引。

| Link | 当前 PyBullet index | Collision geometry |
|---|---:|---|
| `panda_link0` | -1 | 有，固定基座也需要检测障碍物 |
| `panda_link1` … `panda_link7` | 0 … 6 | 有 |
| `panda_link8` | 7 | 无，仅固定连接坐标框架 |
| `panda_hand` | 8 | 有 |
| `panda_leftfinger`, `panda_rightfinger` | 9, 10 | 有 |
| `panda_grasptarget` | 11 | 无，仅工具坐标框架 |

共 11 个有碰撞几何的 link，产生 55 个无序自身 link 对。建议只排除下表 10 对，保留 **45 对**。整条机械臂、手掌、两个手指对外部球体均检查，不套用自碰撞排除表。

## 最小排除表

机器可读版本：[collision_exclusions.json](collision_exclusions.json)。

| 排除的 link 对 | 原因与证据 |
|---|---|
| `link0–link1`、`link1–link2`、`link2–link3`、`link3–link4`、`link4–link5`、`link5–link6`、`link6–link7` | 直接父子关节的安装连接。初始姿态全部有 mesh 结构性重叠，作为自碰撞失败会误报。|
| `panda_link7–panda_hand` | 跨越无 collision geometry 的 `panda_link8`，由两个 fixed joints 构成同一刚体结构；实测结构性穿透 25.192 mm。|
| `panda_hand–panda_leftfinger`、`panda_hand–panda_rightfinger` | 直接父子滑动导轨连接；初始姿态约 9.4 mm 结构性重叠。|

这里的简写 `linkN` 均指 `panda_linkN`。左右手指之间**仍检查**：本诊断将每个手指固定在 0.02 m 开度，二者净空 37.786 mm。若项目改为完全闭合或更换手部资产，需重新核查其闭合接触语义，不应静默沿用结论。

不要把“树上距离不超过两跳”作为排除规则。本地实测 `panda_link5–panda_link7` 会穿透；这正是一组相距两跳但必须保留的检查对。也不要直接复制另一模型的 `Never` 列表。MoveIt 的参考 SRDF 有更宽排除集合，并保留 `link5–link7` 和 `link5–hand`；其碰撞网格与本项目 PyBullet 资产并非已证明完全等价。[MoveIt Panda SRDF](https://github.com/moveit/moveit_resources/blob/ros2/panda_moveit_config/config/panda.srdf)

## 已验证的阴性与阳性

初始化关节姿态按 `panda_joint1` … `panda_joint7` 排列，单位 rad：

```text
[0, -π/4, 0, -3π/4, 0, π/2, π/4]
```

手指各 0.02 m。保留的 45 对均无穿透；最小自身净空为 `link5–link7` 的 **20.155 mm**。

通过固定 seed 4401 的 102 个静态关节样本，找到了多类非邻接碰撞（完整姿态及距离在 JSON）。样本只用于发现阳性，不证明所有未观测碰撞对永不碰撞。

| 阳性 | 关节姿态 q [rad] | 实测 signed distance |
|---|---|---:|
| `link5–link7` | `[1.2273453761, -0.0392911895, 0.7438507561, -1.5157461395, -0.3604113596, -0.0120660168, -1.1324857044]` | -9.725 mm |
| `link2–hand` | `[-1.1678255020, 0.1299682115, 2.3894241366, -2.9121779553, -0.8102254262, 0.1845382658, -2.5607094308]` | -13.175 mm |
| `link5–hand` | `[1.1775434176, 0.5880519928, 1.5149655089, -2.9130405596, -1.1436613140, 0.1128037008, -0.2405583559]` | -44.302 mm |

以上姿态仅验证检测能力，不应当作为机器人应执行到的目标姿态。

在同一初始化姿态，把半径 0.04 m 的静态球放在目标 link 的 world AABB 中心，分别验证 arm、hand、左右 finger：

| 目标 | 球心 [world m] | 对该 link 的 signed distance |
|---|---|---:|
| `panda_link3` | `[-0.1708452023, 0.0281428993, 0.5624750985]` | -94.641 mm |
| `panda_hand` | `[0.3068805176, 0.0017820001, 0.5702633509]` | -68.237 mm |
| `panda_leftfinger` | `[0.3068982169, -0.0331353781, 0.5048917041]` | -50.173 mm |
| `panda_rightfinger` | `[0.3068829162, 0.0331353781, 0.5048917041]` | -50.173 mm |

每一种都同时由 `getClosestPoints` 与 `performCollisionDetection` 后的 contact list 检出目标 link；球可能同时穿透其他 link，这是有效的检测阳性而不是可用避障场景。

## 查询与物理碰撞过滤必须分别处理

本地实测：`setCollisionFilterPair(..., enableCollision=0)` 之后，显式 `getClosestPoints` 仍能报告该排除对的穿透。例如被排除的 `link7–hand` 仍返回 -25.192 mm。**不能认为物理 contact filter 会自动替代几何查询的排除表**。生产碰撞判据必须明确按保留的 45 对查询，或显式过滤返回结果。

同时，`getContactPoints` 的存在不等同于 penetration：诊断中接触缓存包含 signed distance 为 +0.886 mm 的条目。因此要依据 signed distance 和预先固定的数值容差判定，不宜只判断列表是否非空。推荐正式指标同时保存最小 signed distance 与碰撞 Boolean，在配置中明确 `distance < -epsilon` 的穿透失败边界；若要求表面接触也失败，则应使用带小正安全余量的独立规则并一致应用于 A/B/C。

加载时启用 `URDF_USE_SELF_COLLISION`，再依据相同排除表配置物理接触。无需全祖先/全部两跳的全局禁检 flags。几何查询覆盖全部相关 pairs，不以物理引擎默认 flags 代替项目规范。

## 可复跑

在项目根目录执行；输出路径必须尚不存在以免覆盖历史证据：

```bash
.venv/bin/python docs/collision_diagnostic.py --output experiments/collision-check-new.json
```

本次输出：[collision_review_evidence.json](collision_review_evidence.json)。源脚本：[collision_diagnostic.py](collision_diagnostic.py)。脚本从 `getJointInfo` 解析 link 名称、父子关系和实际关节索引；随机诊断使用 URDF 硬限位内缩 0.04 rad，初始化手指 0.02 m。102 个样本及球诊断耗时约 0.09 s，仅为静态诊断吞吐，**不能当作动态仿真吞吐或训练估计**。

## 边界与尚未验证事项

- 上述检测对应本次 URDF、convex collision meshes 和 PyBullet 碰撞余量，并不是 Franka 实机精确外形认证。[Bullet 官方 Panda URDF](https://github.com/bulletphysics/bullet3/blob/master/examples/pybullet/gym/pybullet_data/franka_panda/panda.urdf)
- 未证明排除集合对所有可替换资产通用；资产或手指配置变化时需重新验证。
- 未验证所有姿态中接触响应的物理真实性；阳性诊断只要求检测层能发现已知穿透。
- 每个 simulation substep 后检测只能给出该离散频率下的安全证据，不构成 continuous collision detection 或连续时间安全保证。正式 rollout 需固定检查频率，保留最小净空，报告步长。
- 在创建训练场景前，需要把此诊断逻辑接入 production `collision_report` 的关键测试，避免诊断脚本正确而正式环境漏掉手部。

## 与阶段 1 正式实现的一致性复核

随后读取并实际实例化 `src/panda_posture/robot.py:Panda`，将运行时 `excluded_pairs` 按 link 名称转为无序集合，与本报告的 `collision_exclusions.json` 逐对比较：**集合完全相同，10 对排除、45 对检查**。`panda_leftfinger–panda_rightfinger` 保留；`link5–link7` 保留。正式 `collision_report` 显式遍历保留的自身 pairs，并对 robot–sphere 查询全部 link，因此不依赖 contact filter 替代几何查询。物理过滤也使用同一集合。

当前 `configs/stage1.json` 使用另一组初始化关节角 `[0,-0.45,0,-2.25,0,1.85,0.75]`，本次复核该姿态最小自身净空为 **20.307 mm**，无碰撞。当前正式失败边界为 **signed distance ≤ +0.00001 m**（10 μm 正安全余量），比仅负距离穿透判据略保守；自碰撞与障碍物采用相同边界。初始化及每个 1/240 s 仿真步后的状态均检查，仍不构成连续时间保证。

同时独立读取已保存的 `20261003T190517.323145Z_stage1_tracker` 与 `20261003T190635.999214Z_stage1_replay` 轨迹，两者均为 **960 个物理命令、961 个已检查状态**，`command[k]` 对齐区间 `[time[k], time[k+1]]`，保存误差与 `norm(xref-x)` 重新计算结果完全一致。重放 q 与来源 q 最大差为 0 rad。时间统计边界明确：decision 包含状态/参考/几何查询/跟踪计算，step 包含电机命令提交和 `stepSimulation`；未把渲染与磁盘写入算作在线控制时间。此复核只针对阶段 1 保存证据，不代表带障碍的场景或学习控制器已经验证。
