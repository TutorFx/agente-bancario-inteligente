from pathlib import Path
from streamlit.testing.v1 import AppTest
import pytest

def test_app_loads_correctly():
    app_path = Path(__file__).resolve().parent.parent.parent / "streamlit_app.py"
    at = AppTest.from_file(str(app_path)).run()
    assert not at.exception

