# Deploying kp_webapp on the lab server

Target machine: your own Linux server, reachable as `<user>@<your-server-ip>`
(referred to below as `your-server` - set that up as a `Host` alias in your
own `~/.ssh/config`). Everything - the FastAPI app, OpenBabel, ORCA, and
Multiwfn - runs on this one machine. No SSH orchestration to a separate HPC
cluster; the app just shells out to local binaries.

## 0. Current status (as of first setup, 2026-08-12)

| Component | Status |
|---|---|
| Multiwfn | Installed at `~/software/Multiwfn/Multiwfn_noGUI`, verified (prints version banner, no missing shared libs) |
| OpenBabel + Python deps | Installed via conda-forge in the `kp_webapp` env (`~/software/miniforge3/envs/kp_webapp`), verified (`obabel`, `pybel`, `fastapi`, `uvicorn`, `slowapi` all import/run) |
| ORCA | **Not installed.** Gated behind an academic login + EULA on the ORCA Forum - cannot be automated. See below. |

Re-running `deploy/setup_server.sh` reproduces Multiwfn + the conda env from
scratch if this box is ever wiped; it just checks for ORCA and tells you if
it's missing rather than trying to fetch it.

## 1. Getting ORCA in place (blocks the pipeline until done)

1. Log into https://orcaforum.kofo.mpg.de with your academic account and
   download the **Linux x86_64** ORCA build (the same version/level of
   theory doesn't matter for reproducing already-fitted results, but do use
   a 6.x release since that's what `fukui_2`/`fukui_3` were computed with).
2. Get the tarball onto the server, either:
   ```bash
   scp orca_6_x_x_linux_x86-64.tar.zst your-server:~/software/
   ```
   or download it there directly if the ORCA Forum session works over SSH+browser auth (usually easier from your own machine).
3. On the server, extract it so the `orca` executable ends up at
   `~/software/orca/orca` (this is `pipeline/config.py`'s default `ORCA_BIN`
   path; override via the `Environment=ORCA_BIN=...` line in
   `kp_webapp.service` if you'd rather keep it somewhere else):
   ```bash
   ssh your-server
   mkdir -p ~/software/orca
   tar --zstd -xf ~/software/orca_6_x_x_linux_x86-64.tar.zst -C ~/software/orca --strip-components=1
   ~/software/orca/orca --version   # sanity check
   ```
4. ORCA also needs its OpenMPI runtime on `LD_LIBRARY_PATH` for parallel
   runs - since every job here runs single-threaded (no `%pal` block, see
   `pipeline/orca_runner.py`), this usually isn't needed, but if a job fails
   with a shared-library error mentioning `libmpi`, add the ORCA install
   dir's `lib` (or wherever `openmpi` landed) to `LD_LIBRARY_PATH` in
   `kp_webapp.service`'s `[Service]` block.

## 2. Get the code onto the server

Easiest for fast iteration: rsync straight from your dev machine (no GitHub
credentials needed on the server at all):

```bash
rsync -av --exclude '.venv' --exclude '__pycache__' \
  /path/to/kp_prediction/ your-server:~/kp_webapp/
```

Static frontend changes (`web/index.html`) are live immediately - FastAPI's
`FileResponse` reads it fresh from disk each request, no restart needed.
Any `.py` change needs a service restart (below).

Alternatively, `git clone` this repo directly on the server (it's public, so
no deploy key is required) and `git pull` to update instead of rsyncing.

## 3. First-time environment setup

```bash
ssh your-server
bash ~/kp_webapp/deploy/setup_server.sh
```

(Multiwfn + the conda env are already done as of this writing - this is
mainly useful if the box gets wiped, or to double check ORCA's presence.)

## 4. Run it (localhost only, for testing)

```bash
ssh your-server
~/software/miniforge3/envs/kp_webapp/bin/uvicorn --app-dir ~/kp_webapp api.main:app --port 8001
```

From another terminal (or another ssh session):
```bash
ssh your-server "curl -s http://127.0.0.1:8001/health"
ssh your-server "curl -s -X POST http://127.0.0.1:8001/api/submit -H 'Content-Type: application/json' -d '{\"smiles\":\"C=CC(=O)OC\"}'"
```

## 5. systemd (needs sudo - run these yourself)

```bash
sudo cp ~/kp_webapp/deploy/kp_webapp.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kp_webapp
sudo systemctl status kp_webapp
```

After any `.py` change + rsync:
```bash
sudo systemctl restart kp_webapp
```

**Always verify with a real request after a restart**, not just
`systemctl status` showing `active (running)` - a process can be running
while still serving pre-restart code if the restart silently no-op'd, or
crash-looping on an import error that `status` alone won't surface:
```bash
ssh your-server "curl -s http://127.0.0.1:8001/health"
```

## 6. Cloudflare quick tunnel (temporary public URL, zero firewall changes)

If you're already running another app's quick tunnel on this box (e.g. on
port 8000), that's fine - `cloudflared` supports as many concurrent quick
tunnels as you start, each gets its own random `trycloudflare.com` hostname:

```bash
ssh your-server
nohup ~/bin/cloudflared tunnel --url http://127.0.0.1:8001 > ~/kp_webapp_cloudflared.log 2>&1 &
disown
sleep 3
grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' ~/kp_webapp_cloudflared.log
```

That URL is public and unauthenticated the moment the tunnel is up - fine
for "let a labmate try it today," but it changes on every restart and isn't
meant to be a permanent link. Rate limiting in `api/main.py` (`5/minute` on
submit) is the only thing standing between this and someone hammering your
GPU/CPU with ORCA jobs once the URL leaks past your intended audience.

## 7. Going further (do this later, only once asked)

- A **named** Cloudflare tunnel + real domain/subdomain for a stable URL
  instead of the quick tunnel's throwaway hostname.
- Bumping `api/queue.py`'s `N_WORKERS` past 1 and adding a `%pal nprocs N`
  block to the ORCA inputs in `pipeline/inputs.py`, if a single sequential
  job at a time turns out to be too slow for real usage - the box has 64
  cores, currently unused by this app beyond one job's single thread.
