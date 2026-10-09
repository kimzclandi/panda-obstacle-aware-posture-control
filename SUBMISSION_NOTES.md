# Final delivery map / 交付说明

Revision: 9 October 2026. GitHub distribution is authorized as v1.1.0; no course-platform submission has been performed. The complete Release ZIP preserves the earlier verified local snapshot, whose internal notes predate publication.

Start with README.md. The current files are resolved by study_index.json; historical versions remain for traceability.

- English technical report: deliverables/final_20261009/report_en_v2/final_report_en.pdf, 10 pages including references.
- English silent demonstration: deliverables/final_20261009/videos/final_demo_en_v2.mp4, 52 seconds, two verified four-second physical replays at original speed.
- Chinese page-by-page explanation: deliverables/final_20261009/interpretation_zh.md.
- English oral rehearsal: deliverables/final_20261009/oral_script_en.md; Chinese defense guide: docs/viva_guide_zh.md.
- Full training and evaluation code, three selected trained checkpoints, pinned dependencies, raw results and feasibility witnesses are included.
- Quick verification after installation: env -u PYTHONPATH .venv/bin/python scripts/quickstart.py. It automatically creates a new location manifest if the archive was moved; original evidence is untouched.
- Full requirements-to-evidence map and remaining personal items: docs/final_delivery_checklist.md.

研究结果：APF 92/100，tracker 70/100，PPO 三 seed 为 80/100、81/100、65/100。新增 validation 诊断确认一个最后训练模型发生明显退化。不能据此声称 RL 胜出、已收敛或只要延长训练就能改善。

Final 要求每名实际组员各自写一份至多十页报告。本包包含一份英文技术稿；署名、课程若要求的学号、你真实的个人反思，以及其他成员自己的报告仍需本人核对或提供。不要把历史草稿、排版失败版本或阶段两页 Gym 报告当作本次 final 报告。历史版本保留不代表要作为个人报告重复提交。

用户确认截止 2026-11-20 23:59；时区、完整 rubric、原创比例统计口径未独立核验。本包不宣称达到未经定义的原创代码比例。复用及许可证见 docs/attribution.md。
