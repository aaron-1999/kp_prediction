"""
Extract exactly the four raw descriptors pipeline.formula needs:
beta_fminus, beta_sminus, beta_splus, alpha_splus.

Deliberately does NOT read Multiwfn's own local-softness (s-/s+/s0) table or
global-descriptor block from CDFT.txt - both are derived from E(N)/E(N+1)/
E(N-1), which can silently read as zero for ORCA 6 LeanSCF runs (see the
"Known bug" in fukui-function-pipeline SKILL.md Step 6). Instead this always
recomputes softness locally from the three ORCA .out energies directly
(same approach as that skill's patch_cdft.py), so it's correct regardless of
whether a given run happened to hit that bug.

Only the Fukui f-/f+/f0/CDD table is read from CDFT.txt - those are
density-difference quantities, not energy-dependent, and are always correct.
"""

import re
from pathlib import Path

from .errors import PipelineStepError
from .orca_runner import get_final_energy

HARTREE_TO_EV = 27.2114


def _parse_fukui_table(cdft_text: str) -> dict[int, dict[str, float]]:
    """{atom_num: {'fminus':.., 'fplus':..}} from CDFT.txt's Fukui section.

    Stops at the first blank line after the header - CDFT.txt has a second,
    similarly-shaped local-softness table right after it, and reading past
    the blank line would silently pick up s-/s+ values instead of f-/f+.
    """
    atoms: dict[int, dict[str, float]] = {}
    in_section = False
    for line in cdft_text.splitlines():
        if "f-" in line and "f+" in line and "f0" in line and "CDD" in line:
            in_section = True
            continue
        if in_section and line.strip() == "":
            break
        if in_section:
            # Element symbol field is "(C  " on Multiwfn 3.8 (no closing
            # paren before the numbers) but "(C )" on 2026.x releases (padded
            # to width 2, closing paren present) - the `\)?` handles both.
            m = re.match(
                r"\s*(\d+)\([A-Za-z]+\s*\)?\s+"
                r"([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+"
                r"([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)",
                line,
            )
            if m:
                # groups: 1=num, 2=q(N), 3=q(N+1), 4=q(N-1), 5=f-, 6=f+, 7=f0, 8=CDD
                atoms[int(m.group(1))] = {
                    "fminus": float(m.group(5)),
                    "fplus": float(m.group(6)),
                }
    return atoms


def extract_descriptors(job_dir: Path, beta_idx: int, alpha_idx: int) -> dict[str, float]:
    cdft_path = job_dir / "CDFT.txt"
    atoms = _parse_fukui_table(cdft_path.read_text(errors="replace"))

    for idx, label in [(beta_idx, "beta"), (alpha_idx, "alpha")]:
        if idx not in atoms:
            raise PipelineStepError(
                "extract", f"atom {idx} ({label}-C) not found in CDFT.txt Fukui table"
            )

    e_n = get_final_energy(job_dir / "A_N.out")
    e_nplus = get_final_energy(job_dir / "A_Nplus.out")
    e_nminus = get_final_energy(job_dir / "A_Nminus.out")

    ip = e_nminus - e_n  # Hartree
    ea = e_n - e_nplus  # Hartree
    eta = (ip - ea) / 2  # hardness, Hartree
    if eta == 0:
        raise PipelineStepError("extract", "hardness (eta) is exactly zero - can't compute softness")
    softness = 1.0 / (2 * eta)  # Hartree^-1 - NOT eV, matches how the kp formula was fitted

    beta_fminus = atoms[beta_idx]["fminus"]
    beta_fplus = atoms[beta_idx]["fplus"]
    alpha_fplus = atoms[alpha_idx]["fplus"]

    return {
        "beta_fminus": beta_fminus,
        "beta_sminus": beta_fminus * softness,
        "beta_splus": beta_fplus * softness,
        "alpha_splus": alpha_fplus * softness,
        "IP_eV": ip * HARTREE_TO_EV,
        "EA_eV": ea * HARTREE_TO_EV,
    }
