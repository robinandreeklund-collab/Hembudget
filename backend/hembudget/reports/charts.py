"""Matplotlib → PNG-bytes för embedding i ReportLab PDF:er.

All rendering körs headless (Agg-backend) och returnerar bytes direkt.
Vi använder en mjuk, professionell palette med konsistenta färger
mellan figurerna så rapporten hänger ihop visuellt.

**Graceful degradation:** om matplotlib saknas i miljön (t.ex. user
har inte kört 'pip install matplotlib' efter pull) returnerar chart-
funktionerna None istället för att krascha. PDF-rapporten byggs då
utan diagram — KPI, tabeller och transfer-förslag fungerar ändå.
"""
from __future__ import annotations

import io
from typing import Iterable

HAS_MATPLOTLIB = False
try:
    import matplotlib

    matplotlib.use("Agg")  # headless — måste sättas innan pyplot-import
    import matplotlib.pyplot as plt  # noqa: E402
    HAS_MATPLOTLIB = True
except ImportError:
    plt = None  # type: ignore[assignment]


# Tailwind-inspirerad palette — jordnära men ändå distinkt.
# Första åtta används för de vanligaste kategorierna, resten grå.
DEFAULT_PALETTE = [
    "#0f766e",  # teal-700 — Boende/El
    "#b45309",  # amber-700 — Mat
    "#7c3aed",  # violet-600 — Transport
    "#e11d48",  # rose-600 — Nöje/Shopping
    "#059669",  # emerald-600 — Sparande
    "#0284c7",  # sky-600 — Försäkring
    "#a16207",  # yellow-700 — Hälsa
    "#4f46e5",  # indigo-600 — Barn
    "#64748b",  # slate-500 — Övrigt
]

PERSON_PALETTE = [
    "#0f766e",  # teal (primär person)
    "#b45309",  # amber (sekundär)
    "#7c3aed",  # violet
    "#64748b",  # slate (gemensamt)
]


def _as_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=160, bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def pie_chart(
    labels: list[str],
    values: list[float],
    *,
    title: str,
    palette: list[str] | None = None,
    max_slices: int = 8,
) -> bytes | None:
    if not HAS_MATPLOTLIB:
        return None
    """Donut-chart för kategorifördelning. Slår ihop svansen till
    'Övrigt' om antal slices överstiger max_slices — 12 röda slices
    blir oläsligt."""
    if not values or sum(values) <= 0:
        # Render en tom placeholder i stället för att krascha
        fig, ax = plt.subplots(figsize=(4.5, 3.2))
        ax.text(0.5, 0.5, "Ingen data", ha="center", va="center",
                color="#64748b", fontsize=11)
        ax.set_title(title, fontsize=11, color="#0f172a", pad=10)
        ax.axis("off")
        return _as_png(fig)

    # Sortera fallande och slå ihop svansen
    pairs = sorted(zip(labels, values), key=lambda p: -p[1])
    if len(pairs) > max_slices:
        head = pairs[: max_slices - 1]
        tail_sum = sum(v for _, v in pairs[max_slices - 1 :])
        head.append(("Övrigt", tail_sum))
        pairs = head
    labels_s = [p[0] for p in pairs]
    values_s = [p[1] for p in pairs]

    colors = (palette or DEFAULT_PALETTE)[: len(pairs)]
    # Om färre än palette-längd, komplettera med slate
    while len(colors) < len(pairs):
        colors.append("#94a3b8")

    fig, ax = plt.subplots(figsize=(4.8, 3.4))
    total = sum(values_s)

    def _pct(v: float) -> str:
        share = (v / total * 100) if total > 0 else 0
        return f"{share:.0f}%" if share >= 5 else ""

    wedges, _texts, autotexts = ax.pie(
        values_s,
        labels=None,
        colors=colors,
        autopct=lambda pct: f"{pct:.0f}%" if pct >= 5 else "",
        startangle=90,
        pctdistance=0.78,
        wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 2},
        textprops={"fontsize": 9, "color": "white", "weight": "bold"},
    )
    # Legend med belopp
    legend_labels = [
        f"{lab}  {v:,.0f} kr".replace(",", " ")
        for lab, v in zip(labels_s, values_s)
    ]
    ax.legend(
        wedges, legend_labels,
        loc="center left", bbox_to_anchor=(1.02, 0.5),
        fontsize=8.5, frameon=False,
    )
    ax.set_title(title, fontsize=11, color="#0f172a", pad=10)
    return _as_png(fig)


