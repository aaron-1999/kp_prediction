"""
Drive Multiwfn's Conceptual DFT module (menu 22 -> 2) on the three .gbw files
to produce CDFT.txt. Same menu sequence as
~/.claude/skills/fukui-function-pipeline/templates/run_multiwfn_cdft.sh.template.
"""

import os
import subprocess
from pathlib import Path

from .config import MULTIWFN_BIN, MULTIWFN_PATH
from .errors import PipelineStepError


def run_multiwfn_cdft(job_dir: Path) -> Path:
    an, anplus, anminus = job_dir / "A_N.gbw", job_dir / "A_Nplus.gbw", job_dir / "A_Nminus.gbw"
    for p in (an, anplus, anminus):
        if not p.exists():
            raise PipelineStepError("cdft", f"missing {p.name} - single point calc did not finish")

    stdin = f"22\n2\n{an}\n{anplus}\n{anminus}\n0\n0\nq\n"

    env = dict(os.environ)
    env["Multiwfnpath"] = MULTIWFN_PATH
    env["OMP_STACKSIZE"] = "200M"

    log_path = job_dir / "multiwfn_cdft.log"
    with log_path.open("w") as log:
        # `ulimit -s unlimited` per Multiwfn manual Section 2.1.2 - needed for
        # OpenMP worker threads on some libc/thread-stack configurations.
        subprocess.run(
            ["bash", "-c", f'ulimit -s unlimited; exec "{MULTIWFN_BIN}" "{an}"'],
            cwd=str(job_dir),
            input=stdin,
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
            env=env,
        )

    cdft_path = job_dir / "CDFT.txt"
    if not cdft_path.exists():
        raise PipelineStepError(
            "cdft", "CDFT.txt was not produced", log_tail=_tail(log_path.read_text(errors="replace"))
        )
    return cdft_path


def _tail(text: str, n: int = 40) -> str:
    return "\n".join(text.splitlines()[-n:])
