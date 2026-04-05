"""
Apply gevent monkey-patching before any other module is imported.

ssl=False: do NOT patch Python's ssl module. This avoids the infinite-
recursion crash that occurs when gevent's ssl patch conflicts with
urllib3's TLSVersion.TLSv1_2 setter. Network I/O still benefits from
gevent's socket patching; only the ssl wrapper is left unpatched.

This module must be imported as the very first line of app.py.
"""
from gevent import monkey
monkey.patch_all(ssl=False)
