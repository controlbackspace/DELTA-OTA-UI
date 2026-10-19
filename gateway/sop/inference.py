"""The statistical treatment of Chapter 3, as functions (Equations 1 to 6).

Pure Python, no third-party packages, so the campaign tool runs wherever the gateway does.
Each function says which equation it implements. Nothing here invents data: callers pass the
recorded per-trial values.

  Eq. 1  arithmetic mean                         mean()
  Eq. 2  sample standard deviation (n - 1)       sample_sd()
  Eq. 3  relative payload reduction, percent     relative_reduction_pct()
  Eq. 4  relative RAM reduction, percent         relative_reduction_pct()  (same form)
  --     absolute difference ("security tax")    absolute_difference()
  --     paired-samples t-test (Research Design) paired_t_test()
  Eq. 5  upper tolerance limit  mean + k * sd    upper_tolerance_limit()
  Eq. 6  Success-Run theorem  C = 1 - R^n        success_run_confidence()
"""
from __future__ import annotations

import math
import statistics

# One-sided normal tolerance factors k for 99% coverage at 95% confidence, computed with the exact
# non-central t relation k = t'_{0.95}(n-1, z_0.99 * sqrt(n)) / sqrt(n) (reference implementation:
# scipy.stats.nct). Other sample sizes fall back to the Natrella approximation (within 0.3%).
_EXACT_K_99_95 = {10: 3.9811, 30: 3.0639, 60: 2.8071, 100: 2.6840}


def mean(values) -> float:
    """Eq. 1: the sample arithmetic mean."""
    xs = list(values)
    if not xs:
        raise ValueError("mean of an empty sample")
    return math.fsum(xs) / len(xs)


def sample_sd(values) -> float:
    """Eq. 2: the sample standard deviation, n - 1 in the denominator."""
    xs = list(values)
    if len(xs) < 2:
        raise ValueError("a standard deviation needs at least two values")
    m = mean(xs)
    return math.sqrt(math.fsum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def relative_reduction_pct(baseline: float, proposed: float) -> float:
    """Eq. 3 and Eq. 4: (baseline - proposed) / baseline * 100. Negative means the proposed value is larger."""
    if baseline == 0:
        raise ValueError("the baseline must be non-zero")
    return (baseline - proposed) / baseline * 100.0


def absolute_difference(secured, naked) -> dict:
    """The "Security Tax": the secured value minus the unsecured (naked) value, with the per-trial spread when paired."""
    s, n = list(secured), list(naked)
    out = {"mean_secured": mean(s), "mean_naked": mean(n), "difference": mean(s) - mean(n)}
    if len(s) == len(n) and len(s) >= 2:
        d = [a - b for a, b in zip(s, n)]
        out["sd_of_differences"] = sample_sd(d)
    return out


# ---- paired t-test -------------------------------------------------------------------------------

def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (modified Lentz)."""
    tiny, eps = 1e-300, 1e-15
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, 500):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > tiny else tiny)
        c = 1.0 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_two_sided_p(t: float, df: int) -> float:
    """P(|T| >= |t|) for Student's t with df degrees of freedom."""
    if df < 1:
        raise ValueError("df must be at least 1")
    return regularized_incomplete_beta(df / 2.0, 0.5, df / (df + t * t))


def paired_t_test(first, second) -> dict:
    """Paired-samples t-test of H0: mean(first - second) = 0, two-sided.

    `first` and `second` are matched by trial index. When every difference is identical the
    standard deviation is zero and t is undefined: the result is flagged `degenerate` and
    reports the exact difference instead of a test statistic.
    """
    a, b = list(first), list(second)
    if len(a) != len(b):
        raise ValueError("a paired test needs equal-length samples")
    if len(a) < 2:
        raise ValueError("a paired test needs at least two pairs")
    d = [x - y for x, y in zip(a, b)]
    n = len(d)
    md, sd = mean(d), sample_sd(d)
    out = {"n": n, "df": n - 1, "mean_difference": md, "sd_of_differences": sd,
           "degenerate": False, "t": None, "p_two_sided": None}
    if sd == 0.0:
        out["degenerate"] = True
        return out
    t = md / (sd / math.sqrt(n))
    out["t"] = t
    out["p_two_sided"] = t_two_sided_p(t, n - 1)
    return out


# ---- tolerance interval (Eq. 5) -----------------------------------------------------------------

def tolerance_factor(n: int, coverage: float = 0.99, confidence: float = 0.95) -> tuple[float, bool]:
    """One-sided normal tolerance factor k and whether it is the exact value (True) or the Natrella approximation (False)."""
    if n < 2:
        raise ValueError("n must be at least 2")
    if (coverage, confidence) == (0.99, 0.95) and n in _EXACT_K_99_95:
        return _EXACT_K_99_95[n], True
    nd = statistics.NormalDist()
    zp, zg = nd.inv_cdf(coverage), nd.inv_cdf(confidence)
    a = 1.0 - zg * zg / (2.0 * (n - 1))
    b = zp * zp - zg * zg / n
    return (zp + math.sqrt(zp * zp - a * b)) / a, False


def upper_tolerance_limit(values, coverage: float = 0.99, confidence: float = 0.95) -> dict:
    """Eq. 5: mean + k * sd, the value that `coverage` of all future runs stay below with `confidence`."""
    xs = list(values)
    k, exact = tolerance_factor(len(xs), coverage, confidence)
    m, s = mean(xs), sample_sd(xs)
    return {"n": len(xs), "mean": m, "sd": s, "k": k, "k_exact": exact, "upper_limit": m + k * s,
            "coverage": coverage, "confidence": confidence}


# ---- Success-Run theorem (Eq. 6) ------------------------------------------------------------------

def success_run_confidence(reliability: float, zero_failure_trials: int) -> float:
    """Eq. 6: C = 1 - R^n, the confidence that the reliability is at least R after n failure-free trials."""
    if not 0.0 < reliability < 1.0:
        raise ValueError("reliability must be between 0 and 1")
    if zero_failure_trials < 0:
        raise ValueError("trials must not be negative")
    return 1.0 - reliability ** zero_failure_trials


def success_run_trials(reliability: float, confidence: float) -> int:
    """Smallest number of failure-free trials that demonstrates `reliability` at `confidence`."""
    if not (0.0 < reliability < 1.0 and 0.0 < confidence < 1.0):
        raise ValueError("reliability and confidence must be between 0 and 1")
    return math.ceil(math.log(1.0 - confidence) / math.log(reliability))


# ---- supporting statistics for Chapter 4 (not equations of Chapter 3) -----------------------------

def paired_ci95(first, second) -> dict:
    """95% confidence interval of the mean paired difference, with the t critical value for n - 1 degrees of freedom."""
    r = paired_t_test(first, second)
    n, md, sd = r["n"], r["mean_difference"], r["sd_of_differences"]
    t_crit = _t_critical(n - 1)
    half = t_crit * sd / math.sqrt(n)
    return {"t_critical": t_crit, "low": md - half, "high": md + half}


def _t_critical(df: int, two_sided_alpha: float = 0.05) -> float:
    """Student t quantile by bisection on the exact p-value (df >= 1)."""
    lo, hi = 0.0, 1000.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_two_sided_p(mid, df) > two_sided_alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def effect_size_dz(first, second) -> float:
    """Cohen's dz for paired samples: mean difference over the standard deviation of the differences."""
    r = paired_t_test(first, second)
    if r["degenerate"]:
        raise ValueError("every difference is identical: dz is undefined")
    return r["mean_difference"] / r["sd_of_differences"]


def sign_test_p(first, second) -> dict:
    """Exact two-sided sign test on the paired differences (ties are dropped)."""
    d = [a - b for a, b in zip(first, second) if a != b]
    n = len(d)
    if n == 0:
        raise ValueError("all pairs are tied")
    below = sum(1 for x in d if x < 0)
    k = min(below, n - below)
    p = min(1.0, 2.0 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)
    return {"n": n, "first_lower": below, "p_two_sided": p}


def pearson_r(xs, ys) -> float:
    """Pearson correlation coefficient."""
    x, y = list(xs), list(ys)
    if len(x) != len(y) or len(x) < 2:
        raise ValueError("need two samples of the same length (at least 2)")
    mx, my = mean(x), mean(y)
    sxx = math.fsum((a - mx) ** 2 for a in x)
    syy = math.fsum((b - my) ** 2 for b in y)
    if sxx == 0 or syy == 0:
        raise ValueError("a constant sample has no correlation")
    return math.fsum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sxx * syy)


