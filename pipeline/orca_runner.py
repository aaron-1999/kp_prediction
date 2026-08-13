"""
Thin subprocess wrapper around the ORCA binary. Each ORCA .inp runs
single-threaded (no %pal block) - matches the fukui_2/fukui_3 pipeline this
kp formula was fitted against, and keeps one job's CPU footprint small and
predictable on a shared box.
"""

import os
import subprocess
from pathlib import Path

from .config import ORCA_BIN
from .errors import PipelineStepError

TERMINATED_NORMALLY = "****ORCA TERMINATED NORMALLY****"


def run_orca(input_file: Path, step_name: str) -> Path:
    """Run `orca <input_file>` in its own directory, return the .out path."""
    out_file = input_file.with_suffix(".out")
    with out_file.open("w") as f:
        subprocess.run(
            [ORCA_BIN, str(input_file.name)],
            cwd=str(input_file.parent),
            stdout=f,
            stderr=subprocess.STDOUT,
        )

    text = out_file.read_text(errors="replace")
    if TERMINATED_NORMALLY not in text:
        raise PipelineStepError(step_name, "ORCA did not terminate normally", log_tail=_tail(text))
    return out_file


def get_final_energy(out_file: Path) -> float:
    """Parse 'FINAL SINGLE POINT ENERGY' (Hartree) from an ORCA .out file."""
    energy = None
    for line in out_file.read_text(errors="replace").splitlines():
        if "FINAL SINGLE POINT ENERGY" in line:
            energy = float(line.split()[-1])
    if energy is None:
        raise PipelineStepError(out_file.stem, "no FINAL SINGLE POINT ENERGY found in .out")
    return energy


def _tail(text: str, n: int = 40) -> str:
    return "\n".join(text.splitlines()[-n:])
