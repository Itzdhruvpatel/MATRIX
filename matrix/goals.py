"""Goal tracker: the range of outcomes for a goal, not one hopeful number.

Simulates monthly returns for a mix of shares and safer debt, using long-run assumptions stated
below (not a forecast), and shows the chance of reaching the goal and what monthly amount would
make it likely. The goal is in today's rupees and grows with inflation.
"""
import random
from datetime import date

PATHS = 2000
INFLATION = 0.06
# Long-run yearly return and swing (standard deviation): Indian shares and debt funds, rough.
EQUITY = (0.11, 0.18)
DEBT = (0.07, 0.03)
LIKELY = 0.75  # "likely" means reaching the goal 3 times in 4


def months_until(day: str, today: date) -> int:
    d = date.fromisoformat(day)
    return (d.year - today.year) * 12 + d.month - today.month


def _quantile(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, round(p * (len(xs) - 1))))]


def project(target: float, target_date: str, saved: float, monthly: float, equity_share: float,
            today: date | None = None, paths: int = PATHS, seed=0) -> dict:
    today = today or date.today()
    months = months_until(target_date, today)
    if months < 1:
        raise ValueError("The goal date must be at least a month away")
    need = target * (1 + INFLATION) ** (months / 12)
    mean = equity_share * EQUITY[0] + (1 - equity_share) * DEBT[0]
    # Shares and debt treated as unrelated, which is roughly true in India.
    swing = ((equity_share * EQUITY[1]) ** 2 + ((1 - equity_share) * DEBT[1]) ** 2) ** 0.5
    m_mean, m_swing = (1 + mean) ** (1 / 12) - 1, swing / 12 ** 0.5
    rng = random.Random(seed)
    lump, per_rupee = [], []  # per path: what Rs 1 now grows to, and what Rs 1 a month grows to
    for _ in range(paths):
        a, b = 1.0, 0.0
        for _ in range(months):
            g = 1 + rng.gauss(m_mean, m_swing)
            a *= g
            b = (b + 1) * g  # each month's amount goes in at the start of the month
        lump.append(a)
        per_rupee.append(b)
    finals = [saved * a + monthly * b for a, b in zip(lump, per_rupee)]
    # Final value is linear in the monthly amount, so the amount needed on each path is exact.
    needed = [max(0.0, (need - saved * a) / b) for a, b in zip(lump, per_rupee)]
    return {
        "months": months, "need": need, "put_in": saved + monthly * months,
        "chance": sum(f >= need for f in finals) / paths,
        "low": _quantile(finals, 0.1), "middle": _quantile(finals, 0.5), "high": _quantile(finals, 0.9),
        "monthly_for_likely": _quantile(needed, LIKELY), "likely": LIKELY,
        "assumptions": {"inflation": INFLATION, "mean": mean, "swing": swing},
    }
