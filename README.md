# kp_prediction

Predicts the free-radical propagation rate constant **kp(T)** for a vinyl
monomer directly from its SMILES string, by running a small quantum
chemistry pipeline (ORCA + Multiwfn) and combining the resulting Conceptual
DFT descriptors through a fitted Arrhenius-type model. Ships as both a
standalone Python pipeline and a small async web app (FastAPI + vanilla JS)
that runs it on demand.

A calculation takes several minutes (geometry optimization + 3 single-point
calculations + a CDFT analysis), so this is not a sub-second predictor - it's
meant to replace manually driving ORCA/Multiwfn by hand for one monomer at a
time, not to compete with a trained ML surrogate on latency.

## Try it online

No need to install anything or run the pipeline yourself - a hosted instance
is running at:

**https://win-fotos-pearl-alignment.trycloudflare.com**

Submit a SMILES string, watch it progress through each pipeline stage, and
get back kp(T) plus a chart. (This is a Cloudflare quick-tunnel URL, not a
permanent domain - if it's gone dead, the instance has likely been
restarted; open an issue and I'll update the link.)

## The method

### Background

Conceptual DFT (CDFT) describes a molecule's local reactivity using
[**Fukui functions**](https://en.wikipedia.org/wiki/Fukui_function),
derived from how the electron density redistributes when an electron is
added or removed:

- **f⁻** - reactivity toward an electrophile (computed from the N and N&minus;1
  electron densities)
- **f⁺** - reactivity toward a nucleophile/radical (computed from the N and
  N+1 electron densities)
- **local softness** s⁻ = f⁻ × S, s⁺ = f⁺ × S, where S = 1/(2η) is the
  global softness and η = (IP&minus;EA)/2 is the hardness

For a vinyl monomer CH₂=CR(X) undergoing radical propagation, the two atoms
that matter are:

- **beta-C** - the terminal, unsubstituted `CH2=` carbon (more attached H) -
  the site a propagating radical actually attacks
- **alpha-C** - the substituted `=CR(X)` carbon

### Pipeline

For a given SMILES:

1. **3D geometry** - OpenBabel embeds an initial 3D structure
   (`--gen3d --ff MMFF94`, falling back to plain `--gen3d` if that fails).
2. **Vinyl carbon identification** - the SMILES is re-parsed to find a
   non-aromatic C=C double bond; the carbon with more attached hydrogens is
   beta-C, the other is alpha-C. Aromatic C=C bonds are explicitly excluded
   so a styrenic vinyl group isn't confused with its phenyl ring.
3. **Geometry optimization** - ORCA, `B3LYP def2-SVP Opt TightSCF`.
4. **Three single-point calculations** on the optimized geometry, all
   `B3LYP-D4 def2-SVP TightSCF SP`:
   - **N electrons** (neutral, charge 0, singlet)
   - **N+1 electrons** (anion, charge &minus;1, doublet)
   - **N&minus;1 electrons** (cation, charge +1, doublet)

   ("Nplus"/"Nminus" name the *electron count* relative to N, not the charge
   sign - `A_Nplus` is the extra-electron state, i.e. the **anion**.)
5. **Conceptual DFT analysis** - Multiwfn reads the three `.gbw` files
   (menu path `22` → `2`, condensed Fukui functions via Hirshfeld
   partitioning) and writes a `CDFT.txt` with, per atom, q(N)/q(N+1)/q(N&minus;1),
   f⁻/f⁺/f⁰, and the dual descriptor.
6. **Descriptor extraction** - reads f⁻ and f⁺ at the beta-C and alpha-C
   atom indices from `CDFT.txt`, and independently recomputes softness
   (`s = f × S`) from the SCF energies in the three ORCA `.out` files rather
   than trusting Multiwfn's own softness table. This sidesteps a real bug:
   ORCA 6 LeanSCF runs can make Multiwfn read E(N)/E(N+1)/E(N&minus;1) as
   exactly zero, which silently poisons every energy-derived quantity
   (hardness, softness, electrophilicity) while leaving the Fukui functions
   themselves correct (they're pure electron-density differences, not
   energy-dependent). Recomputing S from the `.out` files directly is
   correct regardless of whether a given run hits this bug.
7. **The fitted formula** - four descriptors go into a linear model for
   ln A and Ea (all softness terms in `e·Hartree⁻¹`, i.e. computed with η in
   Hartree, *not* eV):

   ```
   ln A          = -9.80  + 3.31  · β(s⁻) + 77.3 · α(s⁺)
   Ea (kJ/mol)   = -55.9  + 35.0  · β(f⁻) + 137  · β(s⁺)
   kp(T)         = exp( ln A - Ea·1000 / (R·T) )        R = 8.314 J mol⁻¹ K⁻¹
   ```

   Fitted against a set of ~30 acrylate/methacrylate monomers with DFT
   descriptors computed at exactly the level of theory in step 3-4 above.
   **Changing that level of theory invalidates these coefficients** - they'd
   need to be refit against new descriptors.

The full implementation is in [`pipeline/`](pipeline/) - each step above
corresponds to one module (`inputs.py`, `orca_runner.py`,
`multiwfn_runner.py`, `cdft_parse.py`, `formula.py`), orchestrated by
`job.py`.

### Using the method without the web app

```python
from pipeline.job import new_job, run_pipeline

job = new_job("C=CC(=O)OC")   # methyl acrylate
run_pipeline(job)             # runs obabel + ORCA + Multiwfn, several minutes
print(job.result)
# {'smiles': ..., 'beta_atom_idx': 1, 'alpha_atom_idx': 2,
#  'descriptors': {...}, 'ln_A': ..., 'Ea_kJ_per_mol': ...,
#  'kp_298_15K': ..., 'kp_sweep': [{'T_K': 273.0, 'kp': ...}, ...]}
```

This requires ORCA, Multiwfn, and OpenBabel to be installed and discoverable
via `pipeline/config.py` (see [Requirements](#requirements) below) - no
FastAPI/web dependency needed for this path at all.

## Repository layout

```
pipeline/       inference-only pipeline, zero web-framework dependency
  inputs.py       SMILES -> geometry, vinyl-carbon ID, ORCA input files
  orca_runner.py  subprocess wrapper around ORCA
  multiwfn_runner.py   drives Multiwfn's CDFT module
  cdft_parse.py   CDFT.txt + ORCA .out -> the four descriptors
  formula.py      descriptors -> ln A, Ea, kp(T)
  job.py          ties the above into one job's state machine
api/            FastAPI wrapper (validation, rate limiting, routing only)
web/            single-file frontend
deploy/         systemd unit, environment.yml, and a deploy walkthrough
```

## Requirements

| Tool | Why | Notes |
|---|---|---|
| [ORCA](https://orcaforum.kofo.mpg.de) 6.x | geometry opt + single points | Free for academic use, but gated behind a forum login + EULA - **not** pip/conda-installable, download it yourself |
| [Multiwfn](http://sobereva.com/multiwfn/) | Conceptual DFT / Fukui analysis | Free, no login required |
| [OpenBabel](http://openbabel.org/) (`obabel` + the `pybel` Python bindings) | SMILES → 3D geometry, vinyl-carbon identification | Installed here via conda-forge (`deploy/environment.yml`) - no reliable pip wheel, and apt needs sudo |
| Python 3.11+ | everything else | `fastapi`, `uvicorn`, `slowapi`, `pydantic` - only needed for the web layer, not for `pipeline/` on its own |

## Setting up your own instance

See [`deploy/README.md`](deploy/README.md) for the full walkthrough
(environment setup, systemd service, exposing it with a Cloudflare tunnel).
Short version:

```bash
git clone https://github.com/aaron-1999/kp_prediction.git
cd kp_prediction
bash deploy/setup_server.sh   # Multiwfn + conda env; tells you if ORCA is missing
# ... get ORCA in place yourself, see deploy/README.md section 1 ...
conda activate kp_webapp
uvicorn api.main:app --port 8001
```

## Limitations

- The fitted formula was trained on a specific set of acrylate/methacrylate
  monomers - treat predictions for very different chemistries (e.g. bulky
  or highly conjugated substituents) as extrapolation, not validated
  prediction.
- Single global model, not split by monomer class - see the descriptor
  extraction note above about why local softness is recomputed rather than
  trusted from Multiwfn directly.
- This is a research tool. Predictions are not a substitute for experimental
  kinetics measurement.

## Citing the tools this depends on

If you use this for published work, cite the underlying software per their
own policies - notably Multiwfn requires citing both:
Tian Lu, Feiwu Chen, *J. Comput. Chem.* **33**, 580 (2012);
Tian Lu, *J. Chem. Phys.* **161**, 082503 (2024).
