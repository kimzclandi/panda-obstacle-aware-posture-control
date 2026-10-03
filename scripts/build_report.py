#!/usr/bin/env python3
"""Build a nine-page English report only from a completed frozen study.

The input index contains project-relative paths, so the report can be rebuilt
after relocation without editing any original experiment evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import escape

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                               TableStyle, PageBreak, Image)
from pypdf import PdfReader

from panda_posture.analysis import load_episodes
from panda_posture.artifacts import ROOT, write_json


BLUE = '#164e70'
PALETTE = ['#727e88', '#16847c', '#c65b35', '#8064aa', '#c79823']
ORDER = [('tracker', None), ('potential', None), ('ppo', 144), ('ppo', 145), ('ppo', 146)]


def read(path):
    return json.loads(Path(path).read_text())


def key(row):
    return row['controller'], row.get('training_seed')


def label(k):
    return {'tracker': 'Tracker', 'potential': 'Tuned APF', 'ppo': f'PPO {k[1]}'}[k[0]]


def figure_results(summary, out):
    fig, axes = plt.subplots(1, 3, figsize=(10.8, 3.3), sharey=True)
    for ax, difficulty in zip(axes, ('overall', 'simple', 'tight')):
        groups = {key(g): g for g in summary['groups'] if g['difficulty'] == difficulty}
        values = [100*groups[k]['success_rate'] for k in ORDER]
        ax.bar(range(5), values, color=PALETTE, width=.7)
        for i, k in enumerate(ORDER):
            g = groups[k]
            ax.text(i, values[i]+1.5, f"{g['n_success']}/{g['n_episodes']}", ha='center', fontsize=8)
        ax.set_xticks(range(5), ['Track', 'APF', '144', '145', '146'])
        ax.set(title=difficulty.title(), ylim=(0, 112))
        ax.grid(axis='y', alpha=.2)
        ax.set_axisbelow(True)
    axes[0].set_ylabel('Full-trajectory success (%)')
    fig.tight_layout()
    fig.savefig(out, dpi=190)
    plt.close(fig)


def figure_learning(runs, out):
    fig, ax = plt.subplots(figsize=(10.4, 3.35))
    for i, (seed, directory) in enumerate(runs.items()):
        history = read(directory/'validation_history.json')
        regular = [h for h in history if h['phase'] != 'final_after_update']
        ax.plot([h['timesteps'] for h in regular], [100*h['summary']['success_rate'] for h in regular],
                'o-', lw=1.6, ms=4, color=PALETTE[i+2], label=f'Seed {seed}')
        final = history[-1]
        ax.scatter(final['timesteps'], 100*final['summary']['success_rate'],
                   marker='*', s=95, color=PALETTE[i+2], zorder=4)
    ax.set(xlabel='Policy decisions collected', ylabel='Validation success (%)', ylim=(0, 105))
    ax.grid(alpha=.2)
    ax.legend(ncol=3, loc='lower right')
    fig.tight_layout()
    fig.savefig(out, dpi=190)
    plt.close(fig)


def choose_cases(rows):
    by = {(r['scenario_id'], key(r)): r for r in rows}
    ids = sorted({r['scenario_id'] for r in rows})
    cases = []
    for name, condition in [
        ('APF succeeds; PPO 144 fails', lambda s: by[s, ('potential', None)]['success'] and not by[s, ('ppo', 144)]['success']),
        ('PPO 144 succeeds; APF fails', lambda s: by[s, ('ppo', 144)]['success'] and not by[s, ('potential', None)]['success']),
        ('Tracker fails; APF and PPO 144 succeed', lambda s: not by[s, ('tracker', None)]['success'] and by[s, ('potential', None)]['success'] and by[s, ('ppo', 144)]['success']),
    ]:
        candidates = [s for s in ids if condition(s) and s not in [c['scenario_id'] for c in cases]]
        if candidates:
            cases.append({'scenario_id': candidates[0], 'category': name})
        if len(cases) == 2:
            break
    for sid in ids:
        if len(cases) >= 2:
            break
        if sid not in [c['scenario_id'] for c in cases]:
            cases.append({'scenario_id': sid, 'category': 'Fallback: first remaining fixed scene'})
    return cases


def figure_cases(cases, evaluation, out):
    fig, axes = plt.subplots(2, len(cases), figsize=(10.5, 4.8), squeeze=False)
    for column, case in enumerate(cases):
        sid = case['scenario_id']
        for k, color in zip(ORDER[:3], PALETTE[:3]):
            folder = evaluation/'rollouts'/(k[0] if k[1] is None else f'ppo-seed{k[1]}')/sid
            with np.load(folder/'trajectory.npz') as d:
                axes[0, column].plot(d['time'], d['obstacle_clearance']*1000, color=color, label=label(k))
                axes[1, column].plot(d['time'], d['error']*1000, color=color)
            if column == 0:
                axes[0, column].set_ylabel('Obstacle clearance (mm)')
                axes[1, column].set_ylabel('Position error (mm)')
        axes[0, column].axhline(.01, color='black', lw=.8, ls='--')
        axes[1, column].axhline(20, color='black', lw=.8, ls='--')
        axes[0, column].set_title(sid, fontsize=10)
        axes[1, column].set_xlabel('Reference time (s)')
        for ax in axes[:, column]:
            ax.set_xlim(0, 4)
            ax.grid(alpha=.2)
    axes[0, 0].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=185)
    plt.close(fig)


class Report:
    def __init__(self, output):
        for name, filename in [('Body', 'DejaVuSans.ttf'), ('Bold', 'DejaVuSans-Bold.ttf')]:
            pdfmetrics.registerFont(TTFont(name, '/usr/share/fonts/truetype/dejavu/'+filename))
        self.styles = {
            'body': ParagraphStyle('body', fontName='Body', fontSize=9.7, leading=14.2, spaceAfter=8),
            'small': ParagraphStyle('small', fontName='Body', fontSize=8.1, leading=11.6, spaceAfter=6),
            'h1': ParagraphStyle('h1', fontName='Bold', fontSize=19, leading=24, textColor=colors.HexColor(BLUE), spaceAfter=14),
            'h2': ParagraphStyle('h2', fontName='Bold', fontSize=11.8, leading=16, textColor=colors.HexColor(BLUE), spaceBefore=6, spaceAfter=7),
            'title': ParagraphStyle('title', fontName='Bold', fontSize=24, leading=30, textColor=colors.HexColor(BLUE), spaceAfter=16),
        }
        self.story = []
        self.output = output
        self.text_pages = []

    def p(self, text, style='body'):
        self.story.append(Paragraph(text, self.styles[style]))
        self.text_pages.append(text)

    def page(self, title):
        if self.story:
            self.story.append(PageBreak())
        self.p(title, 'h1')

    def table(self, header, rows, widths):
        content = [[Paragraph(escape(str(x)), self.styles['small']) for x in row] for row in [header]+rows]
        table = Table(content, colWidths=[v*mm for v in widths], repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e7eff4')),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LINEBELOW', (0,0), (-1,0), .8, colors.HexColor(BLUE)),
            ('LINEBELOW', (0,1), (-1,-1), .3, colors.HexColor('#d5dce2')),
            ('LEFTPADDING', (0,0), (-1,-1), 5), ('RIGHTPADDING', (0,0), (-1,-1), 5),
            ('TOPPADDING', (0,0), (-1,-1), 5), ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        self.story.extend([table, Spacer(1, 9)])

    def image(self, path, width=174):
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            ratio = im.height/im.width
        self.story.append(Image(str(path), width=width*mm, height=width*mm*ratio))
        self.story.append(Spacer(1, 7))

    def build(self):
        def footer(canvas, doc):
            canvas.setStrokeColor(colors.HexColor('#ccd9e1'))
            canvas.line(18*mm, 16*mm, 192*mm, 16*mm)
            canvas.setFont('Body', 7.4)
            canvas.setFillColor(colors.HexColor('#52636d'))
            canvas.drawString(18*mm, 11*mm, 'NUS ME5418 | Group 44 | Bounded reproducible study | 4 October 2026')
            canvas.drawRightString(192*mm, 11*mm, str(doc.page))
        doc = SimpleDocTemplate(str(self.output), pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
                                topMargin=18*mm, bottomMargin=22*mm,
                                title='Learning Obstacle-Aware Posture Control for a Redundant Robotic Arm',
                                author='NUS ME5418 Group 44')
        doc.build(self.story, onFirstPage=footer, onLaterPages=footer)
        n = len(PdfReader(self.output).pages)
        if n != 9:
            raise RuntimeError(f'Expected nine pages; got {n}. Inspect and fix layout before delivery.')
        return n


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    idx = read(args.index)
    evaluation = ROOT/idx['evaluation']
    payload = read(evaluation/'episodes.json')
    rows = load_episodes(payload)
    if len(rows) != 500 or any(r['split'] != 'test' for r in rows):
        raise ValueError('Report requires the completed 5-policy x 100 held-out study')
    summary = read(evaluation/'analysis/summary.json')
    if summary['total_episode_rows'] != len(rows):
        raise ValueError('Analysis count mismatch')
    if read(evaluation/'analysis/analysis_provenance.json')['input_sha256'] != hashlib.sha256((evaluation/'episodes.json').read_bytes()).hexdigest():
        raise ValueError('Analysis is stale')
    freeze = read(ROOT/idx['freeze'])
    if freeze['status'] != 'frozen_before_test':
        raise ValueError('Missing pretest freeze')
    runs = {int(seed): ROOT/path for seed, path in sorted(idx['training'].items(), key=lambda item: int(item[0]))}
    if list(runs) != [144,145,146] or {key(r) for r in rows} != set(ORDER):
        raise ValueError('Expected exactly the three prespecified study seeds and two baselines')
    from panda_posture.freeze import verify_frozen_inputs
    verify_frozen_inputs(ROOT/idx['freeze'], ROOT/idx['test'], ROOT/idx['potential'],
                         [(seed, directory/'best_model.zip') for seed, directory in runs.items()])
    evaluation_cfg = read(evaluation/'config.json')
    bound_models = {(int(m['seed']), m['sha256']) for m in freeze['models']}
    if ({(int(m['seed']), m['sha256']) for m in evaluation_cfg['models']} != bound_models
            or evaluation_cfg['dataset_sha256'] != freeze['test_dataset']['sha256']
            or evaluation_cfg['potential_parameters'] != read(ROOT/idx['potential'])['parameters']):
        raise ValueError('Evaluation inputs differ from the frozen models, dataset or baseline')
    train = {seed: read(path/'training_summary.json') for seed, path in runs.items()}
    tuning = read(ROOT/idx['potential'])
    groups = {(g['difficulty'], key(g)): g for g in summary['groups']}
    ppo_rates = [groups['overall', ('ppo', s)]['success_rate'] for s in runs]
    apf_rate = groups['overall', ('potential', None)]['success_rate']
    tracker_rate = groups['overall', ('tracker', None)]['success_rate']
    verdict = ('All three learned policies exceeded the tuned potential-field baseline on this fixed test set.' if min(ppo_rates) > apf_rate
               else 'No learned policy exceeded the tuned potential-field baseline on this fixed test set.' if max(ppo_rates) <= apf_rate
               else 'The advantage over the tuned potential-field baseline depended on the training seed.')
    args.out.mkdir(parents=True, exist_ok=False)
    figs = args.out/'figures'
    figs.mkdir()
    figure_results(summary, figs/'success.png')
    figure_learning(runs, figs/'learning.png')
    cases = choose_cases(rows)
    figure_cases(cases, evaluation, figs/'cases.png')
    write_json(args.out/'example_selection.json', {'rule': 'First lexicographic scene in each prespecified outcome category; seed 144 fixed, not best-test-seed selection', 'cases': cases})
    report = Report(args.out/'final_report_en.pdf')

    report.p('Learning Obstacle-Aware Posture Control for a Redundant Robotic Arm', 'title')
    report.p('NUS ME5418 - Machine Learning in Robotics<br/>Individual report draft | Group 44 | English edition', 'small')
    report.p('Abstract', 'h2')
    report.p('A redundant arm can place its tool correctly while an intermediate link strikes an obstacle. This project therefore learns only the secondary posture motion, leaving a common analytic position tracker responsible for the prescribed path and clock. A fixed-base Franka Panda in PyBullet follows four-second smooth spatial lines around one known static sphere. A tracker-only controller, a validation-tuned full-body artificial potential field (APF), and three independently trained PPO policies share the same actuator interface and safety tests.')
    report.p(f'The study uses 64 training, 24 validation and 100 held-out scenarios, each admitted only after a complete physical joint-motion witness and motor-command replay succeed. Each PPO seed receives 98,304 policy decisions. Test success is {tracker_rate:.0%} for tracking alone, {apf_rate:.0%} for tuned APF, and '+', '.join(f'{v:.0%}' for v in ppo_rates)+f' for PPO seeds 144, 145 and 146. {verdict} These results concern the frozen witness-filtered distribution and limited training budget; they do not establish global feasibility, convergence, continuous-time safety or a benefit attributable specifically to future-reference features.')
    report.p('1. Problem and motivation', 'h2')
    report.p('Tool-position accuracy is only one part of safe arm motion. Seven arm joints provide redundancy for a three-dimensional position task, allowing posture changes without intentionally changing the desired tool velocity. Near an obstacle, however, the remaining directions may be poorly aligned with a locally useful repulsion direction. A learned secondary policy might prepare posture earlier; a geometric controller may instead be more reliable when the model and obstacle are already known. The research question is whether learning improves complete-trajectory success over a tuned conventional alternative, and where either method fails.')
    report.p('The scope deliberately excludes orientation tracking, vision, grasping, hardware and moving obstacles. The policy cannot alter the reference path, duration or clock. This controlled setting makes a negative learning result informative: it tests the added value of learned posture decisions after accurate tracking and usable geometry are already supplied.')
    report.p('New work beyond the proposal comprises the physical execution engine, verified geometry/Jacobians, full-arm APF, witnessed datasets, Gymnasium task, checkpoint-selection safeguards, paired test analysis and motor-replay videos. The following sections describe measured engineering outcomes rather than a proposed experiment.', 'small')

    report.page('2. Shared robot and control system')
    report.p('Frames, shapes and execution', 'h2')
    report.p('The robot is the bundled Panda URDF with a fixed base. Joint and link names are discovered at load time: seven arm joints occupy indices 0-6, two finger joints 9 and 10, and the tool is the origin of panda_grasptarget, link 11. Fingers have fixed 0.02 m position targets and remain collision geometry. The movable model has nine degrees of freedom; the arm columns are selected from the full position Jacobian using the discovered DOF map.')
    report.p('q is a seven-vector in rad; x and x_ref are world-frame tool positions in m. J is 3 x 7 in m/rad. The reference is x_ref(t) = x_0 + (10s^3 - 15s^4 + 6s^5) Delta_x, with s = t/4 clipped to [0,1]. Its analytic derivative supplies v_ref in m/s. This gives zero endpoint velocity and acceleration.')
    report.p('qdot_raw = J_dls [v_ref + 8 (x_ref - x)] + N u_secondary<br/>J_dls = V_3 diag(sigma / (sigma^2 + 0.01^2)) U^T<br/>N = V_null V_null^T; u_secondary = 0.5 clip(a, -1, 1) rad/s<br/>V_3 is the first three columns of full V (7 x 3); U is 3 x 3.', 'small')
    report.p('The primary inverse damps small singular values. The secondary projector uses the SVD numerical nullspace separately: I - J_dls J is generally not an exact nullspace projector. Commands are finally clipped to the shared 1 rad/s joint target limit and applied through URDF-limited velocity motors. The primary controller and Jacobian update at 240 Hz; the seven-vector secondary action updates at 60 Hz and is held over four physical steps. Every formal state transition calls stepSimulation. Resets are restricted to initialization or offline diagnostics.')
    report.p('Verification and safety boundary', 'h2')
    report.table(['Check', 'Measured evidence'], [
        ['Tool Jacobian finite differences', 'Five poses, two perturbations; worst absolute mismatch 6.346e-5 m/rad (threshold 2e-4).'],
        ['Nonzero nullspace diagnostic', 'max ||JN|| = 1.78e-16; damped-complement diagnostic = 4.28e-4.'],
        ['No-obstacle physical line', '4 s / 960 steps; max error 0.02360 mm; RMSE 0.02051 mm; no collision, limit failure or saturation.'],
        ['Motor-command replay', 'Saved command sequence reproduces the joint trajectory exactly in the same environment.'],
    ], [57,117])
    report.p('Closest-point queries cover the base, arm links, hand and fingers. The explicit self-collision list checks 45 pairs and excludes 10 adjacent or rigidly connected structural pairs; a two-hop link pair can collide and is not excluded automatically. Positive collision and distance-gradient tests are included. Success checks the initial state and all 960 post-step states: error <= 20 mm, signed forbidden separation > 10 micrometres, and URDF joint limits within 1e-4 rad numerical tolerance. A violation is latched. No sampled collision result proves safety between simulation steps.')

    report.page('3. Conventional and learned posture control')
    report.p('Artificial potential field baseline', 'h2')
    report.p('The APF sums obstacle, optional self-collision and joint-limit velocity terms. For a closest-point pair, the world normal n points from object B to A; the distance derivative is n^T(J_A - J_B), with J_B = 0 for the static sphere. Inside an influence distance d_0, repulsion scales as k(1/d - 1/d_0)/d^2 times that derivative. The distance used in this coefficient is floored at 15 mm to regularize near-contact growth. A quadratic soft joint-limit term acts inside a 0.3 rad margin, with boundary gain 0.4 rad/s. The result is bounded through the same action interface as PPO. This is a local controller inspired by artificial-potential-field methods [1], not a safety certificate or a globally optimal planner.')
    params = tuning['parameters']
    report.p(f'Twelve predeclared combinations were evaluated on all 24 validation scenes: obstacle gain {{0.0001, 0.0004, 0.0016}}, influence {{0.08, 0.16}} m and self gain {{0, 0.00008}}. Maximum full success selects the baseline; exact ties choose the earliest grid entry. Selected values are obstacle gain {params["obstacle_gain"]}, influence {params["influence_distance"]} m and self gain {params["self_gain"]}. Other terms remain fixed. This finite search is the tuning claim; it does not exhaust all possible conventional controllers.')
    report.p('Observation and action', 'h2')
    report.table(['Observation block', 'Dimensions and fixed normalization'], [
        ['Joint state', 'q: 7, centered/scaled by URDF limits; qdot: 7, divided by shared speed bounds.'],
        ['Current task / clock', 'Position error: 3 / 0.02 m; v_ref: 3 / 0.2 m/s; progress: 1, t/4.'],
        ['Future reference', 'Three world-frame future tool displacements at +0.25, +0.5, +1.0 s: 9 / 0.25 m; endpoint clamped.'],
        ['Sphere and command memory', 'Center: 3 / 1 m; radius: 1 / 0.2 m; presence: 1; last applied motor target: 7 / speed bounds.'],
        ['Geometry', 'Minimum self and sphere clearance: 2 / 0.1 and 0.2 m; eleven per-link sphere clearances: 11 / 0.2 m.'],
    ], [50,124])
    report.p('The resulting 55-vector is float32 with fixed clipping, not running normalization. World coordinates are used consistently; joint features use joint coordinates. Witnesses, controller labels and expert actions are absent. Geometry is available to both APF and PPO, although each computes a different deterministic feature representation. The learned action is a bounded seven-vector; no orientation or clock action exists. This observation approximates the simulation state: fixed finger servos and unobserved solver state preclude a claim of an exact minimal Markov state.', 'small')
    report.p('PPO uses the SB3 implementation [2,3], separate two-layer 64-unit tanh actor/value MLPs and a diagonal Gaussian policy during training. Deterministic evaluation uses its mean action, clipped to the environment bounds. It optimizes a clipped policy-ratio surrogate with value and entropy terms; clipping is an optimization device, not a robot-safety constraint.')

    report.page('4. Reward, training and task semantics')
    report.p('Reward is integrated over every physical step, including the four steps between policy decisions. With e = ||x_ref - x||_2 the scalar tool error, epsilon = 0.02 m, d the smaller self/obstacle clearance, m = 0.05 m and v_k the motor target, the rate is:', 'body')
    report.p('r_k / dt = 1 - 2 min((e/epsilon)^2,1)<br/> - 2 clip((m-d)/m,0,1)^2<br/> - 0.1 min(mean(((v_k-v_(k-1))/v_max)^2),1).<br/>The mean follows elementwise squaring over the seven joints.', 'small')
    report.p('Complete success adds 20; task failure subtracts 20 + 3.1 times the remaining reference seconds. The running rate is bounded between -3.1 and 1. For this four-second undiscounted task, success has a conservative return lower bound of 7.6 and failure an upper bound of -16. This reduces the obvious incentive to end early merely to avoid future running costs. It does not guarantee learning or eliminate all failures among suboptimal policies; PPO also uses discounted returns.')
    report.p('A 24-episode validation probe compared zero, alternating extreme and fixed extreme secondary actions. Nine failures and fifteen successes retained their labels; failed returns did not exceed successful returns in this probe under either the implemented discount or the undiscounted sum. Oscillation reduced return on the five scenes completed by every probe, but one pair of failed trajectories differed by +0.00450 in undiscounted return in favor of oscillation. The probe is a diagnostic, not an exhaustive reward-hacking proof.')
    report.p('Terminated and truncated', 'h2')
    report.p('Reaching the defined four-second horizon is task termination, as are collision, joint-limit or numerical failures. A tracking-tolerance violation permanently removes success eligibility but does not pause the clock. Only an external budget cutoff is truncation; it is unused in study training. Progress is observed so the finite horizon is represented explicitly. This distinction follows Gymnasium bootstrapping semantics [4]. Failed episodes remain in every fixed evaluation denominator.')
    report.table(['PPO setting', 'Frozen value'], [
        ['Rollout / minibatch / optimizer epochs', '512 decisions / 64 samples / 10'],
        ['Learning rate / gamma / GAE lambda', '3e-4 / 0.995 / 0.95'],
        ['Clip range / entropy coefficient', '0.2 / 0.01'],
        ['Training seeds / budget per seed', '144, 145, 146 / 98,304 policy decisions'],
        ['Validation cadence', 'Every 12,288 decisions, plus evaluation after the final optimizer update.'],
        ['Checkpoint ranking', 'Success descending; collision ascending; full completion descending; earliest trained checkpoint breaks exact ties.'],
    ], [69,105])
    report.p('Step-zero validation is diagnostic and cannot win selection. The final optimizer update is evaluated explicitly because a step callback occurs before that rollout is optimized. Each chosen model is loaded into an independent environment and evaluated again; final-model save/load deterministic actions are required to match exactly. Training uses CPU PyTorch with one thread per independent process. The three study runs are concurrent independent learners, not distributed training. No GPU acceleration or convergence claim is made.')

    report.page('5. Feasibility and experimental protocol')
    report.p('A dynamic witness defines admissibility', 'h2')
    report.p('Candidate initial arm angles are perturbed by up to 0.25 rad around the base pose. Line displacement components are sampled from x in [0.05,0.13], y in [-0.11,0.11], z in [-0.065,0.07] m; duration is always four seconds. Sphere radii lie in [0.035,0.07] m. Offline geometry placement uses an intermediate surface on an unobstructed candidate motion. The prescribed surface-gap band is [0.035,0.07] m for simple layouts and [-0.018,0.008] m for tight layouts. These names denote generation strata, not guaranteed empirical difficulty.')
    report.p('Initial forbidden contact is rejected and initial obstacle clearance must be at least 1 mm. Three bounded witness attempts are run: tracker, default APF, and one seeded constant random secondary command. Acceptance uses their union. One successful attempt is selected and its complete motor sequence is replayed through the same actuator dynamics, reference time, limits and tolerance. Discrete IK states alone are insufficient. Searches without a witness are labelled unverified feasible, not mathematically infeasible. The witness is never a training input or an imitation-learning target.')
    report.p('The train/validation generator accepted 88 of 182 logged candidates: 85 were initially colliding, one failed the initial margin and eight remained unverified. Eight accepted scenes had only a random-secondary witness, two only a tracker witness and eight only an APF witness. This prevents acceptance from being equivalent to APF success, but the bounded union still creates selection bias. Claims therefore remain conditional on this generator and local initial-pose region.')
    report.table(['Partition', 'Size / use'], [
        ['Train', '64 (32 simple, 32 tight); seed 4410 generator; PPO updates only.'],
        ['Validation', '24 (12 + 12); same predeclared candidate-index split cycle; APF parameters and checkpoints only.'],
        ['Held-out test', '100 (50 + 50); separate generator seed 4490; fixed common scenes for all five policies.'],
    ], [43,131])
    report.p('Physical configuration hashes exclude labels and seeds and reject duplicate tasks across splits. Before model selection, access to test-generation results is restricted to feasibility and file integrity; candidate witness outcomes do not feed back to tuning. After validation selects the models and parameters, a detailed integrity audit creates the pretest manifest binding dataset, witness evidence, scientific source files, numerical thresholds, selected APF parameters and three checkpoint hashes. The test entry point refuses mismatched inputs. Normalization never updates on test.')
    report.p('The primary endpoint is complete-trajectory success, with all failures retained. Pairwise success effects use 10,000 matched bootstrap resamples; overall resampling stays within each difficulty and preserves the 50/50 mixture. This measures scenario-sampling uncertainty conditional on a fixed learned policy and the accepted distribution. Variation across three training seeds is reported separately. Continuous comparisons use only scenes that all compared policies physically completed for the full horizon, with the conditional sample size stated. They cannot replace the primary endpoint.')

    report.page('6. Held-out results and training behavior')
    report.p(verdict)
    report.image(figs/'success.png')
    report.p('Figure 1. Identical fixed test scenes, all failures retained. The two difficulty strata each contain 50 scenes. Counts are shown above bars; seed identifiers refer to independent training runs.', 'small')
    report.table(['Policy', 'Overall', 'Simple', 'Tight', 'Collision'], [
        [label(k), f"{groups['overall', k]['n_success']}/100", f"{groups['simple', k]['n_success']}/50", f"{groups['tight', k]['n_success']}/50", f"{groups['overall', k]['collision_rate']:.0%}"] for k in ORDER
    ], [44,32,32,32,34])
    report.image(figs/'learning.png')
    report.p('Figure 2. Full validation success versus collected policy decisions. Circles occur during rollout collection before the current optimizer update; stars are the final updated model. Step zero is shown but excluded from selection. These are validation measurements, not smoothed training returns.', 'small')
    spread = next(s for s in summary['training_seed_spread'] if s['difficulty'] == 'overall')
    report.p(f'The three-seed mean is {spread["mean_success_rate"]:.1%}, with sample standard deviation {100*spread["sample_std_success_rate"]:.2f} percentage points and range {min(ppo_rates):.0%}-{max(ppo_rates):.0%}. This describes training-seed variability on the same 100 scenes; the outcomes are not 300 independent test scenarios. Checkpoints were chosen at '+', '.join(f'{train[s]["best_validation_timestep"]:,} decisions (seed {s})' for s in runs)+'.')

    report.page('7. Paired effects, accuracy and execution cost')
    effect_rows = []
    for seed in runs:
        paired = next(p for p in summary['paired_comparisons'] if p['difficulty']=='overall' and p['policy_a']=={'controller':'potential','training_seed':None} and p['policy_b']=={'controller':'ppo','training_seed':seed})
        e = paired['success_effect']
        effect_rows.append([str(seed), f"{100*e['difference_b_minus_a']:+.1f}", f"[{100*e['interval'][0]:+.1f}, {100*e['interval'][1]:+.1f}]", f"{e['a_only_success']} / {e['b_only_success']}"])
    report.table(['PPO seed', 'PPO - APF (pp)', '95% paired interval', 'APF-only / PPO-only'], effect_rows, [29,43,51,51])
    report.p('The intervals above are empirical percentile intervals from stratified paired scenario resampling, conditional on each trained policy. They are not confidence intervals over repeated training. Per-stratum Wilson intervals and all pairwise results are retained in the machine-readable analysis. The overall Wilson interval is labelled a descriptive approximation because the difficulty mixture is fixed.', 'small')
    common = next(c for c in summary['common_completion_comparisons'] if c['difficulty']=='overall')
    ids = common['scenario_ids']
    report.p(f'Conditional continuous comparison: {len(ids)} / 100 scenes completed for four seconds by every policy. This excludes early-terminated scenes from continuous averages while retaining them in success and collision rates. Completion does not itself imply success; no success-only filter is applied.')
    continuous_rows=[]
    for k in ORDER:
        def avg(field, factor=1):
            metric = next(p for p in common['metrics'][field]['policies'] if key(p)==k)
            return 'N/A' if metric['mean'] is None else f"{metric['mean']*factor:.3f}"
        continuous_rows.append([label(k),avg('rmse_position_m_on_executed_prefix',1000),avg('min_obstacle_clearance_m',1000),avg('command_squared_acceleration_integral_on_executed_prefix_rad2_s3'),avg('joint_step_saturation_fraction',100)])
    report.table(['Policy', 'RMSE (mm)', 'Min gap (mm)', 'Smoothness*', 'Sat. (%)'], continuous_rows, [39,34,36,34,31])
    report.p('*Mean per-episode integral of squared finite-difference command acceleration (rad^2/s^3); smaller is smoother on this shared subset. Min gap is the mean of per-episode minimum obstacle clearance. Saturation is the fraction of joint-step targets clipped. These conditional values do not demonstrate superior global performance.', 'small')
    timing=[]
    for k in ORDER:
        subset=[r for r in rows if key(r)==k]
        timing.append([label(k)]+[f"{np.mean([r[f] for r in subset]):.3f}" for f in ['decision_mean_ms','secondary_decision_mean_ms','step_mean_ms']])
    report.table(['Policy', 'Decision / 240 Hz', 'Secondary / 60 Hz', 'Motor + physics'],timing,[43,46,43,42])
    report.p('All timing entries are milliseconds: unweighted means of episode-level means over all 100 executed prefixes. Decision includes state/reference, geometric safety checks, Jacobian and primary control, plus amortized secondary computation. Secondary includes APF geometry/control or PPO feature construction and inference. Motor + physics includes finger/arm command submission and stepSimulation. Robot loading, rendering and disk writes are excluded. Prefix lengths differ, so these descriptive implementation costs are not paired speedup estimates or hard real-time guarantees.', 'small')
    report.p('Measured per-seed learning wall times including callback validation: '+', '.join(f'{train[s]["learning_wall_s_including_callback_validation"]/60:.2f} min ({s})' for s in runs)+'. These runs overlap; their sum is summed per-process wall time, neither elapsed study duration nor CPU process time. The study uses CPU simulation and does not claim a measured GPU benefit.', 'small')

    report.page('8. Failure cases and interpretation')
    report.image(figs/'cases.png')
    report.p('Figure 3. Two deterministic outcome examples from the fixed test batch. Lines end at actual termination; a missing suffix is not zero error. Dashed lines indicate the 0.01 mm conservative obstacle-contact band and 20 mm tracking tolerance. The displayed geometry is obstacle clearance; all safety checks also include self-collision and limits.', 'small')
    for case in cases:
        sid=case['scenario_id']
        descriptions=[]
        for k in ORDER[:3]:
            row=next(r for r in rows if r['scenario_id']==sid and key(r)==k)
            descriptions.append(f"{label(k)}: {'success' if row['success'] else 'latched '+', '.join(row['failure_reasons'])}; executed {row['completed_duration_s']:.3f} s")
        report.p(f'<b>{sid}</b> - {escape(case["category"])}. '+escape('; '.join(descriptions))+'.', 'small')
    report.p('Selection uses the first lexicographic scene in prespecified outcome categories and fixes PPO seed 144, rather than choosing the best test seed. These examples illustrate observed disagreement; they do not estimate its frequency. The accompanying videos physically replay the recorded motor commands and verify the complete joint trajectory. Early failures freeze visibly at their failure time while other panes continue.')
    report.p('Mechanism versus hypothesis', 'h2')
    report.p('APF behavior is explained locally by geometric distance gradients, their projection into available redundant directions, and command limits. PPO can learn state-dependent posture changes but is trained on only 64 distinct scene configurations. When a learned policy collides despite a valid witness, the task was dynamically feasible under the shared contract; the observed policy simply did not realize a safe motion. A witness does not reveal whether PPO should have discovered it within this budget.')
    report.p('Poor alignment of the projected repulsion direction, abrupt closest-feature changes, limited experience near rare tight layouts and reward competition from self-clearance are plausible failure mechanisms. The stored trajectories permit inspection, but the current study does not isolate their causal contributions. There is no separately trained no-future-reference policy and no longer-budget learning curve on a new held-out set, so neither anticipation nor insufficient training can be claimed as the sole cause of a result.')

    report.page('9. Lessons, limitations and reproducibility')
    report.p('The engineering process changed the quality of the evidence more than adding model complexity. Name-based DOF mapping and finite differences prevented a tool/Jacobian mismatch. Explicit collision-pair handling was necessary because closest-point queries do not automatically inherit every filter choice. NaN failures needed explicit latching. The final-update callback boundary required an additional validation pass; a previous pilot was audited separately rather than silently rewriting history. These are concrete implementation lessons, not claims about unrecorded personal learning or other members\' contributions.')
    report.p(f'{verdict} The defensible conclusion is restricted to known geometry, four-second local lines, one sphere, the specified witness filter, three seeds and the declared PPO/APF budgets. Learning has not been compared with a globally optimized planner, MPC or a broader APF search. Three seeds provide limited training-variance evidence; 100 fixed scenes provide limited conditional generalization evidence. A 240 Hz collision check does not prove continuous-time safety. Physics/model mismatch, orientation tasks, moving obstacles and hardware remain outside scope.')
    report.p('Reproduction and next experiment', 'h2')
    report.p('The source package contains the pinned environment, training and evaluation entry points, all three functional checkpoints, selected APF parameters, scene IDs and dynamic witnesses, raw failures and trajectories, a pretest freeze manifest and regenerated analysis. README.md and docs/reproduction.md explain bootstrap, quick validation, full paired evaluation and path relocation. The report builder consumes a project-relative study index and refuses an incomplete 500-row batch. A future extension should be declared before observing a new test set: more diverse training scenes and a larger compute budget, followed by an independently trained future-reference ablation. Optional arcs are deferred to preserve the core comparison.')
    report.p('External reuse includes PyBullet and its Panda asset, Gymnasium, SB3/PyTorch and scientific/reporting libraries; exact versions, licenses and notices are archived. Project-specific control integration, task semantics, scene/witness pipeline, analysis and verification are implemented here. The course permits AI assistance according to the user; no percentage of originality is asserted because the course counting rule remains unspecified. This draft does not invent separate group-member contributions. The submitting student should check identity details and add their own supported reflection before upload.', 'small')
    report.p('References and evidence', 'h2')
    refs=[
        '[1] O. Khatib (1986). Real-Time Obstacle Avoidance for Manipulators and Mobile Robots. International Journal of Robotics Research, 5(1), 90-98. <link href="https://khatib.stanford.edu/publications/pdfs/Khatib_1986_IJRR.pdf" color="#164e70">Author-hosted paper</link>.',
        '[2] J. Schulman, F. Wolski, P. Dhariwal, A. Radford and O. Klimov (2017). Proximal Policy Optimization Algorithms. arXiv:1707.06347. <link href="https://arxiv.org/abs/1707.06347" color="#164e70">Primary paper</link>.',
        '[3] Stable-Baselines3. PPO implementation documentation; installed version 2.9.0 is pinned in requirements.lock.txt. <link href="https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html" color="#164e70">Official documentation</link> (accessed 4 October 2026).',
        '[4] Farama Foundation. Gymnasium: Handling Time Limits. <link href="https://gymnasium.farama.org/main/tutorials/handling_time_limits/" color="#164e70">Official documentation</link> (accessed 4 October 2026).',
        '[5] Bullet Physics / PyBullet bundled franka_panda model. Local URDF, geometry, joint metadata and asset hashes are recorded by the model and freeze manifests. Panda asset license: Apache-2.0; PyBullet: Zlib.',
        '[6] Project evidence: study_index.json; frozen protocol; training_summary.json for seeds 144-146; paired episodes.json; analysis/summary.json; source snapshots and immutable experiment folders. All numerical results above derive from these local records.',
    ]
    for ref in refs:
        report.p(ref,'small')
    n=report.build()
    (args.out/'report_text_en.txt').write_text('\n\n'.join(report.text_pages)+'\n')
    write_json(args.out/'report_provenance.json',{'pages':n,'study_index':str(args.index.resolve()),
        'index_sha256':hashlib.sha256(args.index.read_bytes()).hexdigest(),
        'episodes_sha256':hashlib.sha256((evaluation/'episodes.json').read_bytes()).hexdigest(),
        'pdf_sha256':hashlib.sha256(report.output.read_bytes()).hexdigest(),
        'generator_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'visual_review':'pending; render and inspect every page before delivery'})
    print(report.output)


if __name__=='__main__':
    main()
