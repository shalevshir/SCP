"""Pytest configuration for dashboard core tests.

Sets up Python path before test imports.
"""

import sys
from pathlib import Path

# Get project root
# This file is at: tests/unit/test_dashboard/core/conftest.py
# Project root is 5 levels up (core -> test_dashboard -> unit -> tests -> SCP)
_this_file = Path(__file__).resolve()
_project_root = _this_file.parent.parent.parent.parent.parent
_project_root_str = str(_project_root)

# Ensure project root is in path BEFORE test imports
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)
