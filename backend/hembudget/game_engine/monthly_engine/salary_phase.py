"""Fas A · Lönespec.

Spec: dev/game-motor/03-monthly-engine.md (Fas A).

Per spelmånad genererar vi:
  1. En `MailItem` med kind="salary_slip" som beskriver bruttolön → netto
  2. En `Transaction` som krediterar lönekontot med nettobeloppet
     på utbetalningsdagen (default 25:e i månaden)

För hushåll med partner skapas separat lönespec + transaktion för
partnern (också på 25:e).
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from ...db.models import Account, MailItem, Transaction
from ...school.tax import compute_net_salary
from ..pools.yrkespool import YRKE_BY_KEY
from ..profile_generator.schema import GeneratedProfile
from ..release_schedule import release_at_for_day


SALARY_DAY = 25  # Utbetalningsdag · pengarna landar på kontot
LONESPEC_DAY = 22  # Lönespec-mailet · normalt 2-3 dagar före utbetalning


def _payday(year_month: str) -> date:
    """Returnera 25:e i year_month (eller sista i månaden om kortare)."""
    y, m = map(int, year_month.split("-"))
    return date(y, m, SALARY_DAY)


def _tx_hash(student_scope: str, year_month: str, kind: str) -> str:
    """Stabil hash för dedup. Samma (scope, ym, kind) ger samma hash."""
    raw = f"{student_scope}|{year_month}|{kind}|monthly_engine"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _build_salary_body(
    *,
    name: str,
    yrke_display: str,
    gross: int,
    net: int,
    grundavdrag: int,
    kommunal: int,
    statlig: int,
    year_month: str,
) -> str:
    """Människo-läsbar lönespec som visas när eleven öppnar mailet."""
    return (
        f"Lönespec för {year_month}\n"
        f"\n"
        f"Anställd: {name}\n"
        f"Befattning: {yrke_display}\n"
        f"\n"
        f"Bruttolön                      {gross:>10,} kr\n"
        f"Grundavdrag                    {grundavdrag:>10,} kr\n"
        f"Kommunalskatt                  {kommunal:>10,} kr\n"
        f"Statlig skatt                  {statlig:>10,} kr\n"
        f"------------------------------ -----------\n"
        f"Nettolön (utbetalas {SALARY_DAY}:e)  {net:>10,} kr\n"
    ).replace(",", " ")


def _create_salary_for(
    s: Session,
    *,
    person_name: str,
    yrke_key: str,
    gross_monthly: int,
    year_month: str,
    salary_account: Account,
    student_scope: str,
    is_partner: bool,
    release_base: Optional[datetime] = None,
) -> tuple[MailItem, Transaction, dict]:
    """Skapa lönespec-mail + lön-in-transaktion för en person."""
    tax = compute_net_salary(gross_monthly)
    yrke = YRKE_BY_KEY.get(yrke_key)
    yrke_display = yrke.display if yrke else "Okänt yrke"

    pay_d = _payday(year_month)

    body = _build_salary_body(
        name=person_name,
        yrke_display=yrke_display,
        gross=tax.gross_monthly,
        net=tax.net_monthly,
        grundavdrag=tax.grundavdrag,
        kommunal=tax.kommunal_tax,
        statlig=tax.statlig_tax,
        year_month=year_month,
    )

    # Lönespec-mailet kommer 2-3 dagar FÖRE lön-transaktionen (det är
    # så det funkar i verkligheten · skattedagen är 22-23, lönedagen 25).
    # I real-tids-projektionen blir mailet alltså synligt innan pengarna
    # syns på kontot — eleven hinner läsa specen, kontrollera skatten,
    # och INNAN pengarna landar.
    mail_released_at = (
        release_at_for_day(release_base, LONESPEC_DAY)
        if release_base is not None
        else None
    )
    tx_released_at = (
        release_at_for_day(release_base, SALARY_DAY)
        if release_base is not None
        else None
    )

    sender_label = "Arbetsgivaren" + (" (partner)" if is_partner else "")
    # received_at = SPEL-datetime · annars stämplas alla seedade mail
    # med real-tid (utcnow) → eleven ser "7 maj" i postlådan trots
    # att lönespec gäller januari. Vi använder pay_d - 3 dgr (lönespec
    # arriverar 2-3 dgr före lön i verkligheten) som naive datetime.
    from datetime import datetime as _dt_sp, timedelta as _td_sp
    spec_arrival = _dt_sp.combine(
        pay_d - _td_sp(days=3), _dt_sp.min.time(),
    ).replace(hour=9)
    mail = MailItem(
        sender=sender_label,
        sender_short="WORK",
        sender_kind="work",
        sender_meta=f"lönespec · {year_month}",
        mail_type="salary_slip",
        subject=f"Lönespec {year_month}",
        body_meta=f"Nettolön {tax.net_monthly:,} kr".replace(",", " "),
        body=body,
        amount=Decimal(tax.net_monthly),
        due_date=pay_d,
        status="unhandled",
        released_at=mail_released_at,
        received_at=spec_arrival,
    )
    s.add(mail)

    kind_suffix = "partner_salary" if is_partner else "salary"
    tx_kind = f"{kind_suffix}_{year_month}"
    desc = (
        f"Lön {year_month} · {yrke_display}"
        + (" (partner)" if is_partner else "")
    )
    tx = Transaction(
        account_id=salary_account.id,
        date=pay_d,
        amount=Decimal(tax.net_monthly),
        currency="SEK",
        raw_description=desc,
        normalized_merchant=sender_label,
        hash=_tx_hash(student_scope, year_month, tx_kind),
        user_verified=True,
        released_at=tx_released_at,
    )
    s.add(tx)
    s.flush()

    summary = {
        "person": "partner" if is_partner else "main",
        "yrke": yrke_display,
        "gross": tax.gross_monthly,
        "net": tax.net_monthly,
        "tax_total": tax.total_tax,
        "mail_id": mail.id,
        "tx_id": tx.id,
        "payday": pay_d.isoformat(),
    }
    return mail, tx, summary


def generate_salary_phase(
    s: Session,
    *,
    profile: GeneratedProfile,
    year_month: str,
    salary_account: Account,
    student_scope: str,
    student_name: Optional[str] = None,
    release_base: Optional[datetime] = None,
) -> dict:
    """Kör Fas A för en spelmånad. Returnerar summary för WeekTickRun.

    Skapar lönespec + lön-in både för huvudspelare och ev. partner.

    `release_base`: T0 för realtid-projektion. Lön släpps på dag 25
    vilket motsvarar T0 + 96h (≈ fredag morgon). None = visa direkt.
    """
    name = student_name or profile.name
    summaries = []

    # Anställningsstatus-gate · skippa huvudpersonens lön om eleven
    # sagt upp sig (status='self_employed'/'unemployed') OCH employment_
    # end_on har passerats. Partner-lön påverkas EJ (partner har sin
    # egen anställning som vi inte simulerar uppsägning för än).
    main_employed = True
    try:
        from ...school.engines import (
            master_session as _ms_emp,
            get_current_actor_student as _gcas_emp,
        )
        from ...school.models import StudentProfile as _SP_emp
        from datetime import date as _d_emp
        _actor_emp = _gcas_emp()
        if _actor_emp is not None:
            with _ms_emp() as _msdb_emp:
                _prof_emp = (
                    _msdb_emp.query(_SP_emp)
                    .filter(_SP_emp.student_id == _actor_emp)
                    .first()
                )
                if _prof_emp is not None:
                    status = (
                        getattr(_prof_emp, "employment_status", None)
                        or "employed"
                    )
                    end_on = getattr(_prof_emp, "employment_end_on", None)
                    ym_y, ym_m = map(int, year_month.split("-"))
                    ym_last_day = _d_emp(
                        ym_y, ym_m,
                        28,  # konservativt 28e så bara hela månader efter
                        # uppsägningstidens slut räknas som "ingen lön"
                    )
                    if status != "employed":
                        # Status redan annan än anställd
                        if end_on is None or ym_last_day > end_on:
                            main_employed = False
    except Exception:
        # Defensiv · vid fel · falla tillbaka till anställd så lön
        # genereras (annars kraschar tick_month tyst för alla elever
        # som har migrationsproblem).
        import logging
        logging.getLogger(__name__).exception(
            "salary_phase: employment-status-check misslyckades · "
            "behandlar som 'employed'",
        )

    if main_employed:
        _mail, _tx, main_summary = _create_salary_for(
            s,
            person_name=name,
            yrke_key=profile.yrke_key,
            gross_monthly=profile.monthly_gross,
            year_month=year_month,
            salary_account=salary_account,
            student_scope=student_scope,
            is_partner=False,
            release_base=release_base,
        )
        summaries.append(main_summary)

    if (
        profile.family.partner_yrke_key
        and profile.family.partner_gross_monthly
        and profile.family.partner_model in ("ai", "klasskompis")
    ):
        _m, _t, partner_summary = _create_salary_for(
            s,
            person_name=f"Partner till {name}",
            yrke_key=profile.family.partner_yrke_key,
            gross_monthly=profile.family.partner_gross_monthly,
            year_month=year_month,
            salary_account=salary_account,
            student_scope=student_scope,
            is_partner=True,
            release_base=release_base,
        )
        summaries.append(partner_summary)

    total_net = sum(x["net"] for x in summaries)
    return {
        "people": summaries,
        "total_net_credited": total_net,
        "payday": _payday(year_month).isoformat(),
    }
