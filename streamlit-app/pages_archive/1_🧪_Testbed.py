"""
Testbed Dashboard - Accessible via Streamlit Pages
This file makes the testbed accessible via Streamlit's native
multi-page app feature
"""
import sys
from pathlib import Path
import importlib.util

# Add parent directory to path to import testbed
parent_dir = Path(__file__).parent.parent
if str(parent_dir) not in sys.path:
    sys.path.insert(0, str(parent_dir))

# Import testbed module - testbed.py is in parent directory
try:
    # Direct import - testbed.py is in streamlit-app/ directory
    testbed_path = parent_dir / "testbed.py"
    if testbed_path.exists():
        spec = importlib.util.spec_from_file_location(
            "testbed", testbed_path
        )
        testbed_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(testbed_module)
        main = testbed_module.main
    else:
        # Fallback: try regular import
        from testbed import main
except ImportError as e:
    # If import fails, show error in Streamlit
    import streamlit as st
    st.error(f"❌ Failed to import testbed module: {e}")
    st.info(f"Looking for testbed.py in: {parent_dir}")
    st.info(f"Python path: {sys.path}")
    raise

# In Streamlit multi-page apps, code executes directly
# (no if __name__ == "__main__")
main()
