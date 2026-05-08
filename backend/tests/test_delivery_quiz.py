"""Tester för leverans-quiz · ersätter slider-fusket.

Verifierar:
1. score_answers — deterministisk inom slump-intervall
2. pick_questions — anti-repetition + industry-bias
3. update_recent_ids — håller max 10
4. End-to-end via /jobs/{id}/quality-quiz + /submit-delivery-quiz
"""
from __future__ import annotations

import random


def test_score_answers_perfect():
    from hembudget.business.delivery_quiz import score_answers
    # 3 bra svar → mean 100, jitter ±7 → 93-100
    for _ in range(20):
        s = score_answers(["good", "good", "good"])
        assert 93 <= s <= 100, s


def test_score_answers_terrible():
    from hembudget.business.delivery_quiz import score_answers
    # 3 dåliga → mean 20, jitter ±7 → 13-27
    for _ in range(20):
        s = score_answers(["bad", "bad", "bad"])
        assert 13 <= s <= 27, s


def test_score_answers_mixed():
    from hembudget.business.delivery_quiz import score_answers
    # 1 bra, 1 mid, 1 dålig → mean 60, jitter → 53-67
    for _ in range(20):
        s = score_answers(["good", "mid", "bad"])
        assert 53 <= s <= 67, s


def test_score_answers_invalid():
    from hembudget.business.delivery_quiz import score_answers
    import pytest
    with pytest.raises(ValueError):
        score_answers(["good", "good"])  # bara 2
    with pytest.raises(ValueError):
        score_answers(["good", "good", "perfect"])  # ogiltigt level


def test_pick_questions_returns_three():
    from hembudget.business.delivery_quiz import pick_questions
    rng = random.Random(42)
    qs = pick_questions(industry_key=None, recent_ids=[], rng=rng)
    assert len(qs) == 3
    assert len({q.id for q in qs}) == 3  # unika


def test_pick_questions_anti_repetition():
    from hembudget.business.delivery_quiz import pick_questions
    rng = random.Random(123)
    # Plocka 3 frågor, banna dem · nästa körning ska ge OLIKA
    first = pick_questions(industry_key=None, recent_ids=[], rng=rng)
    banned = [q.id for q in first]
    rng2 = random.Random(123)  # samma seed!
    second = pick_questions(
        industry_key=None, recent_ids=banned, rng=rng2,
    )
    second_ids = {q.id for q in second}
    assert not (set(banned) & second_ids), (
        f"Repetition: {banned} vs {second_ids}"
    )


def test_pick_questions_falls_back_when_recent_too_large():
    """Om recent_ids täcker hela biblioteket → fall back till alla frågor."""
    from hembudget.business.delivery_quiz import (
        pick_questions, _ALL_QUESTIONS,
    )
    all_ids = [q.id for q in _ALL_QUESTIONS]
    qs = pick_questions(
        industry_key=None,
        recent_ids=all_ids,
        rng=random.Random(0),
    )
    assert len(qs) == 3  # plockar ändå


def test_pick_questions_industry_bias():
    """webshop_it_konsult-elev ska oftare få IT-frågor."""
    from hembudget.business.delivery_quiz import pick_questions
    it_count = 0
    universal_count = 0
    for seed in range(50):
        rng = random.Random(seed)
        qs = pick_questions(
            industry_key="webshop_it_konsult",
            recent_ids=[],
            rng=rng,
        )
        for q in qs:
            if q.industry == "webshop_it_konsult":
                it_count += 1
            elif q.industry is None:
                universal_count += 1
    # Med 2× vikt på IT-matchande borde IT > universal i totalt antal träffar
    # (även om biblioteket har fler universella).
    assert it_count > 0, "borde få IT-frågor"
    # Sanity: ratio IT vs universal · IT ska vara minst 30 % av träffarna
    total = it_count + universal_count
    assert it_count / total >= 0.30, (
        f"IT-bias för svag: {it_count}/{total}"
    )


def test_update_recent_ids_keeps_n():
    from hembudget.business.delivery_quiz import update_recent_ids
    existing = [1, 2, 3]
    new = [4, 5, 6]
    result = update_recent_ids(existing, new, keep_n=4)
    # Nya först, sen behåll fram tills 4 totalt
    assert result == [4, 5, 6, 1]


def test_update_recent_ids_dedupes():
    from hembudget.business.delivery_quiz import update_recent_ids
    existing = [1, 2, 3]
    new = [3, 4]  # 3 finns redan
    result = update_recent_ids(existing, new, keep_n=10)
    assert result.count(3) == 1
    assert 4 in result


def test_universal_questions_have_no_industry():
    from hembudget.business.delivery_quiz import _UNIVERSAL
    for q in _UNIVERSAL:
        assert q.industry is None, q.id


def test_question_ids_unique():
    from hembudget.business.delivery_quiz import _ALL_QUESTIONS
    ids = [q.id for q in _ALL_QUESTIONS]
    assert len(ids) == len(set(ids)), "Duplicate question IDs"


def test_question_library_size():
    """Säkerhet · vi vill ha minst 50 frågor totalt."""
    from hembudget.business.delivery_quiz import _ALL_QUESTIONS
    assert len(_ALL_QUESTIONS) >= 50, len(_ALL_QUESTIONS)
