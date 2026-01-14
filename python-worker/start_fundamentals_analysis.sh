#!/bin/bash

# Start Fundamentals Analysis UI
echo "🚀 Starting Fundamentals Analysis Dashboard on port 8503..."
cd /Users/krishnag/tools/trading-system/python-worker
streamlit run streamlit_fundamentals_analysis.py --server.port 8503 --server.headless false