def linear_slope(xs, ys) -> float:
    """Least-squares slope of y on x."""
    x, y = list(xs), list(ys)
    mx, my = mean(x), mean(y)
    sxx = math.fsum((a - mx) ** 2 for a in x)
    if sxx == 0:
        raise ValueError("x is constant")
    return math.fsum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx


def fisher_exact_two_sided(a_fail: int, a_n: int, b_fail: int, b_n: int) -> float:
    """Two-sided Fisher exact test on 2 x 2 failure counts (sum of all tables no more likely than the observed one)."""
    n, k = a_n + b_n, a_fail + b_fail

    def prob(x: int) -> float:
        return math.comb(k, x) * math.comb(n - k, a_n - x) / math.comb(n, a_n)

    p0 = prob(a_fail)
    return min(1.0, sum(prob(x) for x in range(max(0, k - b_n), min(k, a_n) + 1) if prob(x) <= p0 * (1 + 1e-9)))


def wilson_interval(successes: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    """Wilson score interval for a proportion (default 95%)."""
    if n <= 0 or not 0 <= successes <= n:
        raise ValueError("need 0 <= successes <= n and n > 0")
    p = successes / n
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - half) / denom, (centre + half) / denom


def welch_t(first, second) -> dict:
    """Unpaired Welch t-test (unequal variances), two-sided; the degrees of freedom are rounded for the p-value."""
    a, b = list(first), list(second)
    na, nb = len(a), len(b)
    va, vb = sample_sd(a) ** 2 / na, sample_sd(b) ** 2 / nb
    t = (mean(a) - mean(b)) / math.sqrt(va + vb)
    df = (va + vb) ** 2 / (va ** 2 / (na - 1) + vb ** 2 / (nb - 1))
    return {"t": t, "df": df, "p_two_sided": t_two_sided_p(t, max(1, round(df))), "n_first": na, "n_second": nb}
