"""Bond calculator: what a bond really pays, and what happens to its price if interest rates move.

Plain fixed-coupon bonds only (government securities, corporate bonds, SDLs). Price is per 100 of
face value, without accrued interest.
"""


def cash_flows(coupon: float, years: float, per_year: int, face: float = 100.0) -> list[tuple[float, float]]:
    """(time in years, amount) for each payment, the last one including the face value back."""
    n = max(1, round(years * per_year))
    pay = face * coupon / per_year
    return [((k + 1) / per_year, pay + (face if k == n - 1 else 0)) for k in range(n)]


def price(flows, yld: float, per_year: int) -> float:
    return sum(a / (1 + yld / per_year) ** (t * per_year) for t, a in flows)


def yield_to_maturity(flows, paid: float, per_year: int) -> float:
    """The yearly return if held to the end and every payment is made, found by halving."""
    lo, hi = -0.5, 2.0
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if price(flows, mid, per_year) > paid else (lo, mid)
    return (lo + hi) / 2


def analyse(coupon: float, years: float, paid: float, per_year: int = 2) -> dict:
    if per_year not in (1, 2, 4, 12):
        raise ValueError("Payments a year must be 1, 2, 4 or 12")
    if not (0 <= coupon < 1 and 0 < years <= 50 and 0 < paid < 1000):
        raise ValueError("Coupon 0 to 100%, 1 month to 50 years left, price per 100 of face value")
    flows = cash_flows(coupon, years, per_year)
    y = yield_to_maturity(flows, paid, per_year)
    p0 = price(flows, y, per_year)
    duration = sum(t * a / (1 + y / per_year) ** (t * per_year) for t, a in flows) / p0
    moves = {f"{m:+.0%}": price(flows, y + m, per_year) / paid - 1 for m in (-0.02, -0.01, 0.01, 0.02)}
    return {"ytm": y, "current_yield": coupon * 100 / paid, "duration": duration,
            "modified_duration": duration / (1 + y / per_year), "received": sum(a for _, a in flows),
            "payments": len(flows), "rate_moves": moves}
