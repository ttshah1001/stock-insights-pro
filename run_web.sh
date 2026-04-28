#!/bin/bash
# Start the Quant Stock Analysis web app. Then open http://127.0.0.1:5000 in your browser.
cd "$(dirname "$0")"
echo "Starting server at http://127.0.0.1:5000"
echo "Press Ctrl+C to stop"
python3 app.py
