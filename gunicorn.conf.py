"""
Gunicorn configuration — kept at project root so it is found correctly
when gunicorn is invoked with --chdir backend and -c ../gunicorn.conf.py.

Placing settings here (rather than on the command line) avoids silent
truncation or misquoting by Render's deploy infrastructure.
"""
workers = 1        # exactly one worker — APScheduler is not multi-process safe
timeout = 120      # allow long-running pipeline requests (fetcher + PDF gen)
loglevel = "info"
