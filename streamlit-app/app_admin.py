"""
Trading System Admin Dashboard - Legacy Entry Point
This file now redirects to the admin dashboard.
"""
import streamlit as st
import sys
import os

# Add current directory to path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Redirect to admin dashboard
from admin_dashboard import main

if __name__ == "__main__":
    main()
