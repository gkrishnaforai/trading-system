"""
Trading System Admin Dashboard - Main Entry Point
Run this with: streamlit run admin_main.py
"""
import streamlit as st
import sys
import os

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from admin_dashboard import main

if __name__ == "__main__":
    main()
