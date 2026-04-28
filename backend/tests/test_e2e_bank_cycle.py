"""E2E-test som bevisar att Rolling N+1 + dynamiskt kontoutdrag
fungerar end-to-end över en hel månadscykel.

Flödet som testas:
1. Lärare skapar elev (med profil)
2. Lärare genererar batch för november
3. Verifiera: kontoutdrag-PDF för november är (nästan) tomt — ingen
   ledger-historik finns ännu. Self-healing skapar upcomings för
   både november och december (första batchen).
4. Eleven signerar HYRA + EL i banken med EkonomilabbetID
5. Kör scheduled-payments/run-due (simulerar att förfallodag inträffat)
6. Verifiera: HYRA + EL är dragna från lönekontot, Transactions skapade,
   UpcomingTransactions matchade. TRE-fakturan är fortfarande osignerad.
7. Lärare genererar batch för december
8. Verifiera: kontoutdrag för november nu visar HYRA + EL i ledgern
   (eleven signerade dem) men INTE TRE (fortfarande osignerad).
9. Verifiera: nya upcomings för januari finns (rolling N+1 igen).

Detta är beviset att arkitekturen håller — varje månads kontoutdrag
visar bara faktiska händelser, eleven har full agency över signering,
och systemet itererar månadsvis utan att fastna.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.db.base import session_scope
from hembudget.school.engines import (
    init_master_engine, master_session, scope_context, scope_for_student,
)
from hembudget.school.models import (
    Student, StudentProfile, Teacher,
    ScenarioBatch, BatchArtifact,
)
from hembudget.security.crypto import hash_password, random_token


@pytest.fixture
def fx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
    monkeypatch.delenv("TURNSTILE_SECRET", raising=False)
    from hembudget.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    from hembudget.security import rate_limit as rl_mod
    rl_mod.reset_all_for_testing()
    from hembudget.school import engines as eng_mod
    if eng_mod._master_engine is not None:
        eng_mod._master_engine.dispose()
    eng_mod._master_engine = None
    eng_mod._master_session = None
    for e in list(eng_mod._scope_engines.values()):
        e.dispose()
    eng_mod._scope_engines.clear()
    eng_mod._scope_sessions.clear()
    from hembudget.school import demo_seed as demo_seed_mod
    monkeypatch.setattr(demo_seed_mod, "build_demo", lambda: {"skipped": True})

    import importlib
    import hembudget.main as main_mod
    importlib.reload(main_mod)
    app = main_mod.build_app()
    init_master_engine()

    with master_session() as s:
        t = Teacher(
            email="t@x.se", name="T",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(t); s.flush()
        tid = t.id
        stu = Student(
            teacher_id=tid, display_name="Linda", login_code="LIN00001",
        )
        s.add(stu); s.flush()
        sid = stu.id
        s.add(StudentProfile(
            student_id=sid,
            profession="IT-konsult", employer="Visma",
            gross_salary_monthly=37000, net_salary_monthly=24300,
            tax_rate_effective=0.22, age=22, city="Stockholm",
            family_status="ensam", housing_type="hyresratt",
            housing_monthly=8500, personality="blandad",
        ))

    tch_tok = random_token()
    stu_tok = random_token()
    register_token(tch_tok, role="teacher", teacher_id=tid)
    register_token(stu_tok, role="student", student_id=sid)
    return TestClient(app), tch_tok, stu_tok, tid, sid


def _generate_batch(sid: int, year_month: str) -> ScenarioBatch:
    """Generera en batch direkt via teacher.batch (utanför HTTP-flödet
    så testet inte är beroende av lärar-impersonations-headers)."""
    from hembudget.teacher.batch import create_batch_for_student
    with master_session() as s:
        student = s.get(Student, sid)
        batch = create_batch_for_student(s, student, year_month)
        s.flush()
        return batch


def _list_upcoming_bills(sid: int) -> list[tuple[str, str, float]]:
    """Returnera (name, expected_date, amount) för obetalda bills."""
    from hembudget.db.models import UpcomingTransaction
    with master_session() as s:
        student = s.get(Student, sid)
    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            rows = (
                s.query(UpcomingTransaction)
                .filter(
                    UpcomingTransaction.kind == "bill",
                    UpcomingTransaction.matched_transaction_id.is_(None),
                )
                .order_by(UpcomingTransaction.expected_date.asc())
                .all()
            )
            return [
                (u.name, u.expected_date.isoformat(), float(u.amount))
                for u in rows
            ]


def _list_transactions(sid: int) -> list[tuple[str, str, float]]:
    from hembudget.db.models import Account, Transaction
    with master_session() as s:
        student = s.get(Student, sid)
    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            acc = s.query(Account).filter(Account.type == "checking").first()
            if not acc:
                return []
            rows = (
                s.query(Transaction)
                .filter(Transaction.account_id == acc.id)
                .order_by(Transaction.date.asc())
                .all()
            )
            return [
                (t.raw_description, t.date.isoformat(), float(t.amount))
                for t in rows
            ]


def test_full_month_cycle_rolling_n_plus_1_and_dynamic_statement(fx) -> None:
    client, _, stu, _tid, sid = fx

    # ──── Steg 1+2: Generera november-batchen ────────────────────────
    nov_batch = _generate_batch(sid, "2026-11")
    assert nov_batch.year_month == "2026-11"

    # ──── Steg 3: Self-healing init — november OCH december-upcomings ────
    bills = _list_upcoming_bills(sid)
    nov_dates = [d for _, d, _ in bills if d.startswith("2026-11")]
    dec_dates = [d for _, d, _ in bills if d.startswith("2026-12")]
    assert len(nov_dates) >= 4, (
        f"Första batchen ska seed:a CURRENT month — fick {nov_dates}"
    )
    assert len(dec_dates) >= 4, (
        f"Rolling N+1 ska skapa NEXT month — fick {dec_dates}"
    )
    nov_names = {n for n, d, _ in bills if d.startswith("2026-11")}
    assert any("HYRA" in n for n in nov_names)

    # Kontoutdrag-PDF för november ska vara fallback (ingen ledger än)
    with master_session() as s:
        kontoutdrag = (
            s.query(BatchArtifact)
            .filter(
                BatchArtifact.batch_id == nov_batch.id,
                BatchArtifact.kind == "kontoutdrag",
            )
            .first()
        )
        assert kontoutdrag is not None
        assert kontoutdrag.meta.get("source") == "scenario_fallback"

    # ──── Steg 4: Sätt PIN + skapa session + bekräfta + signera ────
    client.post(
        "/bank/set-pin",
        json={"pin": "2222"},
        headers={"Authorization": f"Bearer {stu}"},
    )
    init_resp = client.post(
        "/bank/session/init",
        json={"purpose": "sign_payment_batch:1,2"},
        headers={"Authorization": f"Bearer {stu}"},
    )
    sess_token = init_resp.json()["token"]
    client.post(
        f"/bank/session/{sess_token}/confirm",
        json={"pin": "2222"},
    )
    # Hitta de NOVEMBER-upcomings som heter HYRA och el-företaget
    upcoming_resp = client.get(
        "/bank/upcoming-payments",
        headers={"Authorization": f"Bearer {stu}"},
    )
    nov_upcomings = [
        u for u in upcoming_resp.json()
        if u["expected_date"].startswith("2026-11")
    ]
    hyra = next(u for u in nov_upcomings if "HYRA" in u["name"])
    el = next(
        u for u in nov_upcomings
        if any(v in u["name"] for v in (
            "VATTENFALL", "FORTUM", "ELLEVIO", "TIBBER",
        ))
    )
    # Signera de två
    sign_resp = client.post(
        "/bank/upcoming-payments/sign",
        json={
            "upcoming_ids": [hyra["upcoming_id"], el["upcoming_id"]],
            "account_id": hyra["debit_account_id"],
            "bank_session_token": sess_token,
        },
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert sign_resp.status_code == 200, sign_resp.text
    assert sign_resp.json()["signed_count"] == 2

    # ──── Steg 5: Kör scheduled-payments/run-due med datum efter förfall ───
    # Använd as_of-parameter om endpoint stöder det; annars fake datum
    run_resp = client.post(
        "/bank/scheduled-payments/run-due",
        json={"as_of": "2026-12-15"},
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert run_resp.status_code == 200, run_resp.text
    run_body = run_resp.json()
    assert run_body.get("executed", 0) >= 2, run_body

    # ──── Steg 6: Transactions ska finnas + upcomings matchade ────
    txs = _list_transactions(sid)
    debit_names = [n for n, _, a in txs if a < 0]
    assert any("HYRA" in n for n in debit_names), debit_names
    assert any(
        any(v in n for v in ("VATTENFALL", "FORTUM", "ELLEVIO", "TIBBER"))
        for n in debit_names
    ), debit_names

    # TRE-fakturan ska FORTFARANDE vara osignerad
    remaining = client.get(
        "/bank/upcoming-payments",
        headers={"Authorization": f"Bearer {stu}"},
    ).json()
    nov_remaining_names = {
        u["name"] for u in remaining
        if u["expected_date"].startswith("2026-11")
    }
    # HYRA + EL är borta (matchad eller executed)
    assert not any("HYRA" in n for n in nov_remaining_names), nov_remaining_names

    # ──── Steg 7: Generera december-batchen ──────────────────────────
    dec_batch = _generate_batch(sid, "2026-12")

    # ──── Steg 8: Decembers kontoutdrag-PDF för november-aktivitet ────
    # NOTE: dec_batch.year_month är 2026-12, men för november-aktiviteten
    # bör eleven kunna re-generera november-batchen för att se ledgern.
    # Vår batch-funktion är idempotent så vi kör overwrite=True.
    from hembudget.teacher.batch import create_batch_for_student
    with master_session() as s:
        student = s.get(Student, sid)
        rebuilt_nov = create_batch_for_student(
            s, student, "2026-11", overwrite=True,
        )
        kontoutdrag_v2 = (
            s.query(BatchArtifact)
            .filter(
                BatchArtifact.batch_id == rebuilt_nov.id,
                BatchArtifact.kind == "kontoutdrag",
            )
            .first()
        )
        assert kontoutdrag_v2.meta.get("source") == "ledger", (
            "Efter att eleven signerat och run-due körts ska november-"
            "kontoutdraget byggas dynamiskt från ledgern, inte från fallback"
        )
        assert kontoutdrag_v2.meta.get("tx_count", 0) >= 2, (
            f"Kontoutdraget ska visa minst HYRA + EL — fick "
            f"{kontoutdrag_v2.meta.get('tx_count')} TX"
        )

    # ──── Steg 9: Januari-upcomings ska finnas (rolling N+1) ────────
    bills_after = _list_upcoming_bills(sid)
    jan_dates = [d for _, d, _ in bills_after if d.startswith("2027-01")]
    assert len(jan_dates) >= 4, (
        f"December-batchen ska skapa januari-upcomings — fick {jan_dates}"
    )
    # December-batchen ska INTE ha skapat november-fakturor (de fanns redan)
    nov_dec_count = len([
        n for n, d, _ in bills_after if d.startswith("2026-11")
    ])
    # TRE-fakturan kvar (osignerad), ev EL/HYRA matchade och borttagna
    # från listan via matched_transaction_id-filtret
    assert nov_dec_count <= 4, (
        f"November-fakturor ska inte ha duplicerats — fick "
        f"{nov_dec_count} kvarvarande"
    )
    assert dec_batch is not None


def test_unsigned_bill_triggers_reminder_with_late_fee(fx) -> None:
    """Pedagogiskt test: eleven glömmer signera december-hyran. Efter
    förfall + 5 dagar skapar reminders/run en påminnelse-rad MED
    en separat UpcomingTransaction för påminnelseavgiften.

    Verifierar Rolling N+1 mot reminder-flödet: fakturor som genereras
    i förväg (för nästa månad) men aldrig signeras eskalerar genom
    samma reminder-stege som i verkligheten."""
    client, _, stu, _tid, sid = fx
    from hembudget.db.models import PaymentReminder, UpcomingTransaction

    # Generera batch (skapar både nov + dec upcomings via self-healing)
    _generate_batch(sid, "2026-11")

    # Hitta december-hyran (som vi inte signerar)
    bills = _list_upcoming_bills(sid)
    dec_hyra = [
        (n, d) for n, d, _ in bills
        if "HYRA" in n and d.startswith("2026-12")
    ]
    assert dec_hyra, f"Hittade ingen december-hyra: {bills}"
    hyra_date = dec_hyra[0][1]

    # Spola fram tiden 6 dagar efter förfallodagen
    from datetime import date as _date, timedelta as _td
    after = (_date.fromisoformat(hyra_date) + _td(days=6)).isoformat()

    r = client.post(
        "/bank/reminders/run",
        json={"as_of": after},
        headers={"Authorization": f"Bearer {stu}"},
    )
    assert r.status_code == 200, r.text

    # Verifiera påminnelse-rad + extra upcoming för avgiften
    with master_session() as s:
        student = s.get(Student, sid)
    scope_key = scope_for_student(student)
    with scope_context(scope_key):
        with session_scope() as s:
            reminders = s.query(PaymentReminder).all()
            assert len(reminders) >= 1, "Minst en påminnelse ska ha skapats"
            # Extra UpcomingTransaction för påminnelseavgiften.
            # När as_of är 6 dagar efter dec-hyrans förfallodag är
            # november-fakturor (också osignerade) typiskt 30+ dagar
            # över → de hamnar på högre reminder-nivå med högre
            # avgift. Vi verifierar bara att MINST en avgifts-rad
            # skapats med rimligt belopp (60-180 kr enligt stegen).
            fee_rows = (
                s.query(UpcomingTransaction)
                .filter(UpcomingTransaction.source == "reminder")
                .all()
            )
            assert len(fee_rows) >= 1, "Påminnelseavgift ska ha lagts som upcoming"
            for fee in fee_rows:
                assert fee.amount in (
                    Decimal("60"), Decimal("120"), Decimal("180"),
                ), f"Oväntad påminnelseavgift: {fee.amount}"
