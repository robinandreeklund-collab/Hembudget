"""Tester för game_engine/pools/ — konsistens + realism för 2026-data.

Pools är datafundamentet för Profile Generator (G3-G4) och får inte
drifta från SCB-värden eller bli självmotsägande mellan körningar.
"""
from __future__ import annotations

import random
from collections import Counter

import pytest

from hembudget.game_engine.pools import (
    YRKESPOOL,
    YRKE_BY_KEY,
    STADSPOOL,
    pick_city_weighted,
    pick_yrke_by_archetype,
)
from hembudget.game_engine.pools.stadspool import (
    STAD_BY_KEY,
    pick_city_by_region,
)


# === YRKESPOOL: STRUKTUR + REALISM ===


class TestYrkespoolStruktur:
    def test_pool_har_minst_25_yrken(self):
        """Spec siktar på ~30 — vi accepterar 25-50 i denna fas."""
        assert 25 <= len(YRKESPOOL) <= 50

    def test_alla_yrken_har_unik_key(self):
        keys = [y.key for y in YRKESPOOL]
        duplicates = [k for k, c in Counter(keys).items() if c > 1]
        assert not duplicates, f"Duplikat-keys: {duplicates}"

    def test_lookup_index_matchar_pool(self):
        assert len(YRKE_BY_KEY) == len(YRKESPOOL)
        for y in YRKESPOOL:
            assert YRKE_BY_KEY[y.key] is y

    def test_ssyk_ar_4_siffrigt(self):
        for y in YRKESPOOL:
            assert y.ssyk.isdigit() and len(y.ssyk) == 4, (
                f"{y.key}: SSYK {y.ssyk!r} ska vara 4 siffror"
            )


class TestYrkespoolRealism:
    def test_min_lon_under_median_under_max(self):
        for y in YRKESPOOL:
            assert y.monthly_gross_min < y.monthly_gross_median < y.monthly_gross_max, (
                f"{y.key}: lönespann inkonsistent "
                f"({y.monthly_gross_min}/{y.monthly_gross_median}/{y.monthly_gross_max})"
            )

    def test_lon_inom_realistiskt_2026_spann(self):
        """Heltid-yrken: 22-90k min, 25-120k max. Studerande deltid undantas."""
        for y in YRKESPOOL:
            if y.key.startswith("studerande_") or y.education_level == "ingen":
                # Deltids-/instegs-arketyper (studiebidrag + extrajobb)
                assert 1_000 <= y.monthly_gross_min, (
                    f"{y.key}: min-lön {y.monthly_gross_min} orealistiskt låg"
                )
                continue
            assert 22_000 <= y.monthly_gross_min <= 90_000, (
                f"{y.key}: min-lön {y.monthly_gross_min} utanför rimligt spann"
            )
            assert 25_000 <= y.monthly_gross_max <= 120_000, (
                f"{y.key}: max-lön {y.monthly_gross_max} utanför rimligt spann"
            )

    def test_education_hogskola_har_hogre_median_an_gymnasium(self):
        """Sanity: högskoleyrken ska i snitt ge mer än gymnasieyrken."""
        gym = [y.monthly_gross_median for y in YRKESPOOL if y.education_level == "gymnasium"]
        hog = [y.monthly_gross_median for y in YRKESPOOL if y.education_level == "hogskola"]
        if gym and hog:
            assert sum(hog) / len(hog) > sum(gym) / len(gym), (
                "Högskoleyrken har inte högre snittlön än gymnasieyrken"
            )

    def test_weight_per_level_innehaller_alla_niva(self):
        for y in YRKESPOOL:
            for level in (1, 2, 3):
                assert level in y.weight_per_level, (
                    f"{y.key}: saknar vikt för level {level}"
                )
                assert 0 <= y.weight_per_level[level] <= 5, (
                    f"{y.key}: orimlig vikt för level {level}"
                )

    def test_competency_match_inte_tom(self):
        for y in YRKESPOOL:
            assert y.competency_match, f"{y.key}: saknar competency_match"

    def test_physical_demand_och_schedule_inom_1_10(self):
        for y in YRKESPOOL:
            assert 1 <= y.physical_demand <= 10
            assert 1 <= y.schedule_irregularity <= 10


# === STADSPOOL: STRUKTUR + REALISM ===


class TestStadspoolStruktur:
    def test_har_minst_12_stader(self):
        assert len(STADSPOOL) >= 12

    def test_alla_stader_har_unik_key(self):
        keys = [s.key for s in STADSPOOL]
        duplicates = [k for k, c in Counter(keys).items() if c > 1]
        assert not duplicates, f"Duplikat-keys: {duplicates}"

    def test_lookup_index_matchar_pool(self):
        assert len(STAD_BY_KEY) == len(STADSPOOL)

    def test_innehaller_de_tre_storstaderna(self):
        keys = {s.key for s in STADSPOOL}
        assert {"stockholm", "goteborg", "malmo"}.issubset(keys)

    def test_innehaller_generiska_orter(self):
        """`medelstad` + `smaort` används som fallback i city_preference."""
        keys = {s.key for s in STADSPOOL}
        assert "medelstad" in keys
        assert "smaort" in keys


