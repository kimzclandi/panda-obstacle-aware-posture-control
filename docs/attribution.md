# 复用、许可证、AI 协助与贡献台账

本台账建立并核实于 2026-10-04。核实对象是本项目 `.venv/lib/python3.11/site-packages` 中的实际 wheel 元数据和许可文件；不是根据包名猜测许可证，也没有把主机已有 ROS 包算入项目依赖。完整版本、来源、原始许可元数据、notice 归档路径与 SHA-256 位于 [third_party/inventory.json](third_party/inventory.json)。

**这些第三方许可证不为本项目自编源码选择许可证。项目源码的发布许可由作者另行决定。** 安装的包不全部等于已使用的算法，更不计为项目自行实现的库。

## 已安装组件与来源

许可摘要保留 wheel 元数据的 `AND`/`OR` 关系；NumPy、SciPy、PyTorch、Matplotlib 等含附带组件，不能只用一个主库简称覆盖其全部许可。复制的全文按安装路径保存在 `docs/third_party/notices/`，不修改上游原文。

| 来源 | 实际版本 | 已核实许可摘要 | 项目用途 / 状态 | 已归档证据 |
| --- | --- | --- | --- | --- |
| [cloudpickle](https://github.com/cloudpipe/cloudpickle) | `3.1.2` | BSD-3-Clause | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/cloudpickle-3.1.2.dist-info/licenses/LICENSE) |
| [contourpy](https://github.com/contourpy/contourpy) | `1.3.3` | BSD-3-Clause | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/contourpy-1.3.3.dist-info/LICENSE) |
| [cycler](https://github.com/matplotlib/cycler) | `0.12.1` | BSD-3-Clause | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/cycler-0.12.1.dist-info/LICENSE) |
| [Farama-Notifications](https://github.com/Farama-Foundation/Farama-Notifications) | `0.0.6` | MIT | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/farama_notifications-0.0.6.dist-info/licenses/LICENSE) |
| [filelock](https://github.com/tox-dev/py-filelock) | `3.32.3` | MIT | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/filelock-3.32.3.dist-info/licenses/LICENSE) |
| [fonttools](http://github.com/fonttools/fonttools) | `4.66.1` | MIT；附带组件见 LICENSE.external | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/fonttools-4.66.1.dist-info/licenses/LICENSE) |
| [fsspec](https://github.com/fsspec/filesystem_spec) | `2026.7.0` | BSD-3-Clause | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/fsspec-2026.7.0.dist-info/licenses/LICENSE) |
| [gymnasium](https://github.com/Farama-Foundation/Gymnasium) | `1.3.0` | MIT | 已安装环境接口；不等于 PPO 环境已实现 | [本地许可](third_party/notices/gymnasium-1.3.0.dist-info/licenses/LICENSE) |
| [iniconfig](https://github.com/pytest-dev/iniconfig) | `2.3.0` | MIT | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/iniconfig-2.3.0.dist-info/licenses/LICENSE) |
| [Jinja2](https://github.com/pallets/jinja/) | `3.1.6` | BSD-3-Clause | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/jinja2-3.1.6.dist-info/licenses/LICENSE.txt) |
| [kiwisolver](https://github.com/nucleic/kiwi) | `1.5.1` | BSD-3-Clause | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/kiwisolver-1.5.1.dist-info/licenses/LICENSE) |
| [MarkupSafe](https://github.com/pallets/markupsafe/) | `3.0.3` | BSD-3-Clause | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/markupsafe-3.0.3.dist-info/licenses/LICENSE.txt) |
| [matplotlib](https://github.com/matplotlib/matplotlib) | `3.11.2` | Matplotlib 许可协议；附带字体等有各自许可 | 实验静态图表；阶段 1 已使用 | [本地许可](third_party/notices/matplotlib-3.11.2.dist-info/LICENSE) |
| [mpmath](https://github.com/fredrik-johansson/mpmath) | `1.3.0` | BSD-3-Clause | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/mpmath-1.3.0.dist-info/LICENSE) |
| [networkx](https://github.com/networkx/networkx) | `3.6.1` | BSD-3-Clause | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/networkx-3.6.1.dist-info/licenses/LICENSE.txt) |
| [numpy](https://github.com/numpy/numpy) | `2.4.6` | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | 矩阵计算与诊断；阶段 1 已使用 | [本地许可](third_party/notices/numpy-2.4.6.dist-info/licenses/LICENSE.txt) |
| [packaging](https://github.com/pypa/packaging) | `26.3` | Apache-2.0 OR BSD-2-Clause | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/packaging-26.3.dist-info/licenses/LICENSE) |
| [pillow](https://github.com/python-pillow/Pillow) | `12.3.0` | MIT-CMU | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/pillow-12.3.0.dist-info/licenses/LICENSE) |
| `pluggy`（元数据未提供 URL；[PyPI](https://pypi.org/project/pluggy/)） | `1.6.0` | MIT | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/pluggy-1.6.0.dist-info/licenses/LICENSE) |
| [pybullet](https://github.com/bulletphysics/bullet3) | `3.2.7` | Zlib；附带资源另有许可 | 物理、Jacobian、关节电机、碰撞；阶段 1 已使用 | [本地许可](third_party/notices/pybullet-3.2.7.dist-info/LICENSE.txt) |
| [Pygments](https://github.com/pygments/pygments) | `2.21.0` | BSD-2-Clause | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/pygments-2.21.0.dist-info/licenses/LICENSE) |
| [pyparsing](https://github.com/pyparsing/pyparsing.git) | `3.3.3` | MIT | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/pyparsing-3.3.3.dist-info/licenses/LICENSE) |
| [pytest](https://github.com/pytest-dev/pytest) | `9.1.1` | MIT | 关键逻辑测试 | [本地许可](third_party/notices/pytest-9.1.1.dist-info/licenses/LICENSE) |
| [python-dateutil](https://github.com/dateutil/dateutil) | `2.9.0.post0` | Apache-2.0 / BSD-3-Clause，适用范围见全文 | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/python_dateutil-2.9.0.post0.dist-info/LICENSE) |
| [scipy](https://github.com/scipy/scipy) | `1.17.1` | BSD-3-Clause；wheel 附带库许可见全文 | 已安装数值工具；具体使用以代码导入为准 | [本地许可](third_party/notices/scipy-1.17.1.dist-info/LICENSE.txt) |
| [setuptools](https://github.com/pypa/setuptools) | `78.1.0` | MIT；vendored 组件另有许可 | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/setuptools-78.1.0.dist-info/licenses/LICENSE) |
| [six](https://github.com/benjaminp/six) | `1.17.0` | MIT | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/six-1.17.0.dist-info/LICENSE) |
| [sympy](https://github.com/sympy/sympy) | `1.14.0` | BSD-3-Clause | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/sympy-1.14.0.dist-info/licenses/LICENSE) |
| [torch](https://github.com/pytorch/pytorch) | `2.14.1+cpu` | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT | 已安装 CPU 深度学习后端；不等于模型已训练 | [本地许可](third_party/notices/torch-2.14.1+cpu.dist-info/licenses/LICENSE) |
| [typing_extensions](https://github.com/python/typing_extensions) | `4.16.0` | PSF-2.0 | 已安装间接或构建/测试依赖 | [本地许可](third_party/notices/typing_extensions-4.16.0.dist-info/licenses/LICENSE) |
| [Stable-Baselines3](https://github.com/DLR-RM/stable-baselines3) | `2.9.0` | MIT | PPO 框架已安装；不等于模型已训练 | [本地许可](third_party/notices/stable_baselines3-2.9.0.dist-info/licenses/LICENSE) |

## Panda 模型资产：与 PyBullet 本体许可分开

- 来源：本机 PyBullet 3.2.7 wheel 的 `pybullet_data/franka_panda/`，由 [Bullet 上游项目](https://github.com/bulletphysics/bullet3) 随包分发；没有声称自建模型。
- 安装目录 `franka_panda/LICENSE.txt` 明确为 **Apache License 2.0**，已原样保存为 [Panda 资产许可](third_party/notices/pybullet_data/franka_panda/LICENSE.txt)。PyBullet dist-info 的本体许可为 Zlib，二者不能混写。
- 使用内容：`panda.urdf` 及它引用的碰撞/可视 mesh。URDF 头部说明它由 `panda_arm_hand.urdf.xacro` 自动生成；这不是本项目原创模型。
- 当前通过安装包路径读取模型，没有对 Panda 资产做项目内修改。模型身份与碰撞形状由实验 metadata 记录。后续如复制或修改资产，保留原许可及来源并记录具体改动。
- `inventory.json` 还可能包含 wheel 内其他未使用资产的许可。归档许可不意味着项目使用了那些资产；当前研究机器人仅为 Panda。

## 学术来源与 AI 协助

| 来源 | 用途 / 归属 |
| --- | --- |
| Khatib 1986，DOI `10.1177/027836498600500106` | 人工势场研究背景；引用思想不等于自行提出算法；实际实现另记。 |
| [Schulman et al. 2017](https://arxiv.org/abs/1707.06347) | PPO 方法来源；项目贡献是控制和评估，不声称提出新 PPO 算法。 |
| OpenAI Codex | 本次工程、诊断、测试、文档和教学协助。用户确认老师允许完全 AI 辅助且不要求特别标注；该记录是内部工作来源，不另设提交义务。代码实现不等于用户已经掌握。 |

## “至少 50% 原创项目代码”边界

Proposal 明确作出至少 50% 原创项目代码的承诺，但课程截图也要求至少 50% from scratch，并披露复用来源；当前没有对分母、AI 辅助代码计入方式、配置、测试、注释、样板、生成文件和依赖的正式统计定义。用户已确认允许完全 AI 辅助且不需要特别标注，这不自动定义“50%”的统计口径。不能用项目代码行数、删除依赖代码、AI 生成量或自定义统计直接宣称满足。

待课程确认后记录：规则原文与版本、计量对象、复用片段出处、AI 辅助代码在原创比例中的计入方式、实际参与者贡献和最终复核方法。当前可审查的原创工作方向是任务环境、共享控制与执行接口、全臂势场组合、验证诊断、场景与 witness 管线、公平评估与失败分析；这仅是归属候选，不是比例结论。

## 成员贡献

Proposal 列出的成员为 LIN KAIHAO、LIU LINJUN、WANG KEXIN。用户确认目前独自开展项目。只记录用户实际完成的审阅、独立复跑、理论解释和报告贡献，不根据 proposal 名单虚构其他成员分工，也不把 AI 完成的实现记成某位成员已独立编写。允许 AI 协助的课程政策不免除用户理解、核验与答辩准备。

每次里程碑后建议追加下表，证据指向 commit、实验 ID 或审阅记录。

| 日期 | 实际参与者 | 工作内容 | 复用/AI 协助 | 可核验证据 | 本人复跑或解释确认 |
| --- | --- | --- | --- | --- | --- |
| 2026-10-04 | Codex（AI 协助） | 首轮规格、决策与教学文档草拟 | 基于用户需求与 proposal | 本目录文件；具体工程实测见 progress | 学生掌握尚未确认 |
