import pytest
from root_agent.dependencies import get_banco_agil_adapter

def test_lazy_loading_adapter():
    adapter1 = get_banco_agil_adapter()
    adapter2 = get_banco_agil_adapter()
    
    assert adapter1 is not None
    assert adapter1 is adapter2
