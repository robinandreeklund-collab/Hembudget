"""Tester för P3 — nya assignment_kinds (link_transfer, add_upcoming).

Verifierar att checkers i `teacher/assignments.py` korrekt klassar
status mot elevens scope-DB.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import (
    Assignment, Student, Teacher,
)
from hembudget.security.crypto import hash_password


@pytest.fixture
def fx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Bygger upp en elev + scope-DB så vi kan stoppa in transaktioner
    och kommande poster och köra evaluate() mot dem."""
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    from hembudget.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from hembudget.school import engines as eng_mod
    if eng_mod._master_engine is not None:
        eng_mod._master_engine.dispose()
    eng_mod._master_engine = None
    eng_mod._master_session = None
    for e in list(eng_mod._scope_engines.values()):
        e.dispose()
    eng_mod._scope_engines.clear()
    eng_mod._scope_sessions.clear()

    init_master_engine()

    with master_session() as s:
        t = Teacher(
            email="t@x.se", name="T",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(t); s.flush()
        stu = Student(
            teacher_id=t.id, display_name="A", login_code="LOGINCODE",
        )
        s.add(stu); s.flush()
        sid = stu.id
        # Återhämta som detached objekt (scope_for_student behöver bara
        # id+family_id)
        s.refresh(stu)

        class _Stub:
            id = stu.id
            family_id = stu.family_id

    return _Stub


def _make_assignment(kind: str, **params) -> Assignment:
    a = Assignment(
        teacher_id=1, student_id=1,
        title="t", description="d", kind=kind,
        params=params or None,
    )
    return a


def test_link_transfer_not_started(fx) -> None:
    from hembudget.teacher.assignments import evaluate
    student = fx
    a = _make_assignment("link_transfer", target_count=2)
    res = evaluate(a, student)
    assert res.status == "not_started"
    assert "0/2" in res.progress


def test_link_transfer_in_progress_then_completed(fx) -> None:
    from hembudget.teacher.assignments import evaluate
    from hembudget.db.base import session_scope
    from hembudget.db.models import Account, Transaction
    from hembudget.school.engines import scope_context, scope_for_student
    student = fx

    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            acc = Account(name="Lönekonto", bank="Demo", type="checking", currency="SEK")
            s.add(acc); s.flush()
            # Lägg till 1 transfer
            tx = Transaction(
                account_id=acc.id, date=date(2025, 8, 1),
                amount=Decimal("-100.00"), currency="SEK",
                raw_description="t1", hash="h1",
                is_transfer=True,
            )
            s.add(tx)

    a = _make_assignment("link_transfer", target_count=2)
    res = evaluate(a, student)
    assert res.status == "in_progress"
    assert "1/2" in res.progress

    # Lägg till en till — nu klart
    with scope_context(scope_key):
        with session_scope() as s:
            acc = s.query(Account).first()
            tx = Transaction(
                account_id=acc.id, date=date(2025, 8, 2),
                amount=Decimal("100.00"), currency="SEK",
                raw_description="t2", hash="h2",
                is_transfer=True,
            )
            s.add(tx)

    res = evaluate(a, student)
    assert res.status == "completed"


def test_add_upcoming_not_started(fx) -> None:
    from hembudget.teacher.assignments import evaluate
    student = fx
    a = _make_assignment("add_upcoming", target_count=3)
    res = evaluate(a, student)
    assert res.status == "not_started"
    assert "0/3" in res.progress


def test_add_upcoming_completes_when_target_hit(fx) -> None:
    from hembudget.teacher.assignments import evaluate
    from hembudget.db.base import session_scope
    from hembudget.db.models import UpcomingTransaction
    from hembudget.school.engines import scope_context, scope_for_student
    student = fx

    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            for i, name in enumerate(["Hyra", "El", "Mobil"]):
                s.add(UpcomingTransaction(
                    kind="bill", name=name,
                    amount=Decimal("500.00"),
                    expected_date=date(2025, 8, 25 + i),
                ))

    a = _make_assignment("add_upcoming", target_count=3)
    res = evaluate(a, student)
    assert res.status == "completed"
    assert "3" in res.progress


def test_add_upcoming_default_target_is_one(fx) -> None:
    """Om params saknas ska target_count default till 1 — så att
    enkla 'lägg till en kommande räkning'-uppdrag fungerar utan params."""
    from hembudget.teacher.assignments import evaluate
    from hembudget.db.base import session_scope
    from hembudget.db.models import UpcomingTransaction
    from hembudget.school.engines import scope_context, scope_for_student
    student = fx

    a = _make_assignment("add_upcoming")  # inga params
    res = evaluate(a, student)
    assert res.status == "not_started"

    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            s.add(UpcomingTransaction(
                kind="bill", name="X",
                amount=Decimal("100.00"),
                expected_date=date(2025, 8, 1),
            ))

    res = evaluate(a, student)
    assert res.status == "completed"


def test_make_transfer_not_started(fx) -> None:
    """make_transfer ska börja som 'not_started' när inga överföringar finns."""
    from hembudget.teacher.assignments import evaluate
    student = fx
    a = _make_assignment("make_transfer", target_count=1)
    res = evaluate(a, student)
    assert res.status == "not_started"
    assert "0/1" in res.progress


def test_make_transfer_counts_paired_destinations(fx) -> None:
    """En proaktiv överföring (parad, positivt belopp på destinationen) ska
    räknas — räknar destinationssidan så vi inte dubbelräknar paret."""
    from hembudget.teacher.assignments import evaluate
    from hembudget.db.base import session_scope
    from hembudget.db.models import Account, Transaction
    from hembudget.school.engines import scope_context, scope_for_student
    student = fx

    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            src = Account(name="Lön", bank="Demo", type="checking", currency="SEK")
            dst = Account(name="Spar", bank="Demo", type="savings", currency="SEK")
            s.add_all([src, dst]); s.flush()
            out = Transaction(
                account_id=src.id, date=date.today(),
                amount=Decimal("-200.00"), currency="SEK",
                raw_description="t-out", hash="ho1", is_transfer=True,
            )
            inn = Transaction(
                account_id=dst.id, date=date.today(),
                amount=Decimal("200.00"), currency="SEK",
                raw_description="t-in", hash="hi1", is_transfer=True,
            )
            s.add_all([out, inn]); s.flush()
            out.transfer_pair_id = inn.id
            inn.transfer_pair_id = out.id

    a = _make_assignment("make_transfer", target_count=1)
    res = evaluate(a, student)
    assert res.status == "completed"
    assert "1" in res.progress


def test_make_transfer_filters_by_account_kind(fx) -> None:
    """to_account_kind=savings ska bara räkna överföringar TILL sparkonto."""
    from hembudget.teacher.assignments import evaluate
    from hembudget.db.base import session_scope
    from hembudget.db.models import Account, Transaction
    from hembudget.school.engines import scope_context, scope_for_student
    student = fx

    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            a1 = Account(name="A", bank="Demo", type="checking", currency="SEK")
            a2 = Account(name="B", bank="Demo", type="checking", currency="SEK")
            s.add_all([a1, a2]); s.flush()
            out = Transaction(
                account_id=a1.id, date=date.today(),
                amount=Decimal("-50.00"), currency="SEK",
                raw_description="t-out", hash="hox", is_transfer=True,
            )
            inn = Transaction(
                account_id=a2.id, date=date.today(),
                amount=Decimal("50.00"), currency="SEK",
                raw_description="t-in", hash="hix", is_transfer=True,
            )
            s.add_all([out, inn]); s.flush()
            out.transfer_pair_id = inn.id
            inn.transfer_pair_id = out.id

    # Krav: överföring ska gå till SAVINGS — vi har bara checking → checking
    a = _make_assignment(
        "make_transfer", target_count=1, to_account_kind="savings",
    )
    res = evaluate(a, student)
    assert res.status == "not_started"


def test_make_transfer_filters_by_min_amount(fx) -> None:
    """min_amount=500 ska kräva minst 500 kr per överföring."""
    from hembudget.teacher.assignments import evaluate
    from hembudget.db.base import session_scope
    from hembudget.db.models import Account, Transaction
    from hembudget.school.engines import scope_context, scope_for_student
    student = fx

    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            a1 = Account(name="A", bank="Demo", type="checking", currency="SEK")
            a2 = Account(name="B", bank="Demo", type="savings", currency="SEK")
            s.add_all([a1, a2]); s.flush()
            # 100 kr — under min_amount
            out = Transaction(
                account_id=a1.id, date=date.today(),
                amount=Decimal("-100.00"), currency="SEK",
                raw_description="t", hash="ha", is_transfer=True,
            )
            inn = Transaction(
                account_id=a2.id, date=date.today(),
                amount=Decimal("100.00"), currency="SEK",
                raw_description="t", hash="hb", is_transfer=True,
            )
            s.add_all([out, inn]); s.flush()
            out.transfer_pair_id = inn.id
            inn.transfer_pair_id = out.id

    a = _make_assignment("make_transfer", target_count=1, min_amount=500)
    res = evaluate(a, student)
    assert res.status == "not_started"


def test_stock_open_account_not_started(fx) -> None:
    from hembudget.teacher.assignments import evaluate
    student = fx
    a = _make_assignment("stock_open_account", target_count=1)
    res = evaluate(a, student)
    assert res.status == "not_started"


def test_stock_open_account_completes_when_isk_exists(fx) -> None:
    from hembudget.teacher.assignments import evaluate
    from hembudget.db.base import session_scope
    from hembudget.db.models import Account
    from hembudget.school.engines import scope_context, scope_for_student
    student = fx

    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            s.add(Account(name="ISK1", bank="Demo", type="isk"))

    a = _make_assignment("stock_open_account", target_count=1)
    res = evaluate(a, student)
    assert res.status == "completed"


def test_stock_diversify_not_started(fx) -> None:
    from hembudget.teacher.assignments import evaluate
    student = fx
    a = _make_assignment(
        "stock_diversify", min_holdings=5, min_sectors=3,
    )
    res = evaluate(a, student)
    assert res.status == "not_started"


def test_stock_diversify_completes_with_5_across_3_sectors(fx) -> None:
    from hembudget.teacher.assignments import evaluate
    from hembudget.db.base import session_scope
    from hembudget.db.models import Account, StockHolding
    from hembudget.school.engines import (
        master_session, scope_context, scope_for_student,
    )
    from hembudget.school.stock_seed import seed_stock_universe
    from decimal import Decimal as D
    student = fx

    # Seeda master med stock universe så stock_diversify-checkern kan
    # slå upp sektorer
    with master_session() as ms:
        seed_stock_universe(ms)

    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            isk = Account(name="ISK", bank="Demo", type="isk")
            s.add(isk); s.flush()
            # 5 aktier över 3+ sektorer (Industri, Bank, Telecom)
            for ticker in ["VOLV-B.ST", "ATCO-A.ST", "SEB-A.ST", "TELIA.ST", "ERIC-B.ST"]:
                s.add(StockHolding(
                    account_id=isk.id, ticker=ticker,
                    quantity=10, avg_cost=D("100"),
                ))

    a = _make_assignment(
        "stock_diversify", min_holdings=5, min_sectors=3,
    )
    res = evaluate(a, student)
    assert res.status == "completed"
    assert res.detail["holdings"] == 5
    assert res.detail["sectors"] >= 3


def test_stock_diversify_in_progress_when_only_one_sector(fx) -> None:
    from hembudget.teacher.assignments import evaluate
    from hembudget.db.base import session_scope
    from hembudget.db.models import Account, StockHolding
    from hembudget.school.engines import (
        master_session, scope_context, scope_for_student,
    )
    from hembudget.school.stock_seed import seed_stock_universe
    from decimal import Decimal as D
    student = fx

    with master_session() as ms:
        seed_stock_universe(ms)

    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            isk = Account(name="ISK", bank="Demo", type="isk")
            s.add(isk); s.flush()
            # 5 aktier men alla från Industri
            for ticker in ["VOLV-B.ST", "ATCO-A.ST", "SAND.ST", "ABB.ST", "ALFA.ST"]:
                s.add(StockHolding(
                    account_id=isk.id, ticker=ticker,
                    quantity=10, avg_cost=D("100"),
                ))

    a = _make_assignment(
        "stock_diversify", min_holdings=5, min_sectors=3,
    )
    res = evaluate(a, student)
    assert res.status == "in_progress"


def test_trigger_credit_flow_not_started(fx) -> None:
    from hembudget.teacher.assignments import evaluate
    student = fx
    a = _make_assignment("trigger_credit_flow", target_count=1)
    res = evaluate(a, student)
    assert res.status == "not_started"


def test_trigger_credit_flow_completes_with_application(fx) -> None:
    from hembudget.teacher.assignments import evaluate
    from hembudget.db.base import session_scope
    from hembudget.db.models import CreditApplication
    from hembudget.school.engines import scope_context, scope_for_student
    from decimal import Decimal as D
    student = fx

    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            s.add(CreditApplication(
                kind="private", requested_amount=D("10000"),
                requested_months=24, result="declined",
            ))

    a = _make_assignment("trigger_credit_flow", target_count=1)
    res = evaluate(a, student)
    assert res.status == "completed"


def test_credit_template_seeds(fx) -> None:
    from hembudget.school.module_seed import seed_system_modules
    from hembudget.school.models import Module
    with master_session() as s:
        seed_system_modules(s)
    with master_session() as s:
        m = s.query(Module).filter(
            Module.title == "Kreditmånaden — när pengarna inte räcker",
            Module.teacher_id.is_(None),
        ).first()
        assert m is not None
        assert m.is_template is True
        assert len(m.steps) == 6
        kinds = [
            (st.params or {}).get("assignment_kind")
            for st in m.steps if st.kind == "task"
        ]
        assert "trigger_credit_flow" in kinds


def test_stocks_template_seeds(fx) -> None:
    """Aktiemodulen ska seedas som systemmodul med 8 steg."""
    from hembudget.school.module_seed import seed_system_modules
    from hembudget.school.models import Module
    with master_session() as s:
        seed_system_modules(s)
    with master_session() as s:
        m = s.query(Module).filter(
            Module.title == "Aktier — komma igång",
            Module.teacher_id.is_(None),
        ).first()
        assert m is not None
        assert m.is_template is True
        assert len(m.steps) == 8
        kinds = [
            (st.params or {}).get("assignment_kind")
            for st in m.steps if st.kind == "task"
        ]
        assert "stock_open_account" in kinds
        assert "make_transfer" in kinds
        assert "stock_diversify" in kinds


def test_system_tour_template_seeds(fx) -> None:
    """Den nya 'Lär känna systemet'-modulen ska seedas som systemmodul."""
    from hembudget.school.module_seed import seed_system_modules
    from hembudget.school.models import Module
    with master_session() as s:
        seed_system_modules(s)
    with master_session() as s:
        m = s.query(Module).filter(
            Module.title == "Lär känna systemet",
            Module.teacher_id.is_(None),
        ).first()
        assert m is not None
        assert m.is_template is True
        # Två task-steg ska ha link_transfer + add_upcoming
        kinds = [
            (st.params or {}).get("assignment_kind")
            for st in m.steps if st.kind == "task"
        ]
        assert "link_transfer" in kinds
        assert "add_upcoming" in kinds
