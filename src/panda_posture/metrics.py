"""Episode-level failure latch; every sampled state contributes to success."""
from dataclasses import dataclass, field
import math


@dataclass
class SuccessMonitor:
    reasons: set = field(default_factory=set)

    def observe(self, error, tolerance, collision, joint_limit):
        if not math.isfinite(error):
            self.reasons.add('numerical_failure')
        if error > tolerance:
            self.reasons.add('tracking_tolerance')
        if collision:
            self.reasons.add('collision')
        if joint_limit:
            self.reasons.add('joint_limit')

    def success(self, completed):
        return bool(completed and not self.reasons)


def aggregate(episodes):
    """Never remove early failures from the success denominator."""
    if not episodes:
        raise ValueError('Empty evaluation')
    return {'episodes': len(episodes),
            'success_rate': sum(bool(e['success']) for e in episodes)/len(episodes),
            'collision_rate': sum('collision' in e['failure_reasons'] for e in episodes)/len(episodes)}
