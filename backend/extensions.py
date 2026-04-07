import os

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

_storage_uri = os.getenv("RATELIMIT_STORAGE_URI", "memory://")

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri=_storage_uri,
    headers_enabled=True,
)
