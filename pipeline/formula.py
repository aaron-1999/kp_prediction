"""
kp(T) from the four raw Fukui/softness descriptors, via a single fitted
Arrhenius-type model (ln kp = ln A - Ea/RT, with ln A and Ea themselves
linear in the descriptors). Coefficients supplied directly by the project
owner - NOT derived from project_report.md's two-group (acrylate/
methacrylate) model, which was superseded by this single unified fit.

Fitted on descriptors computed at B3LYP/def2-SVP (geometry) + B3LYP-D4/
def2-SVP (single points) - see pipeline/inputs.py. Changing that level of
theory without re-fitting these coefficients would silently invalidate every
prediction this module makes.
"""

import math

R_GAS = 8.314  # J / (mol K)

# ln A = A0 + A_BETA_SMINUS * beta_s- + A_ALPHA_SPLUS * alpha_s+
A0 = -9.80
A_BETA_SMINUS = 3.31
A_ALPHA_SPLUS = 77.3

# Ea (kJ/mol) = EA0 + EA_BETA_FMINUS * beta_f- + EA_BETA_SPLUS * beta_s+
EA0 = -55.9
EA_BETA_FMINUS = 35.0
EA_BETA_SPLUS = 137.0


def ln_a(descriptors: dict[str, float]) -> float:
    return (
        A0
        + A_BETA_SMINUS * descriptors["beta_sminus"]
        + A_ALPHA_SPLUS * descriptors["alpha_splus"]
    )


def ea_kj_per_mol(descriptors: dict[str, float]) -> float:
    return (
        EA0
        + EA_BETA_FMINUS * descriptors["beta_fminus"]
        + EA_BETA_SPLUS * descriptors["beta_splus"]
    )


def kp_at(descriptors: dict[str, float], temperature_k: float) -> float:
    lnA = ln_a(descriptors)
    ea_j = ea_kj_per_mol(descriptors) * 1000.0
    return math.exp(lnA - ea_j / (R_GAS * temperature_k))


def kp_sweep(descriptors: dict[str, float], t_min: float = 273.0, t_max: float = 373.0,
             n_points: int = 51) -> list[tuple[float, float]]:
    """[(T_K, kp), ...] - cheap to compute at any resolution since it's a
    closed-form equation once ln A / Ea are known; the expensive part is the
    one-time DFT calculation that produced the descriptors, not this sweep."""
    if n_points < 2:
        n_points = 2
    step = (t_max - t_min) / (n_points - 1)
    lnA = ln_a(descriptors)
    ea_j = ea_kj_per_mol(descriptors) * 1000.0
    points = []
    for i in range(n_points):
        t = t_min + i * step
        kp = math.exp(lnA - ea_j / (R_GAS * t))
        points.append((t, kp))
    return points
