# 全臂人工势场次级控制器

本文件描述阶段 2 的实现选择，不是 proposal 已指定的算法，也不是调参已经完成的证明。实现位于 `src/panda_posture/secondary.py`；共享投影、动作缩放和电机执行仍由 `control.py`、`task.py`、`robot.py` 完成。

## 接口与信息范围

`PotentialField(params=None)` 可作为 `controller(task)` 调用，输出有限的 `(7,)` 无量纲 action，范围 `[-1,1]`。输入 `task.robot`、`task.cfg`、`task.state['q']`；不读取 witness、未来机器人状态或其他控制器轨迹，不改参考轨迹或时间。`name='potential'` 用于记录标签。

同一套机器人和几何信息也向学习控制器开放。`robot_distance_features(robot, max_distance=0.5)` 返回形状 `(11,4)`：按 `robot.collision_links` 顺序，每行是 `[clip(d/max_distance,-1,1), nx,ny,nz]`，分别为归一化有符号距离和世界坐标法向。无障碍或超查询范围用 `[1,0,0,0]`。这组数是截断的几何特征，不能用于宣称超查询范围的准确净空；最终碰撞判据仍独立检查。

碰撞几何覆盖 base、七个 arm links、hand、左右 fingers；工具空 link 没有碰撞形状，因此不单独加入。自碰使用已审查的 45 对 `self_pairs`，不扩大排除范围。每个 link/自碰对使用最近一对几何点，避免仅用工具到球心距离。在一个物体包含多个碰撞子形状时，最小距离仍是保守安全监测量；这里的梯度为最小距离的局部分支。

## 公式、坐标与单位

Bullet closest-point 元组的 `point[5]` 是 A 上的世界点、`point[6]` 是 B 上的世界点，`point[7]` 是 **B 指向 A** 的世界单位法向 `n`，`point[8]` 是有符号距离 `d`（m）。正数为分离，负数为穿透。

静态障碍物：`g = n.T @ J_A`；自碰：`g = n.T @ (J_A - J_B)`。`J_A/J_B` 形状 `(3,7)`、单位 m/rad，`g` 形状 `(7,)`、单位 m/rad。基座固定，所以其 Jacobian 为零。

每项采用有限作用范围的经典逆距离势场：

`U(d) = eta/2 * (1/d - 1/d0)^2`，仅在 `d < d0` 内激活。

下降势能对应增加净空的速度 `u = eta * (1/d - 1/d0) / d^2 * g`。`eta` 的实现单位为 rad²·m²/s，因此速度为 rad/s。计算时用 `max(d, distance_floor)` 正则化导数，使接触附近不出现数值发散；这相当于在 floor 以下将斥力大小封顶，不能称为严格的无限 barrier。势场只在零空间内间接改变姿态，不保证避障。

关节限位使用软边界区：距下界小于 `joint_margin` 时给正速度，距上界小于该区时给负速度；权重是归一化剩余边界余量的平方。`joint_gain` 为 rad/s，`joint_margin` 为 rad。靠近多个约束时三项可能互相抵消；越过限位也不会被这一项“合法化”。碰撞与限位失败由共享监测锁存。

各几何项与关节项相加得到 `u_raw`，除以共享 `secondary_speed_limit` 后逐分量裁剪到 `[-1,1]`；共享控制器再把 action 缩放回速度、做 SVD 零空间投影、与主任务相加并进行最终速度限制。`last_diagnostics` 保存三个原始速度项、未限幅总量、action 裁剪维度和控制计算耗时。必须结合共享最终命令饱和、投影泄漏与跟踪误差解释实际行为。APF 在 action 裁剪前的幅值再大，也没有比 PPO 更高的电机权限。

## 点 Jacobian 为什么需要单独验证

Panda 所有运动碰撞 link 都有非零惯性 COM 平移。直接把世界最近点减去 COM，再作为 link 原点偏移传给 Jacobian，会给出错误梯度。`Panda.link_frame` 从双精度 COM pose 与局部惯性变换重建 URDF link frame；`point_jacobian` 把世界点转换到从 URDF link 原点度量的局部位置。已安装的 Panda 惯性旋转均为 identity；实现仍显式处理该旋转，其他资产必须重新诊断。

官方 [Bullet Jacobian 示例](https://github.com/bulletphysics/bullet3/blob/master/examples/pybullet/examples/jacobian.py) 与 [Quickstart Guide](https://raw.githubusercontent.com/bulletphysics/bullet3/master/docs/pybullet_quickstartguide.pdf) 对局部点文字描述有歧义，因此本项目不以文字解释代替实际有限差分。验证固定同一个 link 上的材料点，在扰动关节后重新通过 link pose 求该点世界坐标；距离梯度验证则重新执行 closest-point 查询，允许最近点随几何运动改变。只有诊断使用 `resetJointState`；在线势场既不重置也不步进机器人。

## 已执行的关键验证与成本

`env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/test_secondary.py -q`：新增 16 项测试通过（首次 1.48 s）。包括：三个非零姿态、所有碰撞 links 的非原点 Jacobian；两个姿态各 link 的球距离梯度；五组自碰距离梯度、固定 finger-pair 的近零梯度；全臂/手/指特征覆盖；限位排斥方向；无在线 reset/step；非有限参数、状态与动作尺度拒绝。

初始姿态的独立诊断观察：所有运动碰撞 link 点 Jacobian 最大绝对差约 `1.4e-11 m/rad`，球距离梯度最大差约 `1.9e-8 m/rad`，所查自碰距离梯度最大差约 `1e-10 m/rad`。这不是所有配置的统一误差上界；测试容差考虑最近特征切换。

开发机器 CPU、DIRECT，home 姿态加球心 `(0.35,0.18,0.45)` m、半径 `0.04` m，20 次预热后 500 次重复调用：APF 平均约 **1.274 ms/decision**，几何特征平均约 **0.115 ms/call**。该布局有 2 个球近邻 link、5 个近距离自碰对。APF 计时包含几何查询、必要点 Jacobian、各项组合与 action 裁剪，不含主任务、物理步进或文件输出；它是固定姿态微测量，不能替代完整 rollout/训练吞吐。只对接近的自碰对计算 Jacobian，但每次查询全部 45 个保留自碰对。若控制器以 action repeat 运行，应三组控制器共享相同频率，主跟踪与碰撞检查仍逐物理步执行。

## Validation 调参与失败解释

当前默认：`influence_distance=.12 m`、`obstacle_gain=.0004`、`self_influence=.06 m`、`self_gain=.00008`、`distance_floor=.015 m`、`joint_margin=.3 rad`、`joint_gain=.4 rad/s`，均只是开发起点。只能根据 validation 完整成功率选参数，不以 test 或有利视频筛选。

建议先测试 `influence_distance` 为 `.08/.12/.18`，`obstacle_gain` 为 `.0001/.0004/.0012`；保留明确预先规定的组合和并列选择规则（先成功率，再失败率/净空或控制成本）。随后视 validation 失败原因调整自碰与关节项，报告完整候选范围和预算。势场作用距离过短可能来不及避让；过长会使多个链接斥力抵消或引起无必要运动。高 gain 可能频繁 action 饱和并扭转梯度方向，不能假定更大更强；低 gain 可能只在已经不可挽回时有微小响应。

局部势场会陷入局部极小值、受最近几何特征切换影响，也可能在主任务零空间投影后几乎没有有效避障方向。近未来轨迹信息可被公平提供，但当前 APF 是反应式几何场；不要将这一点误称为传统方法的理论上限。除非正式比较已完成，不宣称 PPO 超过 APF，也不将 witness 搜索失败当成不可行证明。
