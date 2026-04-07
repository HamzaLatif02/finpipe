"""
conftest.py — project root

Adds the project root to sys.path so that pytest can import modules
that live in the root directory (analysis.py, chart_analyst.py, etc.)
regardless of how pytest is invoked.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
