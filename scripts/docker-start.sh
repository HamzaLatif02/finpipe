#!/bin/sh
set -e

echo "============================================"
echo "  Financial Pipeline"
echo "  Starting up..."
echo "============================================"
echo "  FLASK_ENV: ${FLASK_ENV}"
echo "  PORT:      ${PORT}"
echo "  Workers:   1"
echo "============================================"

# Initialise the database before starting the server so tables
# exist before the first request arrives.
python -c "
import sys
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/backend')
from db import init_db
init_db()
print('Database initialised')
try:
    from pg_jobs import init_pg_jobs_table
    init_pg_jobs_table()
    print('PostgreSQL jobs table ready')
except Exception as e:
    print(f'PostgreSQL not configured (OK for local): {e}')
"

# Start gunicorn using the project-level config file.
# --chdir backend : change to backend/ before loading app:app
# -c ../gunicorn.conf.py : config file relative to backend/ CWD
#                          (resolves to /app/gunicorn.conf.py)
# gunicorn.conf.py sets: worker_class=eventlet, workers=1,
#                        timeout=300, keepalive=5
exec gunicorn \
    --chdir backend \
    app:app \
    --bind "0.0.0.0:${PORT}" \
    -c ../gunicorn.conf.py \
    --access-logfile - \
    --error-logfile -
