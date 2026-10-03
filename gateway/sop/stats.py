"""Small, dependency-free summary statistics for repeated measurements."""
from __future__ import annotations

import math

# Two-sided 95% Student t critical values for df = 1..30.
_T95 = [
    12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
    2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
    2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042,
]


def t_critical_95(df: int) -> float:
    if df < 1:
        raise ValueError("need at least 2 samples for a confidence interval")
    if df <= 30:
        return _T95[df - 1]
    if df <= 60:
        return 2.000
    return 1.980 if df <= 120 else 1.960


def percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated percentile of an already sorted list, q in [0, 1]."""
    if not sorted_values:
        raise ValueError("no values")
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def summarize(values) -> dict:
    """n, mean, sample SD, min, max, median, p95 and the 95% CI half-width of
    the mean (None when n < 2). Raises on an empty input: no data, no summary."""
    xs = sorted(float(v) for v in values)
    n = len(xs)
    if n == 0:
        raise ValueError("cannot summarize an empty sample")
    mean = sum(xs) / n
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / (n - 1)) if n > 1 else None
    ci = t_critical_95(n - 1) * sd / math.sqrt(n) if sd is not None else None
    return {
        "n": n,
        "mean": mean,
        "sd": sd,
        "min": xs[0],
        "max": xs[-1],
        "median": percentile(xs, 0.5),
        "p95": percentile(xs, 0.95),
        "ci95": ci,
    }


def fmt_ci(s: dict, digits: int = 2, unit: str = "") -> str:
    """'12.34 ± 0.56 ms (n=30)' for tables and claim sentences."""
    half = f" ± {s['ci95']:.{digits}f}" if s.get("ci95") is not None else ""
    return f"{s['mean']:.{digits}f}{half}{unit} (n={s['n']})"
