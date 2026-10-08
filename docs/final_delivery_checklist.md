# Final 技术交付验收与剩余个人事项

本地修订日期：2026-10-09。机器可读证据：[review summary](../experiments/20261008T222511.498438Z_final_delivery_review/summary.json)、[PDF/视频检查](../experiments/20261008T222511.498438Z_final_delivery_review/visual_review.json)。文件入口统一由 study_index.json 指向；本地打包不等于提交。

| 截图中的 final 要求 | 当前文件与证据 | 状态 |
| --- | --- | --- |
| 完整训练代码 | src/panda_posture/train.py，README 实际训练命令、冻结配置、三 seed 日志 | 已具备 |
| 简单 validation/testing | scripts/quickstart.py 自动搬迁与三模型验证；scripts/run_frozen_test.py 完整复评 | 本机与新目录独立环境通过 |
| 至少一个已训练 functional model | 三个 training/*/best_model.zip，validation 选模、独立保存加载和实际执行记录 | 三个均验证可用；不声称收敛 |
| 精确依赖和 README | Python 3.11.17、35 包 requirements.lock.txt，CPU / DIRECT 安装运行说明 | 实装与运行通过 |
| 每人 <=10 页英文报告 | deliverables/final_20261009/report_en_v2/final_report_en.pdf | 技术稿 10 页含参考文献，逐页检查通过；个人信息/反思待核对 |
| 演示视频 | deliverables/final_20261009/videos/final_demo_en_v2.mp4 | 52 秒、1560 帧、30 fps；完整解码、抽帧检查，两个原速物理案例 |
| 库/工具/代码来源披露 | docs/attribution.md 与 docs/third_party/ | 已整理；不宣称未经定义的 50% 比例 |
| 一个小组 ZIP | 项目上级目录 Panda_Final_Project_20261009.zip 与旁置 receipt | 打包结果以 ZIP receipt 为准；没有自动提交 |

## 此次具体改善

报告增加训练稳定性专页：三个 seed 的初始、选中、最后模型分开；seed145 最后模型独立重放 24 个 validation 回合，1 成功、8 碰撞、15 限位。验证曲线是重复使用的选模集诊断，不作为新的 held-out 估计。没有修改旧控制器、冻结阈值、三个已选模型或原来的 500 回合结果。

视频增加红色球障碍箭头、参考/实际轨迹图例和稳定性说明。第一个案例换到能看到球体的相机角度；只变显示，不变物理。两段重放共六个窗口的最大 q 差均为 0。

quickstart 自动为搬迁副本创建新 freeze，不要求用户手动编辑旧绝对路径。108 项关键逻辑测试全部通过（8.57 秒）；另在新目录项目 .venv 安装 35 个锁定依赖，三个模型各 960 步 / 240 次保存加载动作核对通过。q、qd、x、xref、command、error、time 数组逐位一致。新环境使用缓存安装、复用 CPython 解释器；这是同一 Linux 主机的搬迁验证，不是另一台电脑或跨平台验证。

## 本人仍需处理的部分

1. 确认英文署名与课程若要求的学号；没有从 proposal 猜测你的身份。
2. 用真实经历核对或补充个人反思；技术稿中的工程教训有记录支持，不替你声称亲自完成了所有实现。
3. 如果最终仍有其他参与成员，各自提供独立个人报告，不能把这一份改名复制给全组。
4. 由本人核对 Canvas 的实际入口/显示时区与完整 rubric，然后自行决定何时提交。已知年份是用户确认的 2026，截图 final 截止为 20 Nov 23:59；未把 Gym 阶段截止混用。

用户随后明确授权将今天的更新同步到现有公开 GitHub 仓库，并通过新 v1.1.0 Release 分发。课程平台提交仍由本人负责；没有代发消息给队友。旧 final Release 与此前交付包保持原字节。公开入口及附件以 [v1.1.0](https://github.com/kimzclandi/panda-obstacle-aware-posture-control/releases/tag/v1.1.0) 为准。

## 保留的失败与限制

首轮报告先后因第二视频尚未生成及超过十页被拒绝，均没有当作合格报告；排版中间件保存在工作目录。第一次环境验证把 venv 建在项目外，冻结资产路径校验按设计拒绝；改在项目 .venv 内实装后通过。默认 uv 缓存只读，通过复制缓存到可写工作目录解决，未改系统环境。所有科研失败回合继续保留于 experiments/。

没有新训练或新的 test 选模。已见 test 不适合再次作为新方法的未见泛化证据；若以后改进学习稳定性，需先声明 train/validation 诊断方案，再用另行冻结的未见测试集评价新方法。
