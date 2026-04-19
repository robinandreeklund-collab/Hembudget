from hembudget.categorize.engine import normalize_merchant


def test_normalize_strips_noise():
    assert normalize_merchant("ICA NÄRA STOCKHOLM *1234") == "ICA NÄRA STOCKHOLM"
    assert normalize_merchant("SPOTIFY SE 123456789") == "SPOTIFY SE"
    assert normalize_merchant("AMEX [STOCKHOLM]") == "AMEX"
    assert normalize_merchant("") == ""


def test_rules_match_seed():
    from unittest.mock import MagicMock

    from hembudget.categorize.rules import RuleEngine
    from hembudget.db.models import Rule

    rules = [
        Rule(id=1, pattern="spotify", is_regex=False, category_id=10, priority=100),
        Rule(id=2, pattern="ica", is_regex=False, category_id=20, priority=100),
    ]
    eng = RuleEngine(rules)
    assert eng.match("Spotify SE 201234").category_id == 10
    assert eng.match("ICA Maxi Uppsala").category_id == 20
    assert eng.match("Något annat") is None
