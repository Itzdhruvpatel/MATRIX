"""Data quality rules. A failed row is quarantined; a flagged row is kept but logged."""

JUMP_LIMIT = 0.20  # 20% move vs exchange's previous close (already adjusted for splits/bonus)
TOLERANCE = 1e-6


def stock_row(r: dict) -> tuple[bool, str | None]:
    if min(r["open"], r["high"], r["low"], r["close"]) <= 0:
        return False, "non-positive price"
    if r["high"] + TOLERANCE < r["low"]:
        return False, "high below low"
    if not (r["low"] - TOLERANCE <= r["close"] <= r["high"] + TOLERANCE):
        return False, "close outside high-low range"
    if r["volume"] < 0:
        return False, "negative volume"
    return True, None


def stock_jump(r: dict) -> str | None:
    if r["prev_close"] > 0:
        move = r["close"] / r["prev_close"] - 1
        if abs(move) > JUMP_LIMIT:
            return f"price jump {move:+.1%} in one day"
    return None


def fund_row(r: dict) -> tuple[bool, str | None]:
    if r["nav"] <= 0:
        return False, "non-positive NAV"
    return True, None
