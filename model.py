"""Transparent baseline; not a validated predictive model."""
import math

def baseline_probability(game_log):
    """Smoothed goals/game estimate, illustrative only. Returns None without games."""
    if not game_log:
        return None
    recent = game_log[:10]
    goals = sum(int(g.get('goals', 0) or 0) for g in recent)
    # 0.15 prior rate, strength equivalent to 10 games; provisional, not calibrated.
    expected_goals = (goals + 1.5) / (len(recent) + 10)
    return round(100 * (1 - math.exp(-expected_goals)), 1)
