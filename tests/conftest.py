"""pytest configuration and fixtures.

PYTHON VERSION NOTE:
This test suite is validated on Python 3.11-3.12. Python 3.11 matches production
(Dockerfile). Python 3.12+ on Windows may encounter pytest+tempfile teardown issues;
run in WSL or Docker if this occurs.
"""
from __future__ import annotations
