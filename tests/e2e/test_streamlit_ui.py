from streamlit.testing.v1 import AppTest
import pytest

def test_app_loads_correctly():
    at = AppTest.from_file("streamlit_app.py").run()
    assert not at.exception
