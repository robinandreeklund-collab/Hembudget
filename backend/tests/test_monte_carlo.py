"""Tester för game_engine.monte_carlo."""
from __future__ import annotations

from pathlib import Path

import pytest


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
    from hembudget.school.engines import init_master_engine
    init_master_engine()


class TestRunner:
    def test_basic_run(self, fx):
        from hembudget.game_engine.monte_carlo import (
            SimConfig, run_simulations, summarize,
        )
        cfg = SimConfig(n_simulations=50, starting_level=1, spend_profile="sparsam")
        res = run_simulations(cfg)
        s = summarize(res)
        assert s["n_completed"] >= 45  # Tillåt få fail
        assert "end_balance" in s
        assert "classification" in s

    def test_classification_sums_to_total(self, fx):
        from hembudget.game_engine.monte_carlo import (
            SimConfig, run_simulations, summarize,
        )
        cfg = SimConfig(n_simulations=100, starting_level=1)
        res = run_simulations(cfg)
        s = summarize(res)
        cls = s["classification"]
        total = cls["positive"] + cls["marginal"] + cls["negative"]
        assert total == s["n_completed"]

    def test_higher_level_has_more_savings(self, fx):
        """Nivå 3 har högre lön → mer kvar i slutet av året."""
        from hembudget.game_engine.monte_carlo import (
            SimConfig, run_simulations, summarize,
        )
        cfg1 = SimConfig(
            n_simulations=200, starting_level=1, spend_profile="sparsam",
        )
        cfg3 = SimConfig(
            n_simulations=200, starting_level=3, spend_profile="sparsam",
        )
        s1 = summarize(run_simulations(cfg1))
        s3 = summarize(run_simulations(cfg3))
        assert s3["end_balance"]["median"] > s1["end_balance"]["median"]

    def test_slosa_worse_than_sparsam(self, fx):
        """Slösa-profil ska ha lägre median än sparsam vid samma nivå."""
        from hembudget.game_engine.monte_carlo import (
            SimConfig, run_simulations, summarize,
        )
        cfg_sparsam = SimConfig(
            n_simulations=200, starting_level=2, spend_profile="sparsam",
        )
        cfg_slosa = SimConfig(
            n_simulations=200, starting_level=2, spend_profile="slosa",
        )
        s_sp = summarize(run_simulations(cfg_sparsam))
        s_sl = summarize(run_simulations(cfg_slosa))
        assert s_sp["end_balance"]["median"] > s_sl["end_balance"]["median"]

    def test_deterministic_for_same_seed_base(self, fx):
        """Samma seed_base = samma resultat."""
        from hembudget.game_engine.monte_carlo import (
            SimConfig, run_simulations, summarize,
        )
        cfg = SimConfig(n_simulations=50, seed_base=12345)
        a = summarize(run_simulations(cfg))
        b = summarize(run_simulations(cfg))
        assert a["end_balance"]["median"] == b["end_balance"]["median"]

    def test_endpoint_runs(self, fx):
        """Endpoint /v2/teacher/monte-carlo returnerar summary."""
        import importlib
        import hembudget.main as main_mod
        importlib.reload(main_mod)
        app = main_mod.build_app()
        from fastapi.testclient import TestClient
        from hembudget.api.deps import register_token
        from hembudget.school.engines import master_session
        from hembudget.school.models import Teacher
        from hembudget.security.crypto import hash_password, random_token
        with master_session() as s:
            t = Teacher(
                email="t@x.se", name="T",
                password_hash=hash_password("Abcdef12!"),
            )
            s.add(t); s.flush()
            tid = t.id
        tok = random_token()
        register_token(tok, role="teacher", teacher_id=tid)
        client = TestClient(app)

        r = client.post(
            "/v2/teacher/monte-carlo",
            json={"n_simulations": 50, "starting_level": 1},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "end_balance" in body
        assert "classification" in body
