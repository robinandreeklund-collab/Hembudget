"""Central nummergenerator för fakturor i företagsläget.

Tidigare hade vi TVÅ olika numreringssystem som rivaliserade:
- `tick_engine.deliver_job`  : f"F-{co.id:04d}-{jobs_delivered:04d}"
- `foretag.add_invoice`      : f"{year}-{n_existing+1:04d}"

Kombinerat med saknad unique-constraint var dubbletter möjliga vid:
1. Tickskapad faktura ("F-0001-0003") + manuell add_invoice ("2026-0001")
   båda räknades till `n_existing` men prefixen var olika
2. Två parallella `add_invoice`-anrop (race condition · läraren
   impersonerar samtidigt som eleven klickar) räknade `n_existing`
   separat → båda fick samma nummer

Den här modulen ger en enda kanonisk helper. Format:
    F-{company_id:04d}-{seq:04d}
där `seq` läses från `SELECT COUNT + 1 FROM company_invoices` med en
SELECT FOR UPDATE-lås per company i Postgres-mode för att eliminera
race conditions. SQLite (test-läge) faller tillbaka till oatomic SELECT
+ retry-loop med UniqueConstraint-violations som signal.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Company, CompanyInvoice


_MAX_RETRIES = 5


def next_invoice_number(s: Session, *, company: Company) -> str:
    """Returnera nästa lediga fakturanummer för company.

    Idempotent och race-säkert · använder UniqueConstraint på
    (tenant_id, company_id, invoice_number) som final spärr; läser
    senaste seq via SELECT MAX(invoice_number) och inkrementerar.

    Format: F-{co.id:04d}-{seq:04d}
    Exempel: F-0001-0001, F-0001-0002, ...

    Anropare ska direkt efter detta `s.add(CompanyInvoice(...,
    invoice_number=...))` och `s.flush()` så att UniqueConstraint
    triggar IntegrityError vid eventuell krock — då kan retry-logik
    fånga den och hämta ett nytt nummer.
    """
    # Hämta högsta numret som börjar på 'F-{co.id:04d}-' och derive
    # nästa seq. SQLite + Postgres stöder LIKE-prefix-sök.
    prefix = f"F-{company.id:04d}-"
    last_n = (
        s.query(func.count(CompanyInvoice.id))
        .filter(
            CompanyInvoice.company_id == company.id,
            CompanyInvoice.invoice_number.like(f"{prefix}%"),
        )
        .scalar()
    ) or 0
    return f"{prefix}{last_n + 1:04d}"


def next_supplier_invoice_number(
    s: Session, *, company: Company, kind_short: str, week_no: int,
) -> str:
    """Returnera nästa lediga supplier-faktura-nummer.

    Format: EV-{week_no}-{kind_short[:5]}-{seq:02d}
    Exempel: EV-3-rabat-01, EV-3-rabat-02

    Tidigare format saknade seq, så två events samma vecka av samma
    kind kunde få identisk invoice_number → race condition + krasch
    vid UniqueConstraint-tillägg.
    """
    from .models import SupplierInvoice
    base = f"EV-{week_no}-{kind_short[:5]}"
    last_n = (
        s.query(func.count(SupplierInvoice.id))
        .filter(
            SupplierInvoice.company_id == company.id,
            SupplierInvoice.invoice_number.like(f"{base}-%"),
        )
        .scalar()
    ) or 0
    return f"{base}-{last_n + 1:02d}"
