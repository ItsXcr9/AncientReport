#!/bin/bash
# AncientReport AI - Startup Script

export PYTHONPATH=/home/AncientReport/analysis/src:$PYTHONPATH
export GEMINI_API_KEY="AIzaSyBPVfd9gaxGvc0FWZzcruZghvWa7MCTcJQ"
export AI_PROVIDER="google"
export AI_MODEL="gemini-2.5-flash-lite"

cd /home/AncientReport/analysis
venv/bin/uvicorn src.main:app --host 0.0.0.0 --port 8800
