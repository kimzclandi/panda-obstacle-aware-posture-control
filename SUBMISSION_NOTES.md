# Submission map / 提交说明

This archive contains the completed bounded study, not a convergence claim or a claim of PPO superiority.

- English individual report draft: `deliverables/report_en/final_report_en.pdf` (9 pages, references included).
- English silent demonstration: `deliverables/videos/final_demo_en.mp4` (38 seconds). Two original physical replay clips and verification records are beside it.
- Chinese explanation: `deliverables/interpretation_zh.md`; oral-defense guide: `docs/viva_guide_zh.md`.
- Source, complete training code, fixed checkpoints and validation entry points: see `README.md` and `study_index.json`.
- Dataset/witnesses/failures/raw trajectories/selection records: immutable `experiments/`.
- Reuse and licenses: `docs/attribution.md` and `docs/third_party/`.

The archive intentionally excludes virtual environments and Python binaries. Rebuild with `bash scripts/bootstrap.sh`. After moving the project, follow `docs/reproduction.md` to create a new relocated freeze manifest, then run the delivery validator or full frozen evaluation. Do not edit the original freeze or raw evidence to replace old absolute paths.

研究结果：APF92%，tracker70%，三PPO seed为80%、81%、65%，每策略相同100个测试场景。报告没有声称RL胜出，也没有将已实现等同于学生已掌握。

提交者请核对个人身份信息和真正的个人反思；当前报告不虚构组员分工。用户确认截止2026-11-20 23:59、AI辅助允许使用；Canvas时区、完整rubric和原创比例计算口径仍需课程材料确认。本包未自动提交到Canvas。
