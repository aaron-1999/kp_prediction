#!/bin/bash
# One-time environment setup on <user>@<your-server-ip>. Idempotent - safe to
# re-run. The conda env + Multiwfn + OpenBabel were already set up manually
# once (2026-08-12); this script documents exactly what was done so it's
# reproducible on a fresh box or after a wipe.
set -euo pipefail

SOFTWARE_DIR="$HOME/software"
mkdir -p "$SOFTWARE_DIR"

# ---- Multiwfn (CDFT engine) ------------------------------------------------
if [ ! -x "$SOFTWARE_DIR/Multiwfn/Multiwfn_noGUI" ]; then
    echo "Installing Multiwfn..."
    cd "$SOFTWARE_DIR"
    curl -sL -o Multiwfn_Linux_noGUI.zip \
        http://sobereva.com/multiwfn/misc/Multiwfn_2026.7.15_bin_Linux_noGUI.zip
    unzip -q Multiwfn_Linux_noGUI.zip -d Multiwfn_tmp
    mv Multiwfn_tmp/Multiwfn_*_bin_Linux_noGUI Multiwfn
    rmdir Multiwfn_tmp
    chmod +x Multiwfn/Multiwfn_noGUI
    rm -f Multiwfn_Linux_noGUI.zip
else
    echo "Multiwfn already installed, skipping."
fi

# ---- Miniforge (conda-forge) + kp_webapp env -------------------------------
# OpenBabel needs its Python bindings (pybel) and this box has no sudo (no
# apt install libopenbabel-dev, no pip wheel that reliably works) - conda-
# forge is the path of least resistance for both OpenBabel and the web app's
# own Python deps living in one place.
if [ ! -d "$SOFTWARE_DIR/miniforge3" ]; then
    echo "Installing Miniforge..."
    cd "$SOFTWARE_DIR"
    curl -sL -o miniforge.sh \
        https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
    bash miniforge.sh -b -p "$SOFTWARE_DIR/miniforge3"
    rm -f miniforge.sh
else
    echo "Miniforge already installed, skipping."
fi

if ! "$SOFTWARE_DIR/miniforge3/bin/conda" env list | grep -q '^kp_webapp '; then
    echo "Creating kp_webapp conda env..."
    "$SOFTWARE_DIR/miniforge3/bin/conda" env create -f "$(dirname "$0")/environment.yml"
else
    echo "kp_webapp conda env already exists, skipping."
fi

# ---- ORCA -------------------------------------------------------------------
# NOT automatable: ORCA is gated behind an academic login + EULA on the ORCA
# Forum (orcaforum.kofo.mpg.de). Download the Linux x86_64 build yourself and
# either scp it here directly, or extract it so the binary ends up at
# exactly this path (pipeline/config.py's default, override with $ORCA_BIN
# in the systemd unit if you install it somewhere else):
#   ~/software/orca/orca
if [ ! -x "$SOFTWARE_DIR/orca/orca" ]; then
    echo ""
    echo "!!! ORCA not found at $SOFTWARE_DIR/orca/orca - the pipeline cannot run"
    echo "    without it. Download the Linux x86_64 build from"
    echo "    https://orcaforum.kofo.mpg.de (requires your academic account),"
    echo "    then: scp <tarball> <user>@<your-server-ip>:~/software/ && ssh in and extract"
    echo "    it so orca (the executable) lives at $SOFTWARE_DIR/orca/orca"
fi

echo ""
echo "Done. Verify with:"
echo "  ~/software/Multiwfn/Multiwfn_noGUI  (should print version banner)"
echo "  ~/software/miniforge3/envs/kp_webapp/bin/obabel -:'C=CC(=O)OC' -oxyz --gen3d"
echo "  ~/software/orca/orca --version   (once ORCA is in place)"
