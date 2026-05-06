"""End-to-end test för företagsläget · biz-spelmotorn via API.

Verifierar att hela biz-flödet fungerar via riktiga HTTP-anrop:
  1. Lärare skapar elev + togglar på business_mode
  2. Eleven skapar företag
  3. Manuell tick genererar offertförfrågningar
  4. Eleven lämnar offert
  5. Tick avgör om kunden tackar ja
  6. Vid accepterad: jobb skapas
  7. Eleven levererar med kvalitet
  8. Faktura skapas automatiskt
  9. Lärar-klassöversikt visar bolag

Detta testar HELA biz-motorn end-to-end, inte bara enheter.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import Student, Teacher
from hembudget.security.crypto import hash_password, random_token


@pytest.fixture
def app_with_student(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
        teacher = Teacher(
            name="Anna L",
            email="anna@example.com",
            password_hash=hash_password("h"),
            ai_enabled=False,
            active=True,
        )
        s.add(teacher); s.flush()
        teacher_id = teacher.id
        s.commit()

    teacher_token = random_token()
    register_token(teacher_token, role="teacher", teacher_id=teacher_id)

    client = TestClient(app)

    # Skapa elev
    r = client.post(
        "/v2/teacher/students/create",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={
            "first_name": "Sara",
            "last_initial": "A",
            "starting_level": 1,
            "spend_profile": "balanserad",
        },
    )
    assert r.status_code == 200
    student_id = r.json()["student_id"]

    # Aktivera biz-mode
    r = client.post(
        f"/v2/teacher/foretag/toggle/{student_id}",
        headers={"Authorization": f"Bearer {teacher_token}"},
        json={"enabled": True},
    )
    assert r.status_code == 200, r.text

    # Skapa elev-token
    student_token = random_token()
    register_token(student_token, role="student", student_id=student_id)

    return client, teacher_token, student_token, teacher_id, student_id


def test_biz_mode_full_flow(app_with_student):
    """End-to-end: skapa bolag → tick → offert → tick → leverera → faktura."""
    client, teacher_token, student_token, _tid, sid = app_with_student
    H = {"Authorization": f"Bearer {student_token}"}

    # === 1. Verifiera att biz-mode är aktiv ===
    r = client.get("/v2/foretag/mode-status", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is True, "Biz-mode borde vara på"
    assert r.json()["has_active_company"] is False

    # === 2. Skapa företag ===
    r = client.post(
        "/v2/foretag",
        headers=H,
        json={
            "name": "Sara A. AB",
            "form": "ab",
            "industry_key": "snickare",
            "share_capital": 25000,
        },
    )
    assert r.status_code == 200, f"Kunde inte skapa bolag: {r.text}"
    company = r.json()
    assert company["name"] == "Sara A. AB"
    assert company["form"] == "ab"

    # === 3. Manuell tick · ev. fler offerter (create_company pre-seedar
    #        2 veckor så bolaget aldrig är tomt direkt efter skapande)
    r = client.post("/v2/foretag/tick", headers=H)
    assert r.status_code == 200, f"Tick failed: {r.text}"

    # === 4. Lista offerter — kombinerar pre-seed + manuell tick ===
    r = client.get("/v2/foretag/opportunities?status_filter=open", headers=H)
    assert r.status_code == 200, r.text
    opps = r.json()
    assert len(opps) >= 1, (
        "Inga öppna offerter listades — pipeline-engine fungerar inte."
    )
    first_opp = opps[0]

    # === 5. Lämna offert (lågt pris för hög acceptans-sannolikhet) ===
    r = client.post(
        f"/v2/foretag/opportunities/{first_opp['id']}/quote",
        headers=H,
        json={
            "offered_price": int(first_opp["market_price"] * 0.7),
            "offered_delivery_days": first_opp["expected_delivery_days"],
            "pitch_text": "Vi har lång erfarenhet och levererar med god kvalitet.",
        },
    )
    assert r.status_code == 200, f"Kunde inte lämna offert: {r.text}"
    quote = r.json()
    assert quote["offered_price"] > 0

    # === 6. Tick igen → kunden ska besluta ===
    r = client.post("/v2/foretag/tick", headers=H)
    assert r.status_code == 200, r.text
    tick2 = r.json()
    assert tick2["quotes_decided"] >= 1, (
        f"Kunden besvarade inte offerten — acceptance_model fungerar inte. "
        f"Notes: {tick2.get('notes')}"
    )

    # === 7. Hämta offert-status — borde vara 'won' eller 'lost' ===
    r = client.get(
        f"/v2/foretag/opportunities/{first_opp['id']}/quote", headers=H,
    )
    assert r.status_code == 200, r.text
    decided_quote = r.json()
    assert decided_quote is not None
    assert decided_quote["accepted"] is not None, (
        "Quote.accepted ska vara True/False efter tick — fortfarande None"
    )
    # Med pris=70% av riktpris + bra pitch ska den oftast vinnas
    # Men determinismen kan ge "lost" — vi accepterar båda
    assert decided_quote["accept_probability"] is not None

    # === 8. Om vunnen → leverera ===
    if decided_quote["accepted"]:
        r = client.get("/v2/foretag/jobs?status_filter=in_progress", headers=H)
        assert r.status_code == 200, r.text
        jobs = r.json()
        assert len(jobs) >= 1, "Vunnen offert skapade inget Job"
        job = jobs[0]

        # Leverera med hög kvalitet
        r = client.post(
            f"/v2/foretag/jobs/{job['id']}/deliver",
            headers=H,
            json={"quality_score": 85, "create_invoice": True},
        )
        assert r.status_code == 200, f"Kunde inte leverera: {r.text}"
        deliver = r.json()
        assert deliver["job"]["status"] == "invoiced"
        assert deliver["invoice_id"] is not None, (
            "Leverans skapade ingen kundfaktura"
        )
        assert deliver["invoice_number"] is not None

    # === 9. Pentagon ska finnas ===
    r = client.get("/v2/foretag/pentagon", headers=H)
    assert r.status_code == 200, r.text
    pent = r.json()
    assert pent["total_score"] >= 0
    for axis in ("omsattning", "kundbas", "likviditet", "tidsatgang", "vinst"):
        assert axis in pent["axes"]


def test_biz_class_overview_shows_company(app_with_student):
    """Lärar-klassöversikt ska visa bolaget när det skapats."""
    client, teacher_token, student_token, _tid, sid = app_with_student
    H_S = {"Authorization": f"Bearer {student_token}"}
    H_T = {"Authorization": f"Bearer {teacher_token}"}

    # Skapa bolag
    client.post(
        "/v2/foretag", headers=H_S,
        json={"name": "Test AB", "form": "ab", "industry_key": "it_konsult"},
    )

    # Lärare hämtar klass-aggregat
    r = client.get("/v2/teacher/foretag/class-overview", headers=H_T)
    assert r.status_code == 200, r.text
    data = r.json()
    rows = data["rows"]
    student_row = next((r for r in rows if r["student_id"] == sid), None)
    assert student_row is not None, "Eleven syns inte i klass-overview"
    assert student_row["has_company"] is True
    assert student_row["company_name"] == "Test AB"
    assert student_row["biz_mode_enabled"] is True


def test_biz_supplier_invoice_mass_send(app_with_student):
    """Lärare ska kunna mass-skicka leverantörsfaktura till elev."""
    client, teacher_token, student_token, _tid, sid = app_with_student
    H_S = {"Authorization": f"Bearer {student_token}"}
    H_T = {"Authorization": f"Bearer {teacher_token}"}

    # Skapa bolag
    client.post(
        "/v2/foretag", headers=H_S,
        json={"name": "Bygg AB", "form": "enskild_firma",
              "industry_key": "snickare"},
    )

    # Lärare skickar leverantörsfaktura
    r = client.post(
        "/v2/teacher/foretag/supplier-invoices", headers=H_T,
        json={
            "target_student_ids": [sid],
            "sender_name": "Bygghandeln Nord",
            "description": "Material för Q3",
            "amount_excl_vat": 4500,
            "vat_rate": 0.25,
            "due_in_days": 30,
        },
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["n_created"] == 1
    assert result["n_skipped_no_company"] == 0

    # Eleven ser fakturan
    r = client.get("/v2/foretag/supplier-invoices", headers=H_S)
    assert r.status_code == 200, r.text
    invoices = r.json()
    assert len(invoices) == 1
    assert invoices[0]["sender_name"] == "Bygghandeln Nord"
    assert invoices[0]["source"] == "teacher"
    assert invoices[0]["status"] == "open"


def test_biz_bank_overview_shape(app_with_student):
    """/v2/foretag/bank-overview returnerar 3 konton + tx-list +
    moms-meta. Strukturen ska matcha BizBankOverviewOut-schemat."""
    client, _teacher_token, student_token, _tid, _sid = app_with_student
    H = {"Authorization": f"Bearer {student_token}"}

    # Utan bolag → 400
    r = client.get("/v2/foretag/bank-overview", headers=H)
    assert r.status_code == 400, r.text

    # Skapa bolag
    client.post(
        "/v2/foretag", headers=H,
        json={
            "name": "Test AB", "form": "ab",
            "industry_key": "it_konsult", "share_capital": 25000,
        },
    )

    r = client.get("/v2/foretag/bank-overview", headers=H)
    assert r.status_code == 200, r.text
    data = r.json()
    # 3 konton: företagskonto + skattekonto + buffert
    assert len(data["accounts"]) == 3, f"Förväntade 3 konton, fick {len(data['accounts'])}"
    primary = next((a for a in data["accounts"] if a["is_primary"]), None)
    assert primary is not None
    assert primary["eye"] == "Företagskonto"
    # Tx-list finns (kan vara tom direkt efter create)
    assert isinstance(data["transactions"], list)
    # Meta-fält finns
    assert "next_vat_due" in data
    assert "own_salary_this_month" in data


def test_biz_industries_endpoint_returns_10_industries(app_with_student):
    """GET /v2/foretag/industries returnerar 10 fasta branscher med
    metadata och 'available_in_my_city'-flagga per bransch."""
    client, _teacher_token, student_token, _tid, _sid = app_with_student
    H = {"Authorization": f"Bearer {student_token}"}
    r = client.get("/v2/foretag/industries", headers=H)
    assert r.status_code == 200, r.text
    industries = r.json()
    assert len(industries) == 10
    keys = {i["key"] for i in industries}
    assert "it_konsult" in keys
    assert "rormokare" in keys
    assert "frisor" in keys
    # Varje bransch har metadata
    for ind in industries:
        assert ind["sni_code"]
        assert ind["hourly_rate_min"] > 0
        assert ind["hourly_rate_max"] > ind["hourly_rate_min"]
        assert "available_in_my_city" in ind


def test_biz_create_company_validates_industry_key(app_with_student):
    """create_company måste få giltig industry_key. Fri text → 400."""
    client, _teacher_token, student_token, _tid, _sid = app_with_student
    H = {"Authorization": f"Bearer {student_token}"}
    # Okänd bransch
    r = client.post(
        "/v2/foretag", headers=H,
        json={
            "name": "Test AB", "form": "ab",
            "industry_key": "fri_text_blah",
        },
    )
    assert r.status_code == 400, r.text
    assert "Okänd bransch" in r.json()["detail"]


def test_biz_create_company_inherits_city_from_character(app_with_student):
    """Stad ärvs från karaktärens StudentProfile.city — kan ej ändras."""
    client, _teacher_token, student_token, _tid, sid = app_with_student
    H = {"Authorization": f"Bearer {student_token}"}

    # Sätt karaktärens stad explicit till Stockholm
    from hembudget.school.models import StudentProfile
    with master_session() as ms:
        prof = ms.query(StudentProfile).filter_by(student_id=sid).first()
        if prof is not None:
            prof.city = "Stockholm"
            ms.commit()

    r = client.post(
        "/v2/foretag", headers=H,
        json={
            "name": "Test", "form": "enskild_firma",
            "industry_key": "it_konsult",
        },
    )
    assert r.status_code == 200, r.text
    company = r.json()
    # city_key borde vara satt, även om vi inte skickade det
    assert company["city_key"] is not None


def test_biz_employment_decision_status_no_pending_at_start(app_with_student):
    """Säg-upp-prompten ska INTE trigga direkt efter företagsstart
    (0 timmar biz · 0 v överbelastning)."""
    client, _teacher_token, student_token, _tid, _sid = app_with_student
    H = {"Authorization": f"Bearer {student_token}"}
    client.post(
        "/v2/foretag", headers=H,
        json={
            "name": "Test", "form": "ab",
            "industry_key": "it_konsult", "share_capital": 25000,
        },
    )
    r = client.get("/v2/foretag/employment-decision/status", headers=H)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["pending"] is False
    assert data["employment_status"] == "employed"
    assert data["weekly_hours_employed"] == 40


def test_biz_employment_decision_apply_parttime(app_with_student):
    """POST /employment-decision · go_parttime halverar lön och sätter 20h."""
    client, _teacher_token, student_token, _tid, sid = app_with_student
    H = {"Authorization": f"Bearer {student_token}"}
    client.post(
        "/v2/foretag", headers=H,
        json={
            "name": "Test", "form": "enskild_firma",
            "industry_key": "it_konsult",
        },
    )
    # Spara löne-baseline för jämförelse
    from hembudget.school.models import StudentProfile
    with master_session() as ms:
        prof = ms.query(StudentProfile).filter_by(student_id=sid).first()
        baseline_gross = int(prof.gross_salary_monthly)

    r = client.post(
        "/v2/foretag/employment-decision",
        headers=H,
        json={"choice": "go_parttime"},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["choice"] == "go_parttime"
    assert result["weekly_hours_employed"] == 20
    assert result["salary_change_pct"] == -50

    # Verifiera att gross-salary halverades
    with master_session() as ms:
        prof = ms.query(StudentProfile).filter_by(student_id=sid).first()
        assert int(prof.gross_salary_monthly) == baseline_gross // 2


def test_biz_private_summary_returns_no_company_at_first(app_with_student):
    """privateSummary returnerar has_company=false innan eleven skapat
    bolag — så BizSummaryCard renderar ingenting."""
    client, _teacher_token, student_token, _tid, _sid = app_with_student
    H = {"Authorization": f"Bearer {student_token}"}
    r = client.get("/v2/foretag/private-summary", headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["has_company"] is False


def test_biz_pentagon_axis_detail_returns_factors_and_events(app_with_student):
    """Flip-kortets baksida · /v2/foretag/pentagon/axis/{axis} ska
    returnera score + faktorer + events + summary för varje av de 5
    axlarna. Speglar privat-pentagonens flip-kort.
    """
    client, _teacher_token, student_token, _tid, _sid = app_with_student
    H = {"Authorization": f"Bearer {student_token}"}

    # Utan bolag → 400
    r = client.get("/v2/foretag/pentagon/axis/omsattning", headers=H)
    assert r.status_code == 400, r.text

    # Skapa bolag
    client.post(
        "/v2/foretag", headers=H,
        json={"name": "Pentagon AB", "form": "ab", "industry_key": "it_konsult"},
    )

    # Alla 5 axlar ska ge en giltig BizAxisDetail
    for axis in ["omsattning", "kundbas", "likviditet", "tidsatgang", "vinst"]:
        r = client.get(f"/v2/foretag/pentagon/axis/{axis}", headers=H)
        assert r.status_code == 200, f"{axis}: {r.text}"
        data = r.json()
        assert data["axis"] == axis
        assert data["axis_label"]  # icke-tom
        assert data["axis_number"] in {"01", "02", "03", "04", "05"}
        assert isinstance(data["score"], int)
        assert 0 <= data["score"] <= 100
        assert isinstance(data["factors"], list)
        assert isinstance(data["events"], list)
        assert data["summary_text"]


def test_biz_pentagon_includes_axes_prev(app_with_student):
    """compute_business_pentagon ska returnera axes_prev när det finns
    historisk data (4-12 v sedan). Direkt efter create finns ingen,
    så axes_prev=None är OK."""
    client, _teacher_token, student_token, _tid, _sid = app_with_student
    H = {"Authorization": f"Bearer {student_token}"}
    client.post(
        "/v2/foretag", headers=H,
        json={"name": "TT", "form": "ab", "industry_key": "it_konsult"},
    )
    r = client.get("/v2/foretag/pentagon", headers=H)
    assert r.status_code == 200, r.text
    pent = r.json()
    # axes_prev kan vara None när det inte finns historisk data
    assert "axes_prev" in pent
    # När det är None → frontend ritar ingen prev-polygon


def test_biz_owner_salary_credits_private_account(app_with_student):
    """När eleven tar ut lön från AB ska pengarna landa på privat-konto."""
    client, teacher_token, student_token, _tid, sid = app_with_student
    H_S = {"Authorization": f"Bearer {student_token}"}

    # Skapa AB
    client.post(
        "/v2/foretag", headers=H_S,
        json={"name": "AB", "form": "ab", "industry_key": "it_konsult"},
    )

    # Hämta privat-konto saldo INNAN
    from hembudget.school.engines import (
        get_scope_session, scope_context, scope_for_student,
    )
    from hembudget.db.models import Account, Transaction
    from hembudget.school.models import Student as _Stu
    with master_session() as s:
        st = s.get(_Stu, sid)
        scope_key = scope_for_student(st)
    maker = get_scope_session(scope_key)
    with scope_context(scope_key):
        with maker() as s:
            checking_before = s.query(Account).filter(
                Account.type == "checking",
            ).first()
            balance_before_count = (
                s.query(Transaction)
                .filter(Transaction.account_id == checking_before.id)
                .count()
            ) if checking_before else 0

    # Ta ut lön (15 000 brutto)
    r = client.post(
        "/v2/foretag/owner-salary", headers=H_S,
        json={"paid_on": str(date.today()), "gross_salary": 15000},
    )
    assert r.status_code == 200, f"Kunde inte ta ut lön: {r.text}"
    salary = r.json()
    assert salary["net_to_owner"] > 0

    # Verifiera att privat-konto fick en ny transaktion
    with scope_context(scope_key):
        with maker() as s:
            checking_after = s.query(Account).filter(
                Account.type == "checking",
            ).first()
            balance_after_count = (
                s.query(Transaction)
                .filter(Transaction.account_id == checking_after.id)
                .count()
            ) if checking_after else 0
            assert balance_after_count > balance_before_count, (
                "Privat-kontot fick ingen ny transaktion när AB-lön betalades"
            )