def bar_chart_budget_vs_actual(
    categories: list[str],
    planned: list[float],
    actual: list[float],
    *,
    title: str,
) -> bytes | None:
    if not HAS_MATPLOTLIB:
        return None
    """Horizontal bar chart: planerat vs faktiskt per kategori.
    Utgifter plottas som absolutbelopp. Röd stapel = faktiskt > planerat."""
    if not categories:
        fig, ax = plt.subplots(figsize=(7, 2))
        ax.text(0.5, 0.5, "Ingen budget satt", ha="center", va="center",
                color="#64748b", fontsize=11)
        ax.set_title(title, fontsize=11, color="#0f172a", pad=10)
        ax.axis("off")
        return _as_png(fig)

    n = len(categories)
    # Visa max 12 rader — annars blir det oläsligt
    if n > 12:
        categories = categories[:12]
        planned = planned[:12]
        actual = actual[:12]
        n = 12

    height = max(2.4, 0.45 * n + 1.0)
    fig, ax = plt.subplots(figsize=(7, height))
    y = list(range(n))

    ax.barh(
        [v + 0.18 for v in y],
        planned,
        height=0.36,
        color="#cbd5e1",
        label="Budget",
    )
    actual_colors = [
        "#e11d48" if a > p else "#059669"
        for a, p in zip(actual, planned)
    ]
    ax.barh(
        [v - 0.18 for v in y],
        actual,
        height=0.36,
        color=actual_colors,
        label="Utfall",
    )
    ax.set_yticks(y)
    ax.set_yticklabels(categories, fontsize=9)
    ax.invert_yaxis()
    ax.tick_params(axis="x", labelsize=8, colors="#475569")
    ax.set_xlabel("kr", fontsize=9, color="#475569")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#cbd5e1")
    ax.spines["bottom"].set_color("#cbd5e1")
    ax.grid(axis="x", color="#e2e8f0", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.set_title(title, fontsize=11, color="#0f172a", pad=10)

    # Egen legend så den matchar "röd = över"
    from matplotlib.patches import Patch
    legend_el = [
        Patch(facecolor="#cbd5e1", label="Budget"),
        Patch(facecolor="#059669", label="Utfall (under)"),
        Patch(facecolor="#e11d48", label="Utfall (över)"),
    ]
    ax.legend(
        handles=legend_el, fontsize=8, loc="lower right", frameon=False,
    )
    return _as_png(fig)


def diff_chart_prev_month(
    categories: list[str],
    diffs: list[float],
    *,
    title: str,
) -> bytes | None:
    if not HAS_MATPLOTLIB:
        return None
    """Horizontell bar för förändring mot förra månaden — röd negativ,
    grön positiv. Sorteras fallande efter absolut belopp."""
    if not categories:
        fig, ax = plt.subplots(figsize=(7, 2))
        ax.text(0.5, 0.5, "Ingen historik", ha="center", va="center",
                color="#64748b", fontsize=11)
        ax.set_title(title, fontsize=11, color="#0f172a", pad=10)
        ax.axis("off")
        return _as_png(fig)

    pairs = sorted(zip(categories, diffs), key=lambda p: -abs(p[1]))[:10]
    categories = [p[0] for p in pairs]
    diffs = [p[1] for p in pairs]
    height = max(2.4, 0.4 * len(categories) + 1.0)
    fig, ax = plt.subplots(figsize=(7, height))
    colors = ["#e11d48" if d > 0 else "#059669" for d in diffs]
    ax.barh(
        list(range(len(categories))),
        diffs,
        color=colors,
        height=0.55,
    )
    ax.set_yticks(list(range(len(categories))))
    ax.set_yticklabels(categories, fontsize=9)
    ax.invert_yaxis()
    ax.tick_params(axis="x", labelsize=8, colors="#475569")
    ax.set_xlabel("kr (jämfört med föregående månad)", fontsize=9, color="#475569")
    ax.axvline(0, color="#475569", linewidth=0.7)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.grid(axis="x", color="#e2e8f0", linewidth=0.5)
    ax.set_axisbelow(True)
    ax.set_title(title, fontsize=11, color="#0f172a", pad=10)
    return _as_png(fig)


def colors_for(n: int, palette: Iterable[str] | None = None) -> list[str]:
    pal = list(palette or DEFAULT_PALETTE)
    out: list[str] = []
    for i in range(n):
        out.append(pal[i % len(pal)])
    return out
