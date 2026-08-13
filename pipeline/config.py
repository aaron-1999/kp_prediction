"""
Paths to external tools, overridable via environment variables so the same
code works during local testing and once deployed under systemd.
"""

import os
from pathlib import Path

HOME = Path.home()

ORCA_BIN = os.environ.get("ORCA_BIN", str(HOME / "software" / "orca" / "orca"))
MULTIWFN_BIN = os.environ.get("MULTIWFN_BIN", str(HOME / "software" / "Multiwfn" / "Multiwfn_noGUI"))
MULTIWFN_PATH = os.environ.get("MULTIWFN_PATH", str(HOME / "software" / "Multiwfn"))

# Absolute path, not a bare "obabel" - under systemd there's no PATH pointing
# at the conda env (unlike an interactive shell after `conda activate`), so a
# bare command name silently 404s as FileNotFoundError.
OBABEL_BIN = os.environ.get(
    "OBABEL_BIN", str(HOME / "software" / "miniforge3" / "envs" / "kp_webapp" / "bin" / "obabel")
)

JOBS_DIR = Path(os.environ.get("KP_JOBS_DIR", str(HOME / "kp_webapp_jobs")))

# ORCA writes to a scratch working directory; each job gets its own so
# concurrent/sequential runs never collide on filenames like mol_opt.gbw.
JOBS_DIR.mkdir(parents=True, exist_ok=True)
