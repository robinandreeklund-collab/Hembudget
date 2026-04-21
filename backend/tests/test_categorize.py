from hembudget.categorize.engine import normalize_merchant


def test_normalize_strips_noise():
    assert normalize_merchant("ICA NÄRA STOCKHOLM *1234") == "ICA NÄRA STOCKHOLM"
    assert normalize_merchant("SPOTIFY SE 123456789") == "SPOTIFY SE"
    assert normalize_merchant("AMEX [STOCKHOLM]") == "AMEX"
    assert normalize_merchant("") == ""


def test_rules_match_seed():
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


def test_swish_in_rule_rejects_negative_amount():
    """Säkerhetsnät: en 'Swish in'-regel ska inte matcha en utgift, även
    om merchant-strängen innehåller 'swish'."""
    from hembudget.categorize.rules import RuleEngine
    from hembudget.db.models import Rule

    rules = [
        Rule(id=1, pattern="swish", is_regex=False, category_id=10, priority=100),
    ]
    cats = {10: "Swish in"}
    eng = RuleEngine(rules, categories_by_id=cats)

    # Positivt belopp → matchar
    assert eng.match("Swish inbetalning PENELOPE", amount=189.0) is not None
    # Negativt belopp → matchar INTE (det borde vara Swish ut)
    assert eng.match("Swish betalning SKATTEVERKET", amount=-159.0) is None


def test_swish_ut_rule_rejects_positive_amount():
    from hembudget.categorize.rules import RuleEngine
    from hembudget.db.models import Rule

    rules = [
        Rule(id=1, pattern="swish", is_regex=False, category_id=10, priority=100),
    ]
    cats = {10: "Swish ut"}
    eng = RuleEngine(rules, categories_by_id=cats)

    assert eng.match("Swish betalning", amount=-50.0) is not None
    assert eng.match("Swish inbetalning", amount=50.0) is None
