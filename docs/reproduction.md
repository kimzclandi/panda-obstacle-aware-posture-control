# 交付包复现、搬迁与原始证据

[中文入口](../README.md) | [English overview](../README.en.md)

**本页用于完整 Release 附件。** 请从 [v1.0.0 Release](https://github.com/kimzclandi/panda-obstacle-aware-posture-control/releases/tag/v1.0.0) 下载 `ME5418_Group44_submission_20261004.zip` 与 `SHA256SUMS`。普通 clone 和 GitHub 自动生成的 Source code 压缩包不含模型、witness 和 `experiments/`，不能运行本页冻结验证。

```bash
# 将 ZIP、PDF、MP4、receipt 与 SHA256SUMS 下载到同一目录后核验全部附件
shasum -a 256 -c SHA256SUMS
unzip ME5418_Group44_submission_20261004.zip
cd panda-posture
```

未下载某个附件时，校验命令会报告它缺失；不要将缺失项当作校验通过。原始包为 716,482,807 字节，发布对应代码提交 `62d74a5eca02554596c64979dd2a47559b8850eb`。

冻结清单记录了最初实验所在 Linux 项目的绝对路径。把工程解压到另一目录后，不能直接把旧路径当作新环境，也不能修改原始配置文件来“修复路径”：这些文件本身属于已哈希的证据。`scripts/relocate_freeze.py` 仅为相同文件创建新的位置映射，保留原始清单和训练选择，随后仍经过同一个 `verify_frozen_inputs` 入口检查。

本页描述可执行复跑流程。尚未完成的训练、冻结、批量测试不因有复跑命令而视作已完成；实际运行目录及结果以 `progress.md` 和交付清单为准。路径中的 `<...>` 必须替换为包内实际目录。

## 1. 交付包必须带哪些文件

- 完整 `src/`、`scripts/`、`configs/`、`requirements.lock.txt`、`pyproject.toml`，以及使用说明。
- 原始冻结清单引用的 train/validation/test 场景清单、接受 witness 的 source/replay 配置、summary 和 NPZ，生成记录与源码快照。
- 三个被选中的模型、训练配置、实际消费场景、validation history、保存/加载检查、独立加载验证、训练 summary 和源码快照。
- 势场的全部 validation 选参证据和选中参数文件。
- 冻结清单 `audit.all_artifact_files` 中其余文件。Panda 模型资产位于项目 `.venv` 的 PyBullet 包内，由锁定依赖重新安装后按 hash 核验。

不要只打包 `best_model.zip` 和场景 JSON，却省去冻结器依赖的原始证据。`.venv/`、`.python/` 和 `.bootstrap/` 是安装环境，不通过直接移动旧虚拟环境复用；在新目录重建。复制后的原始实验文件保留字节内容，解压或文本编辑器不能替换换行、格式化 JSON 或重存 NPZ。

## 2. 在新目录建立环境

进入解压后的 `panda-posture` 项目根目录，使用项目锁定的 Python 3.11.17 和依赖：

```bash
bash scripts/bootstrap.sh
env -u PYTHONPATH .venv/bin/python scripts/check_environment.py
```

bootstrap 只安装到当前项目，不修改系统 Python。使用新项目的 `.venv/bin/python`；若仍导入旧 checkout 的 editable package，搬迁脚本会拒绝。复现目标首先是同版本 Linux/CPU/DIRECT 配置。相同输入 hash 不等于不同机器上的浮点物理轨迹必然逐位相同，重新运行的结果应单独保留并说明机器环境。

安装脚本使用 PyPI 获取普通依赖，并用 PyTorch CPU 的 torch 页面提供特定 wheel；不会修改锁定版本。这样避免 uv 的 first-index 规则让 PyTorch 索引中的旧普通包遮住 PyPI 上的锁定版本。此问题曾在新目录实装时出现，原失败与修复日志保留为搬迁验证证据。

本次原冻结还包含五个 `src/panda_posture.egg-info/` 元数据文件。editable 安装会重新生成 `SOURCES.txt`；bootstrap 在存在 `experiments/study_pretest_freeze.json` 时，先验证这些文件符合原 hash，安装后恢复它们原来的字节，并在 `.bootstrap/metadata_audits/` 保存原始、再生版本及前后 hash。该步骤保持原冻结证据，不改科研源码、参数或依赖版本。交付包必须保留这五个文件，不能仅依 Git 忽略规则打包而漏掉它们。

## 3. 为相同冻结输入重绑路径

以原工程根目录 `/home/linjun/Documents/Codex/2026-10-04/nus-me5418-machine-learning-in-robotics/outputs/panda-posture` 为旧根，在新工程根目录运行：

```bash
env -u PYTHONPATH .venv/bin/python scripts/relocate_freeze.py \
  --freeze experiments/<原始冻结清单>.json \
  --old-root /home/linjun/Documents/Codex/2026-10-04/nus-me5418-machine-learning-in-robotics/outputs/panda-posture \
  --new-root "$PWD" \
  --output experiments/reproduction_01/relocated_freeze.json
```

旧机器和旧根目录可以已经不存在。`--old-root` 必须是清单记录的实际旧项目根；这是文件位置映射，不能换成任意上级目录去包含额外文件。

脚本执行以下检查后才发布新清单：

1. 所有被引用的文件都映射到新工程内部，存在且 SHA-256 完全相同；越界路径、`..` 和逃出项目的 symlink 被拒绝。
2. 模型 seed、权重 hash、势场参数、协议、原始 witness/config/训练记录及全部源码 hash 均保持不变。
3. 原始清单按原字节复制为 `relocated_freeze.json.parent.json`，其 hash 写进新清单并纳入后续入口检查。
4. 调用原有 `verify_frozen_inputs`，通过后才以不可覆盖方式发布 `relocated_freeze.json`。

原始 `frozen_at_utc`、Git 状态、训练选择与审计结论不改写；新清单增加 `relocation`，记录映射时间、新旧根及 parent hash。审计中复制的训练 configuration 仍保留旧 `dataset_path`，因为它描述原运行事实；真正用于新机读取文件的 `path` 指针才被重绑。再次搬迁会保留 parent 链。

任何字节不一致都不能以“只是搬迁”为由绕过。缺文件时补齐交付包，环境/资产不一致时恢复锁定依赖；代码或参数确实需要修改时，应创建新的研究与输出，不能继续沿用同一冻结实验的结论。新清单和 parent snapshot 都拒绝覆盖；失败后若已有 parent snapshot，使用一个新的复现目录重试。

## 4. 先做三模型的交付快速验证

原目录使用：

```bash
env -u PYTHONPATH .venv/bin/python scripts/validate_delivery.py --index study_index.json
```

搬迁后使用新清单覆盖旧位置引用，不编辑原 study index：

```bash
env -u PYTHONPATH .venv/bin/python scripts/validate_delivery.py \
  --index study_index.json \
  --freeze experiments/reproduction_01/relocated_freeze.json
```

脚本先验证完整冻结输入及 index 的模型/参数对应关系，然后固定选取冻结 trainval manifest 中的第一个 validation 场景。三个模型各自加载、另存至新的实验目录、重载；在每个实际访问的 observation 上比较两模型的确定性 action，并通过共享仿真执行器运行一次物理轨迹。比较通过才记录 save/load 成功；任务碰撞、超差等失败照实保留并使快速验收非零退出，不改换更容易的场景。即使任务失败，也分别说明是正常执行后的策略失败还是模型加载/执行异常。

输出为独立 `experiments/<UTC>_delivery_validation/`，包含 `status.json`、重载副本、逐模型验证结果、物理 summary 与 NPZ。其决策耗时包含双模型推理检查，不作正式 benchmark 速度证据。若 index 的 `evaluation` 尚为 null，仍可验证受训模型；这是 validation 功能检查，不能因此宣称 held-out test 已完成。若已有 evaluation 路径，仅核对该批次配置身份，不读取 test 性能或重新选模。

## 5. 新建批量重评估结果

以下命令从 relocated manifest 中读取**已冻结**的模型、参数和场景，不重新选 checkpoint、不调参，也不重新训练：

```bash
env -u PYTHONPATH .venv/bin/python - <<'PY'
import json
from pathlib import Path
from panda_posture.batch import evaluate_batch

freeze_path = Path('experiments/reproduction_01/relocated_freeze.json')
frozen = json.loads(freeze_path.read_text())
out = evaluate_batch(
    frozen['test_dataset']['path'],
    ['test'],
    params_file=frozen['potential_parameters_file']['path'],
    models=[(model['seed'], model['path']) for model in frozen['models']],
    freeze_path=freeze_path,
)
print(out)
PY
```

评估器在加载 test 场景和 PPO 模型前再次检查冻结输入，然后创建新的 `experiments/<UTC>_paired_evaluation/`。把实际输出目录用于分析：

```bash
env -u PYTHONPATH .venv/bin/python -m panda_posture.analysis \
  --episodes experiments/<新的评估目录>/episodes.json \
  --out experiments/<新的评估目录>/analysis
```

所有提前失败仍在分母；`complete=false` 的中断批次不能作完整成功率统计。连续误差/平滑度只比较共同完成完整时域的场景；overall 配对 bootstrap 保留固定难度比例，三个训练 seed 的波动与场景区间分别报告。此命令使用既有受训模型重评估；若要重新训练三个 seed，应作为另一组实验记录，不能替换原 checkpoint 或声称新训练逐位重现旧权重。

原始冻结清单、原始批量结果、新位置映射和新批量结果是不同证据。搬迁脚本只核验内容与位置，不执行模型、不读取 test 的性能来修改任何选择。

## 6. 已实际执行的搬迁验收

原目录快速验收保存在 `experiments/20261003T201415.503267Z_delivery_validation/`。随后复制冻结证据到全新的项目目录，独立安装 Python 3.11.17 与锁定依赖，完成 bootstrap、路径重绑和同一个快速验收入口；完整证据归档在完整 ZIP 内的 `experiments/20261003T202857.594683Z_relocation_verification/summary.json`。

固定 validation 场景 `study-4410-0005` 上，seed 144、145、146 均完成 960 个物理步，每个模型的 240 次访问 observation 上保存前后确定性 action 完全一致。搬迁前后的全部物理状态与命令数组也逐位一致，最大关节差和命令差均为 0；耗时数组不纳入一致性声明。26 个冻结源码文件全部保持原 hash，三模型均通过原冻结输入核验。

首次 bootstrap 因 uv 索引优先级失败，修复为 PyPI + Torch CPU 专属 find-links 后成功；editable 安装实际只再生了被冻结的 `SOURCES.txt`，自动元数据保护恢复原字节且保留审计。归档包含失败/成功日志、独立新环境路径与版本、metadata 原始/再生文件、parent/relocated manifest 和三个实际重跑 NPZ。交付验证相关 18 项边界测试通过。

这证明了本机上新目录、新环境的可迁移安装与功能重现；不是另一种操作系统或不同硬件上的确定性保证，也不是额外 test 性能比较。
