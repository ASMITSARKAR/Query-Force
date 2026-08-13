import pytest
from src.rag.rules import inject_business_rules

def test_inject_business_rules_exact():
    q = "What is our AOV?"
    res = inject_business_rules(q)
    assert "Average Order Value" in res

def test_inject_business_rules_fuzzy():
    q = "What is our aovv?"
    res = inject_business_rules(q)
    assert "Average Order Value" in res

def test_inject_business_rules_broad():
    q = "Show me the key metrics"
    res = inject_business_rules(q)
    assert "Business Rules to strictly follow:" in res
    assert "System Note: The user is asking for general insights or metrics." in res
