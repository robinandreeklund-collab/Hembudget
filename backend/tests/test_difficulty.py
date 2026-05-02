"""Tester för game_engine.difficulty + integration med MC + Monthly Engine."""
from __future__ import annotations

from pathlib import Path

import pytest


class TestDifficultyProfiles:
    def test_all_three_levels_defined(self):
        from hembudget.game_engine.difficulty import DIFFICULTY_PROFILES
        assert set(DIFFICULTY_PROFILES.keys()) == {1, 2, 3}

    def test_higher_level_has_more_events(self):
        from hembudget.game_engine.difficulty import DIFFICULTY_PROFILES
        p1 = DIFFICULTY_PROFILES[1]
        p2 = DIFFICULTY_PROFILES[2]
        p3 = DIFFICULTY_PROFILES[3]
        assert p1.event_frequency_mult < p2.event_frequency_mult < p3.event_frequency_mult
        assert p1.event_cost_mult < p2.event_cost_mult < p3.event_cost_mult

    def test_higher_level_has_more_sick(self):
        from hembudget.game_engine.difficulty import DIFFICULTY_PROFILES
        p1 = DIFFICULTY_PROFILES[1]
        p3 = DIFFICULTY_PROFILES[3]
        assert p1.sick_probability_mult < p3.sick_probability_mult
        assert p1.long_sick_probability_mult < p3.long_sick_probability_mult

    def test_higher_level_amplifies_spend_spread(self):
        from hembudget.game_engine.difficulty import DIFFICULTY_PROFILES
        p1 = DIFFICULTY_PROFILES[1]
        p3 = DIFFICULTY_PROFILES[3]
        assert p1.spend_profile_amplifier < p3.spend_profile_amplifier

    def test_get_difficulty_clamps(self):
        from hembudget.game_engine.difficulty import (
            DIFFICULTY_PROFILES, get_difficulty,
        )
        # Out-of-range clampas till nivå 1 eller 3
        assert get_difficulty(0) is DIFFICULTY_PROFILES[1]
        assert get_difficulty(99) is DIFFICULTY_PROFILES[3]
        assert get_difficulty(-5) is DIFFICULTY_PROFILES[1]


class TestDifficultyAffectsMonteCarlo:
    @pytest.fixture
    def mc_setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HEMBUDGET_SCHOOL_MODE", "1")
        from hembudget.config import settings
        monkeypatch.setattr(settings, "data_dir", tmp_path)
        from hembudget.school import engines as eng_mod
        if eng_mod._master_engine is not None:
            eng_mod._master_engine.dispose()
        eng_mod._master_engine = None
        eng_mod._master_session = None
        from hembudget.school.engines import init_master_engine
        init_master_engine()

    def test_higher_level_lower_positive_pct(self, mc_setup):
        """Nivå 3 ska ha lägre positive% än nivå 1 vid samma spend."""
        from hembudget.game_engine.monte_carlo import (
            SimConfig, run_simulations, summarize,
        )
        cfg1 = SimConfig(
            n_simulations=500, starting_level=1, spend_profile="balanserad",
        )
        cfg3 = SimConfig(
            n_simulations=500, starting_level=3, spend_profile="balanserad",
        )
        s1 = summarize(run_simulations(cfg1))
        s3 = summarize(run_simulations(cfg3))
        assert s1["classification"]["positive_pct"] > s3["classification"]["positive_pct"]

    def test_design_targets_hit_within_bounds(self, mc_setup):
        """Slutkalibrerade profiler ska träffa designmål inom ±8 procentenheter
        med 1000 sims (statistisk variation tillåten)."""
        from hembudget.game_engine.monte_carlo import (
            SimConfig, run_simulations, summarize,
        )
        # Bara test ett urval för att hålla testsuiten snabb
        targets = [
            (1, "sparsam", 90, 95),
            (2, "balanserad", 60, 70),
            (3, "slosa", 25, 35),
        ]
        for level, spend, lo, hi in targets:
            cfg = SimConfig(
                n_simulations=1000, starting_level=level,
                spend_profile=spend, partner_model="auto",
            )
            s = summarize(run_simulations(cfg))
            pos = s["classification"]["positive_pct"]
            # ±8p tolerans pga 1000-sims-brus
            assert lo - 8 <= pos <= hi + 8, (
                f"Nivå {level} {spend}: {pos:.1f}% utanför {lo-8}-{hi+8}%"
            )
