"""
Gunicorn configuration — kept at project root so it is found correctly
when gunicorn is invoked with --chdir backend and -c ../gunicorn.conf.py.

Placing settings here (rather than on the command line) avoids silent
truncation or misquoting by Render's deploy infrastructure.

gevent worker: long-running pipeline requests (yfinance fetch + PDF gen)
are I/O-bound.  gevent's cooperative multitasking handles them without
blocking the worker or triggering Gunicorn's SIGABRT timeout kill.
"""
worker_class       = "eventlet"
workers            = 1    # exactly one worker — APScheduler is not multi-process safe
worker_connections = 1000
timeout            = 300  # generous ceiling; eventlet doesn't use sync-worker heartbeat
keepalive          = 5
loglevel           = "info"
