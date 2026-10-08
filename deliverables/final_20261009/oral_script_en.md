# Oral briefing and defense prompts

This is a technical rehearsal script, not a claim about a student's personal contribution. No presentation length was specified by the available course materials.

## Brief technical explanation

Our question is whether learned secondary posture control improves obstacle avoidance when all methods share the same analytical tool-position tracker. We use a fixed-base, seven-joint Panda with fixed fingers, one known static sphere and a four-second smooth straight trajectory. The policy cannot change the path or stop the reference clock.

The primary controller tracks world-frame tool position using a damped inverse Jacobian. A separate SVD nullspace maps a bounded secondary velocity into posture motion. Every rollout uses velocity motors and physics steps. Accurate tool tracking alone does not guarantee arm safety, so we check the full robot's obstacle clearance, specified self-collision pairs and joint limits at every 240 Hz physics step.

We compare tracker-only, a validation-tuned artificial potential field, and PPO. The data comprise 64 training, 24 validation and 100 held-out scenes. Every accepted scene has a physically executed and replayed feasible joint-motion witness. This provides positive feasibility evidence, although the limited witness search biases the accepted distribution.

Three independent PPO seeds each received 98,304 policy decisions. Validation alone selected the checkpoints. On the same 100 fixed test scenes, the tracker succeeded 70 times, APF 92 times, and PPO 80, 81 and 65 times. Failures stayed in the denominator. These results do not support an advantage over tuned APF under this setup. PPO helped some tight layouts compared with tracking alone, but also introduced failures in simple layouts.

A further validation audit showed why the selected and final checkpoints must be distinguished. Seed 145's selected model achieved 17 of 24 validation successes; its final updated model achieved only one. Independent replay reproduced eight collisions and fifteen joint-limit failures. This confirms deterioration but does not identify its unique optimization cause or justify simply training longer.

The key engineering lesson is that task accuracy, collision safety, learning stability and reproducibility are separate properties. The package retains trained models, all failures, raw trajectories, witnesses, selection records and a frozen protocol. Our conclusion is limited to these short simulated paths and this sampling distribution; we do not claim convergence, continuous-time safety or transfer to hardware.

## Questions to rehearse

1. Why can the tool track correctly while an intermediate arm link collides?
2. Why use a damped primary inverse and a separate nullspace projector?
3. What would fail if only tool-to-sphere distance were checked?
4. What does a physical witness prove, and what does a failed search not prove?
5. What is held fixed across tracker, APF and PPO?
6. Why does reaching the defined task horizon terminate rather than externally truncate?
7. Why is seed 145's 81/100 test score compatible with its final model's 1/24 validation score?
8. Why are three policies on 100 shared scenes not 300 independent test scenes?
9. What can the 45 common-completion continuous comparisons establish?
10. What evidence would be needed to attribute a benefit specifically to future references?

These questions are for rehearsal; the student's understanding has not been independently assessed through answers. Detailed Chinese discussion is in docs/viva_guide_zh.md.
