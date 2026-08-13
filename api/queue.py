"""
Single-worker FIFO job queue. One ORCA pipeline runs at a time - each job is
already CPU/time-heavy on its own (geometry opt + 3 single points + CDFT),
and this is a small interactive demo, not a batch cluster. If load grows,
increase N_WORKERS and pipeline.orca_runner can be given a %pal block, but
don't do either until real usage shows it's needed.
"""

import queue
import threading
from typing import Optional

from pipeline.job import Job, new_job, run_pipeline

_jobs: dict[str, Job] = {}
_lock = threading.Lock()
_queue: "queue.Queue[str]" = queue.Queue()

N_WORKERS = 1


def _worker():
    while True:
        job_id = _queue.get()
        job = _jobs.get(job_id)
        if job is not None:
            run_pipeline(job)
        _queue.task_done()


for _ in range(N_WORKERS):
    threading.Thread(target=_worker, daemon=True).start()


def submit_job(smiles: str) -> Job:
    job = new_job(smiles)
    with _lock:
        _jobs[job.id] = job
    _queue.put(job.id)
    return job


def get_job(job_id: str) -> Optional[Job]:
    with _lock:
        return _jobs.get(job_id)


def queue_position(job_id: str) -> int:
    """0 = currently running or next up, N = N jobs ahead of it."""
    with _lock:
        pending = [jid for jid, j in _jobs.items() if j.stage == "queued" and not j.failed]
    try:
        return pending.index(job_id)
    except ValueError:
        return 0
