"""
Gunicorn configuration for Financial Pipeline.

The post_fork hook starts APScheduler inside the worker process (after the
fork), so the scheduler's background thread and the request handlers share
the same process memory.

Without this, start_scheduler() fires in the gunicorn master process during
app module import.  Worker processes inherit a copy of the _scheduler object
where .running=True, but the background thread was not forked — threads are
never inherited across fork().  The result: add_job() writes to the worker's
in-memory job store, while the heartbeat thread runs in the master reading
from a completely separate job store.  They never see each other's jobs.
"""
import logging

logger = logging.getLogger(__name__)


def post_fork(server, worker):
    """Called by gunicorn in the worker process immediately after forking.

    We start APScheduler here so the scheduler thread lives in the same
    process that handles HTTP requests.
    """
    from scheduler import start_scheduler
    logger.info("[worker PID %d] post_fork: starting scheduler", worker.pid)
    start_scheduler()
