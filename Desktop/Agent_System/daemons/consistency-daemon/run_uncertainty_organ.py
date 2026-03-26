#!/usr/bin/env python3
"""Entrypoint for starting the Uncertainty Organ as a standalone HTTP service."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from consistency_daemon.uncertainty_organ import app
import uvicorn

port = int(os.environ.get("UNCERTAINTY_ORGAN_PORT", "8422"))
uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
