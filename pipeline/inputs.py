"""
SMILES -> initial 3D geometry, vinyl beta/alpha carbon identification, and
ORCA input files. Same DFT level and vinyl-carbon convention as the
fukui_2/fukui_3 pipeline the kp formula was fitted on (see
~/.claude/skills/fukui-function-pipeline/SKILL.md) - do NOT change the level
of theory here without re-fitting pipeline.formula's coefficients, since the
formula was fit on descriptors computed at exactly this level.
"""

import subprocess
from pathlib import Path

from openbabel import pybel

from .config import OBABEL_BIN
from .errors import InvalidSmilesError

OPT_INPUT = """! B3LYP def2-SVP Opt TightSCF

* xyzfile 0 1 mol.xyz
"""

# NOTE: "Nplus"/"Nminus" name the ELECTRON COUNT relative to N, not the charge
# sign. A_Nplus = N+1 electrons state = an ANION = charge -1. A_Nminus = N-1
# electrons state = a CATION = charge +1. Easy to invert by mistake.
AN_INPUT      = "! B3LYP D4 def2-SVP TightSCF SP\n* xyzfile  0 1 mol_opt.xyz\n"
ANPLUS_INPUT  = "! B3LYP D4 def2-SVP TightSCF SP\n* xyzfile -1 2 mol_opt.xyz\n"
ANMINUS_INPUT = "! B3LYP D4 def2-SVP TightSCF SP\n* xyzfile  1 2 mol_opt.xyz\n"


def generate_geometry(smiles: str, job_dir: Path) -> Path:
    """SMILES -> mol.xyz (initial 3D embedding). Raises InvalidSmilesError."""
    xyz_path = job_dir / "mol.xyz"

    cmd = [OBABEL_BIN, f"-:{smiles}", "-oxyz", f"-O{xyz_path}", "--gen3d", "--ff", "MMFF94"]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if not xyz_path.exists() or xyz_path.stat().st_size == 0:
        # Fallback: some structures fail MMFF94 embedding (missing params) but
        # obabel's default force field still manages a 3D embedding.
        cmd2 = [OBABEL_BIN, f"-:{smiles}", "-oxyz", f"-O{xyz_path}", "--gen3d"]
        result = subprocess.run(cmd2, capture_output=True, text=True)

    if not xyz_path.exists() or xyz_path.stat().st_size == 0:
        raise InvalidSmilesError(
            f"obabel could not generate a 3D structure for this SMILES: {result.stderr.strip()}"
        )
    return xyz_path


def identify_vinyl_carbons(smiles: str) -> tuple[int, int]:
    """
    Return (beta_idx, alpha_idx), 1-based atom indices matching ORCA/Multiwfn
    numbering (obabel preserves SMILES atom order into the xyz it writes, and
    ORCA preserves xyz atom order - see generate_geometry, called with the
    same SMILES string).

    beta-C = terminal CH2= (more attached H) - the carbon a radical attacks.
    alpha-C = the other C=C carbon (bears the substituent).
    Skips aromatic C=C (e.g. a phenyl ring) - only a genuine vinyl double
    bond counts, so a molecule like styrene correctly finds the vinyl bond
    and not a ring bond.
    """
    try:
        mol = pybel.readstring("smi", smiles)
    except OSError as e:
        raise InvalidSmilesError(f"could not parse SMILES: {e}") from e
    mol.addh()
    obmol = mol.OBMol

    for bond in pybel.ob.OBMolBondIter(obmol):
        if bond.GetBondOrder() != 2 or bond.IsAromatic():
            continue
        a1, a2 = bond.GetBeginAtom(), bond.GetEndAtom()
        if a1.GetAtomicNum() != 6 or a2.GetAtomicNum() != 6:
            continue

        hcount1 = sum(1 for nb in pybel.ob.OBAtomAtomIter(a1) if nb.GetAtomicNum() == 1)
        hcount2 = sum(1 for nb in pybel.ob.OBAtomAtomIter(a2) if nb.GetAtomicNum() == 1)

        if hcount1 >= hcount2:
            return a1.GetIdx(), a2.GetIdx()
        return a2.GetIdx(), a1.GetIdx()

    raise InvalidSmilesError(
        "no non-aromatic C=C double bond found - this kp formula only applies "
        "to vinyl monomers (acrylates, methacrylates, styrenics, etc.)"
    )


def write_orca_inputs(job_dir: Path) -> None:
    (job_dir / "mol_opt.in").write_text(OPT_INPUT)
    (job_dir / "A_N.inp").write_text(AN_INPUT)
    (job_dir / "A_Nplus.inp").write_text(ANPLUS_INPUT)
    (job_dir / "A_Nminus.inp").write_text(ANMINUS_INPUT)
