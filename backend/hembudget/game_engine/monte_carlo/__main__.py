"""CLI-runner för Monte Carlo · python -m hembudget.game_engine.monte_carlo

Användning:
  python -m hembudget.game_engine.monte_carlo --n 1000 --level 1 --spend sparsam
  python -m hembudget.game_engine.monte_carlo --grid    # alla nivåer × spend
"""
from __future__ import annotations

import argparse
import json
import time

from . import SimConfig, run_simulations, summarize


def _print_row(s: dict, level: int, spend: str, elapsed: float) -> None:
    cls = s["classification"]
    bal = s["end_balance"]
    print(
        f"Nivå {level} {spend:11} {elapsed:.1f}s "
        f"pos={cls['positive_pct']:>5.1f}% "
        f"mar={cls['marginal_pct']:>5.1f}% "
        f"neg={cls['negative_pct']:>5.1f}% "
        f"median={bal['median']:>+9} kr "
        f"p10={bal['p10']:>+9} kr p90={bal['p90']:>+9} kr"
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=500, help="Antal simuleringar")
    p.add_argument("--months", type=int, default=12)
    p.add_argument("--level", type=int, default=1, choices=(1, 2, 3))
    p.add_argument("--spend", choices=("sparsam", "balanserad", "slosa"), default="balanserad")
    p.add_argument("--archetype", default="random")
    p.add_argument("--partner", default="auto")
    p.add_argument("--seed-base", type=int, default=0)
    p.add_argument("--grid", action="store_true", help="Kör alla 3×3-kombos")
    p.add_argument("--json", action="store_true", help="Output som JSON")
    args = p.parse_args()

    # Master-DB krävs för tax-config
    import os
    os.environ.setdefault("HEMBUDGET_SCHOOL_MODE", "1")
    from ...school.engines import init_master_engine
    init_master_engine()

    if args.grid:
        all_results = {}
        for level in (1, 2, 3):
            for spend in ("sparsam", "balanserad", "slosa"):
                cfg = SimConfig(
                    n_simulations=args.n,
                    n_months=args.months,
                    starting_level=level,
                    spend_profile=spend,
                    archetype=args.archetype,
                    partner_model=args.partner,
                    seed_base=args.seed_base,
                )
                t0 = time.time()
                res = run_simulations(cfg)
                summary = summarize(res)
                elapsed = time.time() - t0
                if args.json:
                    all_results[f"level{level}_{spend}"] = summary
                else:
                    _print_row(summary, level, spend, elapsed)
        if args.json:
            print(json.dumps(all_results, indent=2, ensure_ascii=False))
    else:
        cfg = SimConfig(
            n_simulations=args.n,
            n_months=args.months,
            starting_level=args.level,
            spend_profile=args.spend,
            archetype=args.archetype,
            partner_model=args.partner,
            seed_base=args.seed_base,
        )
        t0 = time.time()
        res = run_simulations(cfg)
        summary = summarize(res)
        elapsed = time.time() - t0
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            _print_row(summary, args.level, args.spend, elapsed)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
