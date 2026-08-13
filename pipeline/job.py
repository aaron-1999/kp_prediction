"""
Job dataclass + the actual pipeline steps run for one submitted SMILES.
No FastAPI/Pydantic imports here - this runs inside a plain background
worker thread (see api/queue.py) and could equally be smoke-tested by
calling run_pipeline() directly from a plain Python shell.
"""

import dataclasses
import time
import traceback
import uuid
from pathlib import Path
from typing import Optional

from . import formula
from .cdft_parse import extract_descriptors
from .config import JOBS_DIR
from .errors import InvalidSmilesError, PipelineStepError
from .inputs import generate_geometry, identify_vinyl_carbons, write_orca_inputs
from .multiwfn_runner import run_multiwfn_cdft
from .orca_runner import run_orca

STAGES = [
    "queued",
    "building_geometry",
    "optimizing_geometry",
    "single_point_neutral",
    "single_point_anion",
    "single_point_cation",
    "running_cdft",
    "extracting_descriptors",
    "done",
]


@dataclasses.dataclass
class Job:
    id: str
    smiles: str
    stage: str = "queued"
    failed: bool = False
    error: Optional[str] = None
    result: Optional[dict] = None
    created_at: float = dataclasses.field(default_factory=time.time)

    @property
    def job_dir(self) -> Path:
        return JOBS_DIR / self.id


def new_job(smiles: str) -> Job:
    return Job(id=uuid.uuid4().hex[:12], smiles=smiles)


def run_pipeline(job: Job) -> None:
    job_dir = job.job_dir
    job_dir.mkdir(parents=True, exist_ok=True)

    try:
        beta_idx, alpha_idx = identify_vinyl_carbons(job.smiles)

        job.stage = "building_geometry"
        generate_geometry(job.smiles, job_dir)
        write_orca_inputs(job_dir)

        job.stage = "optimizing_geometry"
        run_orca(job_dir / "mol_opt.in", "optimize")
        opt_xyz = job_dir / "mol_opt.xyz"
        if not opt_xyz.exists():
            raise PipelineStepError("optimize", "mol_opt.xyz not produced")

        job.stage = "single_point_neutral"
        run_orca(job_dir / "A_N.inp", "single_point_neutral")

        job.stage = "single_point_anion"
        run_orca(job_dir / "A_Nplus.inp", "single_point_anion")

        job.stage = "single_point_cation"
        run_orca(job_dir / "A_Nminus.inp", "single_point_cation")

        job.stage = "running_cdft"
        run_multiwfn_cdft(job_dir)

        job.stage = "extracting_descriptors"
        descriptors = extract_descriptors(job_dir, beta_idx, alpha_idx)

        lnA = formula.ln_a(descriptors)
        ea_kj = formula.ea_kj_per_mol(descriptors)
        sweep = formula.kp_sweep(descriptors)
        kp_298 = formula.kp_at(descriptors, 298.15)

        job.result = {
            "smiles": job.smiles,
            "beta_atom_idx": beta_idx,
            "alpha_atom_idx": alpha_idx,
            "descriptors": descriptors,
            "ln_A": lnA,
            "Ea_kJ_per_mol": ea_kj,
            "kp_298_15K": kp_298,
            "kp_sweep": [{"T_K": t, "kp": kp} for t, kp in sweep],
        }
        job.stage = "done"

    except (InvalidSmilesError, PipelineStepError) as e:
        job.failed = True
        job.error = str(e)
        log_tail = getattr(e, "log_tail", "")
        if log_tail:
            (job_dir / "error.log").write_text(log_tail)
    except Exception:
        job.failed = True
        job.error = "internal error - see server logs for this job id"
        (job_dir / "error.log").write_text(traceback.format_exc())
