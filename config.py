import os

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_DIR  = os.path.join(BASE_DIR, "data")
RAW_DIR   = os.path.join(DATA_DIR, "raw")
CLEAN_DIR = os.path.join(DATA_DIR, "clean")
CHARTS_DIR = os.path.join(DATA_DIR, "charts")
DB_PATH   = os.path.join(DATA_DIR, "reporting.db")

# Ensure all data directories exist at import time
for _dir in (DATA_DIR, RAW_DIR, CLEAN_DIR, CHARTS_DIR):
    os.makedirs(_dir, exist_ok=True)
