#!/usr/bin/env bash
# Explicit Owner provisioning only. Runtime never invokes this script.
set -euo pipefail
cd "$(dirname "$0")/.."
python3.12 -m venv .venv
.venv/bin/python -m pip install 'torch==2.8.0+cpu' --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r research/timesfm_cpu/requirements.lock --extra-index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip check
.venv/bin/python research/timesfm_cpu/provision.py models/timesfm-2.5