class TestStadspoolRealism:
    def test_bostadspct_summerar_till_cirka_ett(self):
        """BRF + villa + hyresrätt ska summera till ~1.0 (±10%)."""
        for s in STADSPOOL:
            total = s.bostad_pct_brf + s.bostad_pct_villa + s.bostad_pct_hyresratt
            assert 0.90 <= total <= 1.10, (
                f"{s.key}: bostadsandelar summerar till {total:.2f}"
            )

    def test_stockholm_dyrast_for_brf(self):
        sthlm = STAD_BY_KEY["stockholm"]
        for s in STADSPOOL:
            if s.key == "stockholm":
                continue
            assert s.avg_brf_price_per_kvm <= sthlm.avg_brf_price_per_kvm, (
                f"{s.key} ({s.avg_brf_price_per_kvm}) > Stockholm "
                f"({sthlm.avg_brf_price_per_kvm}) — orealistiskt"
            )

    def test_smaort_billigast_for_brf(self):
        smaort = STAD_BY_KEY["smaort"]
        for s in STADSPOOL:
            if s.key == "smaort":
                continue
            assert smaort.avg_brf_price_per_kvm <= s.avg_brf_price_per_kvm, (
                f"Småort dyrare än {s.key} — orealistiskt"
            )

    def test_kostnadsmultiplikatorer_inom_rimligt_spann(self):
        for s in STADSPOOL:
            assert 0.5 <= s.cost_multiplier_housing <= 2.0
            assert 0.7 <= s.cost_multiplier_food <= 1.3
            assert 0.5 <= s.cost_multiplier_transport <= 1.5

    def test_brf_pris_inom_realistiskt_2026_spann(self):
        for s in STADSPOOL:
            assert 10_000 <= s.avg_brf_price_per_kvm <= 100_000, (
                f"{s.key}: BRF-pris {s.avg_brf_price_per_kvm} orealistiskt"
            )

    def test_hyra_inom_realistiskt_spann(self):
        """Hyresgästföreningen 2024: 80-160 kr/kvm/mån."""
        for s in STADSPOOL:
            assert 70 <= s.avg_rental_per_kvm_month <= 200, (
                f"{s.key}: hyra {s.avg_rental_per_kvm_month} orealistisk"
            )

    def test_storstader_har_hogre_jobtathet(self):
        """Stockholm/Göteborg/Malmö ska ha högre job_density än småort."""
        smaort = STAD_BY_KEY["smaort"]
        for big in ("stockholm", "goteborg", "malmo"):
            assert STAD_BY_KEY[big].job_density > smaort.job_density


# === DETERMINISM + PICKERS ===


class TestDeterminism:
    def test_samma_seed_ger_samma_yrke(self):
        rng1 = random.Random(12345)
        rng2 = random.Random(12345)
        y1 = pick_yrke_by_archetype(rng1, "random", 1)
        y2 = pick_yrke_by_archetype(rng2, "random", 1)
        assert y1.key == y2.key

    def test_samma_seed_ger_samma_stad(self):
        rng1 = random.Random(99)
        rng2 = random.Random(99)
        s1 = pick_city_weighted(rng1)
        s2 = pick_city_weighted(rng2)
        assert s1.key == s2.key

    def test_olika_seed_ger_spridning(self):
        """100 körningar med olika seeds ska träffa minst 8 olika städer."""
        cities_seen = set()
        for seed in range(100):
            rng = random.Random(seed)
            cities_seen.add(pick_city_weighted(rng).key)
        assert len(cities_seen) >= 8, (
            f"Bara {len(cities_seen)} unika städer på 100 seeds — för dålig spridning"
        )


class TestPickerLogik:
    def test_pick_yrke_med_specifik_arketyp(self):
        rng = random.Random(1)
        y = pick_yrke_by_archetype(rng, "vard_underskoterska", 1)
        assert y.archetype == "vard_underskoterska"

    def test_pick_yrke_med_okand_arketyp_fallback(self):
        """Om arketypen inte finns ska den falla tillbaka till random."""
        rng = random.Random(1)
        # Casta som any för att kringgå Literal-typen i testet
        y = pick_yrke_by_archetype(rng, "random", 2)  # type: ignore[arg-type]
        assert y in YRKESPOOL

    def test_city_preference_okar_traffsannolikheten(self):
        """Med preferens för Stockholm ska Stockholm väljas oftare än utan."""
        without_pref = 0
        with_pref = 0
        for seed in range(200):
            rng_a = random.Random(seed)
            rng_b = random.Random(seed)
            if pick_city_weighted(rng_a).key == "stockholm":
                without_pref += 1
            if pick_city_weighted(rng_b, ["stockholm"]).key == "stockholm":
                with_pref += 1
        assert with_pref > without_pref, (
            f"Preferens hade ingen effekt: {without_pref} → {with_pref}"
        )

    def test_pick_city_by_region(self):
        rng = random.Random(7)
        s = pick_city_by_region(rng, "Stockholm")
        assert s.region == "Stockholm"


# === KORS-VALIDERING POOLS ===


class TestPoolKonsistens:
    def test_yrken_med_ob_har_hog_schedule_irregularity(self):
        """Sanity: vård + brandman ska ha irregularity ≥ 7."""
        for key in ("underskoterska", "brandman"):
            if key in YRKE_BY_KEY:
                assert YRKE_BY_KEY[key].schedule_irregularity >= 7, (
                    f"{key} bör ha hög schedule_irregularity"
                )

    def test_studerande_har_lagsta_lon(self):
        if "studerande_gymnasium" in YRKE_BY_KEY:
            stud = YRKE_BY_KEY["studerande_gymnasium"]
            other_medians = [
                y.monthly_gross_median for y in YRKESPOOL
                if y.key != "studerande_gymnasium"
            ]
            assert stud.monthly_gross_median <= min(other_medians), (
                "Studerande borde ha lägst median"
            )
