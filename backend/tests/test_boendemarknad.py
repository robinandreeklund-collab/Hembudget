"""Tester för game_engine.housing_market + /v2/boendemarknad/* endpoints."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hembudget.api.deps import register_token
from hembudget.school.engines import init_master_engine, master_session
from hembudget.school.models import Student, StudentProfile, Teacher
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
            email="t@s.se", name="T",
            password_hash=hash_password("Abcdef12!"),
        )
        s.add(t)
        s.flush()
        tid = t.id
        # Student + StudentProfile (krävs för boendemarknad-endpoints)
        stu = Student(
            teacher_id=tid, display_name="Eva",
            login_code="EVA00001",
        )
        s.add(stu)
        s.flush()
        sid = stu.id
        sp = StudentProfile(
            student_id=sid,
            profession="Ekonom",
            employer="Spelbolaget AB",
            gross_salary_monthly=42000,
            net_salary_monthly=29000,
            tax_rate_effective=0.31,
            personality="blandad",
            age=32,
            city="Stockholm",
            family_status="ensam",
            housing_type="hyresratt",
            housing_monthly=12000,
        )
        s.add(sp)
        s.commit()

    teacher_tok = random_token()
    student_tok = random_token()
    register_token(teacher_tok, role="teacher", teacher_id=tid)
    register_token(student_tok, role="student", student_id=sid)
    return TestClient(app), teacher_tok, student_tok, tid, sid


# === B1 · Marknadsdata ===


class TestMarketData:
    def test_price_grows_over_time_for_stockholm(self):
        from hembudget.game_engine.housing_market import market_price_for
        prices = [market_price_for("stockholm", ym) for ym in (
            "2026-01", "2027-01", "2028-01", "2029-01",
        )]
        # Prisutveckling över 3 år ska vara positiv (stockholm 5%/år)
        assert prices[-1] > prices[0], f"Ingen prisuppgång: {prices}"

    def test_price_deterministic(self):
        from hembudget.game_engine.housing_market import market_price_for
        a = market_price_for("malmo", "2026-06")
        b = market_price_for("malmo", "2026-06")
        assert a == b

    def test_unknown_city_returns_zero(self):
        from hembudget.game_engine.housing_market import market_price_for
        assert market_price_for("nonexistent", "2026-01") == 0


# === B2 · Listings ===


class TestListings:
    def test_listings_count_and_structure(self):
        from hembudget.game_engine.housing_market import listings_for_city
        ls = listings_for_city("stockholm", "2026-01", n=5)
        assert len(ls) == 5
        for l in ls:
            assert l.listing_id.startswith("stockholm-2026-01-")
            assert l.size_kvm > 0
            assert l.asking_price > 0
            assert l.type in ("bostadsratt", "villa", "radhus")

    def test_listings_deterministic(self):
        from hembudget.game_engine.housing_market import listings_for_city
        a = listings_for_city("goteborg", "2026-04", n=3)
        b = listings_for_city("goteborg", "2026-04", n=3)
        assert [l.listing_id for l in a] == [l.listing_id for l in b]
        assert [l.asking_price for l in a] == [l.asking_price for l in b]

    def test_smaort_villas_dominate(self):
        from hembudget.game_engine.housing_market import listings_for_city
        ls = listings_for_city("smaort", "2026-01", n=10)
        villas = sum(1 for l in ls if l.type in ("villa", "radhus"))
        assert villas >= 5, f"Småort har bara {villas}/10 villor"


# === B3 · Köp-flöde ===


class TestBuyFlow:
    def test_buy_succeeds_when_cash_sufficient(self, fx):
        from hembudget.db.models import Account, Loan, MailItem
        from hembudget.game_engine.housing_market import (
            buy_listing, listings_for_city,
        )
        from hembudget.school.engines import (
            get_scope_session, scope_context, scope_for_student,
        )

        _, _, _, _, sid = fx
        with master_session() as s:
            stu = s.get(Student, sid)
            s.expunge(stu)
        scope_key = scope_for_student(stu)

        # Hitta billigaste BR (LTV 85% = lägre kontantinsats än villa LTV 75%)
        listings = listings_for_city("medelstad", "2026-03", n=10)
        brs = [l for l in listings if l.type == "bostadsratt"]
        if not brs:
            # Fallback: använd vilken billig som helst med korrekt LTV
            cheap = min(listings, key=lambda l: l.asking_price)
            ltv = 0.75 if cheap.type == "villa" else 0.85
        else:
            cheap = min(brs, key=lambda l: l.asking_price)
            ltv = 0.85
        cash_required = cheap.asking_price - int(cheap.asking_price * ltv)

        maker = get_scope_session(scope_key)
        with scope_context(scope_key):
            with maker() as s:
                # Säkerställ stort checking-saldo
                s.add(Account(
                    name="Lönekonto", bank="Spel", type="checking",
                    opening_balance=Decimal(cash_required + 50000),
                ))
                s.commit()
                result = buy_listing(
                    s,
                    student_id=sid,
                    student_scope=scope_key,
                    listing=cheap,
                    available_cash=cash_required + 50000,
                    year_month="2026-03",
                )
                s.commit()
                loan_count = s.query(Loan).count()
                mail_count = s.query(MailItem).filter(
                    MailItem.subject.like("Bolån beviljat%"),
                ).count()

        assert result.accepted is True
        assert result.loan_id is not None
        assert result.cash_required == cash_required
        assert "safety" in result.pentagon_delta
        assert loan_count >= 1
        assert mail_count == 1

    def test_buy_fails_when_cash_insufficient(self, fx):
        from hembudget.game_engine.housing_market import (
            buy_listing, listings_for_city,
        )
        from hembudget.school.engines import (
            get_scope_session, scope_context, scope_for_student,
        )

        _, _, _, _, sid = fx
        with master_session() as s:
            stu = s.get(Student, sid)
            s.expunge(stu)
        scope_key = scope_for_student(stu)

        ls = listings_for_city("stockholm", "2026-03", n=5)
        expensive = max(ls, key=lambda l: l.asking_price)

        maker = get_scope_session(scope_key)
        with scope_context(scope_key):
            with maker() as s:
                result = buy_listing(
                    s,
                    student_id=sid,
                    student_scope=scope_key,
                    listing=expensive,
                    available_cash=10_000,  # alldeles för lite
                    year_month="2026-03",
                )

        assert result.accepted is False
        assert result.error and "Kontantinsats" in result.error
        assert result.loan_id is None


# === B5 · Valuation ===


class TestValuation:
    def test_hyresgast_returns_no_owned_home(self, fx):
        from hembudget.game_engine.housing_market import valuate_current_home
        from hembudget.game_engine.profile_generator import generate_profile
        from hembudget.school.engines import (
            get_scope_session, scope_context, scope_for_student,
        )

        _, _, _, _, sid = fx
        with master_session() as s:
            stu = s.get(Student, sid)
            s.expunge(stu)
        scope_key = scope_for_student(stu)
        # Fixturen sätter housing_type=hyresratt
        # Generera ny profil med hyresratt
        profile = generate_profile(seed=999, partner_model="solo")
        # Tvinga hyresratt
        profile.housing.type = "hyresratt"
        profile.housing.purchase_price = None
        profile.housing.loan_amount = None

        maker = get_scope_session(scope_key)
        with scope_context(scope_key):
            with maker() as s:
                v = valuate_current_home(s, profile=profile, year_month="2026-06")
        assert v.has_owned_home is False
        assert v.current_value is None

    def test_owned_home_grows_over_time(self, fx):
        from hembudget.game_engine.housing_market import valuate_current_home
        from hembudget.game_engine.profile_generator import generate_profile
        from hembudget.school.engines import (
            get_scope_session, scope_context, scope_for_student,
        )

        _, _, _, _, sid = fx
        with master_session() as s:
            stu = s.get(Student, sid)
            s.expunge(stu)
        scope_key = scope_for_student(stu)

        # Hitta en seed som ger BR-profil
        for seed in range(50):
            profile = generate_profile(seed=seed, partner_model="solo")
            if profile.housing.type == "bostadsratt" and profile.housing.purchase_price:
                break
        else:
            pytest.skip("Hittade ingen BR-profil i 50 seeds")

        maker = get_scope_session(scope_key)
        with scope_context(scope_key):
            with maker() as s:
                v_now = valuate_current_home(s, profile=profile, year_month="2026-01")
                v_future = valuate_current_home(s, profile=profile, year_month="2028-01")
        assert v_now.has_owned_home is True
        # Marknadsdrift ska öka värdet över 2 år (positivt eller minst neutralt)
        assert v_future.current_value >= v_now.current_value


# === Endpoints ===


class TestEndpoints:
    def test_listings_endpoint_for_student(self, fx):
        client, _, stok, _, _ = fx
        r = client.get(
            "/v2/boendemarknad/listings?ym=2026-01&n=4",
            headers={"Authorization": f"Bearer {stok}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["city_key"] == "stockholm"  # från StudentProfile.city
        assert len(body["listings"]) == 4
        assert body["market_price_per_kvm"] > 0

    def test_listings_requires_token(self, fx):
        client, *_ = fx
        r = client.get("/v2/boendemarknad/listings?ym=2026-01")
        assert r.status_code == 401

    def test_my_home_valuation_for_hyresgast(self, fx):
        client, _, stok, _, _ = fx
        r = client.get(
            "/v2/boendemarknad/my-home/valuation?ym=2026-01",
            headers={"Authorization": f"Bearer {stok}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["has_owned_home"] is False

    def test_teacher_listings_works_for_any_city(self, fx):
        client, ttok, _, _, _ = fx
        r = client.get(
            "/v2/teacher/boendemarknad/listings?city=goteborg&ym=2026-06&n=5",
            headers={"Authorization": f"Bearer {ttok}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["city_key"] == "goteborg"
        assert len(body["listings"]) == 5

    def test_teacher_listings_unknown_city_404(self, fx):
        client, ttok, _, _, _ = fx
        r = client.get(
            "/v2/teacher/boendemarknad/listings?city=elsa-staden",
            headers={"Authorization": f"Bearer {ttok}"},
        )
        assert r.status_code == 404

    def test_teacher_market_prices_returns_all_cities(self, fx):
        client, ttok, _, _, _ = fx
        r = client.get(
            "/v2/teacher/boendemarknad/market-prices?ym=2026-06",
            headers={"Authorization": f"Bearer {ttok}"},
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body) >= 12
        for row in body:
            assert row["price_per_kvm"] > 0

    def test_buy_endpoint_rejects_other_city(self, fx):
        client, _, stok, _, _ = fx
        # Eleven är i Stockholm men försöker köpa goteborg-listing
        r = client.post(
            "/v2/boendemarknad/buy/goteborg-2026-01-00",
            json={"year_month": "2026-01", "listing_id": "goteborg-2026-01-00"},
            headers={"Authorization": f"Bearer {stok}"},
        )
        assert r.status_code == 400

    def test_sell_fails_for_hyresgast(self, fx):
        client, _, stok, _, _ = fx
        r = client.post(
            "/v2/boendemarknad/sell",
            json={"year_month": "2026-01"},
            headers={"Authorization": f"Bearer {stok}"},
        )
        assert r.status_code == 400
