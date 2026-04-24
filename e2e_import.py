"""End-to-end-verifiering mot användarens hela test-data.

Importera alla CSV:er och alla PDFer, verifiera att:
- Alla konton balanserar mot sina CSV-saldon
- Amex/SEB-korten visar exakt fakturans saldo
- Löner hittas och kategoriseras
- Kategorisering fungerar
"""
from __future__ import annotations

import hashlib
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data_for_test"

os.environ["HEMBUDGET_DEMO_MODE"] = "1"

# Importera backend
sys.path.insert(0, str(ROOT / "backend"))

from hembudget.db.models import Base, Account, Transaction, Category  # noqa
from hembudget import demo as demo_mod  # noqa
demo_mod.bootstrap_if_empty = lambda: {"skipped": True}
from hembudget.api import deps as api_deps  # noqa
from hembudget.main import build_app  # noqa
from hembudget.categorize.rules import seed_categories_and_rules  # noqa


def make_client():
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SL = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    # Seeda kategorier + regler
    with SL() as s:
        seed_categories_and_rules(s)
        s.commit()

    app = build_app()

    def _db():
        s = SL()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    app.dependency_overrides[api_deps.db] = _db
    return TestClient(app), SL


def extract_opening_from_nordea_csv(path: Path) -> tuple[Decimal, date]:
    """Sista raden (äldsta datum) har saldo EFTER transaktionen. Vi vill
    veta saldo FÖRE = saldo_efter - belopp_på_raden."""
    import csv
    with open(path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    if not rows:
        return Decimal("0"), date.today()
    last = rows[-1]  # äldsta
    saldo_after = Decimal(last["Saldo"].replace(",", "."))
    amount = Decimal(last["Belopp"].replace(",", "."))
    opening = saldo_after - amount
    d_parts = last["Bokföringsdag"].split("/")
    tx_date = date(int(d_parts[0]), int(d_parts[1]), int(d_parts[2]))
    # Opening gäller från dagen FÖRE äldsta transaktion
    from datetime import timedelta
    return opening, tx_date - timedelta(days=1)


def final_balance_from_nordea_csv(path: Path) -> Decimal:
    """FÖRSTA raden (senaste) har slutsaldo."""
    import csv
    with open(path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    if not rows:
        return Decimal("0")
    return Decimal(rows[0]["Saldo"].replace(",", "."))


def import_account(client, SL, account_name, account_number, acc_type, bank, csvs):
    # Skapa konto med opening_balance från ÄLDSTA CSV
    # Vi antar att CSVerna är tidssorterade så äldsta är sist i sorterad lista
    sorted_csvs = sorted(csvs)  # filnamn har timestamp
    # Få opening från den tidigaste filen (äldsta CSV-filen sparad först)
    oldest = sorted_csvs[0]
    opening, opening_date = extract_opening_from_nordea_csv(oldest)

    # Skapa konto
    r = client.post(
        "/accounts",
        json={
            "name": account_name,
            "bank": bank,
            "type": acc_type,
            "account_number": account_number,
            "opening_balance": str(opening),
            "opening_balance_date": opening_date.isoformat(),
        },
    )
    assert r.status_code == 200, r.text
    acc_id = r.json()["id"]

    # Importera alla CSVer
    for csv_path in sorted_csvs:
        with open(csv_path, "rb") as f:
            r = client.post(
                "/import/csv",
                data={"account_id": str(acc_id), "bank": bank},
                files={"file": (csv_path.name, f.read(), "text/csv")},
            )
        assert r.status_code == 200, f"{csv_path.name}: {r.text}"

    return acc_id, opening


def main():
    client, SL = make_client()

    # Setup alla Nordea-konton
    print("=" * 72)
    print("KONTON + CSV-IMPORT")
    print("=" * 72)

    accounts_config = [
        ("Mat 1722 20 34439", "1722 20 34439", "shared", "nordea",
         DATA / "Mat 1722 20 34439"),
        ("Rese 1190 30 10772", "1190 30 10772", "savings", "nordea",
         DATA / "Rese 1190 30 10772"),
        ("Robin 1709 20 72840", "1709 20 72840", "checking", "nordea",
         DATA / "Robin 1709 20 72840"),
        ("Robin 880104-7591", "880104-7591", "checking", "nordea",
         DATA / "Robin 880104-7591"),
        ("Robin spar 3435 20 01910", "3435 20 01910", "savings", "nordea",
         DATA / "Robin spar 3435 20 01910"),
    ]

    acc_ids: dict[str, int] = {}
    for name, num, acc_type, bank, dir_ in accounts_config:
        csvs = sorted(dir_.glob("*.csv"))
        if not csvs:
            print(f"  SKIPPAR {name}: inga CSV:er")
            continue
        acc_id, opening = import_account(
            client, SL, name, num, acc_type, bank, csvs,
        )
        acc_ids[name] = acc_id

        # Jämför slut-saldo från senaste CSV mot kontots nuvarande saldo
        newest = csvs[-1]  # filnamnen är timestamps, senaste sist
        expected_final = final_balance_from_nordea_csv(newest)
        r = client.get("/balances/")
        found = next(a for a in r.json()["accounts"] if a["id"] == acc_id)
        got = Decimal(str(found["current_balance"]))
        match = "✓" if abs(got - expected_final) < Decimal("1") else "❌"
        print(f"  {match} {name}: saldo={got:.2f} förväntat={expected_final:.2f}")

    # Importera Amex (3 fakturor)
    print("\n" + "=" * 72)
    print("AMEX-FAKTUROR")
    print("=" * 72)
    amex_dir = DATA / "Amex"
    for pdf in sorted(amex_dir.glob("*.pdf")):
        with open(pdf, "rb") as f:
            r = client.post(
                "/upcoming/parse-credit-card-pdf",
                files={"file": (pdf.name, f.read(), "application/pdf")},
            )
        if r.status_code != 200:
            print(f"  ❌ {pdf.name}: {r.status_code} {r.text[:200]}")
            continue
        body = r.json()
        print(f"  ✓ {pdf.name}: {body['transactions_created']} tx, "
              f"summa={body['invoice_total']:.2f}, "
              f"förfallodag={body['due_date']}")
        breakdown = body.get("cardholders_breakdown", {})
        for holder, amt in breakdown.items():
            print(f"      👤 {holder}: {amt:.2f}")

    # Importera SEB (4 fakturor)
    print("\n" + "=" * 72)
    print("SEB KORT-FAKTUROR")
    print("=" * 72)
    seb_dir = DATA / "seb"
    for pdf in sorted(seb_dir.glob("*.pdf")):
        with open(pdf, "rb") as f:
            r = client.post(
                "/upcoming/parse-credit-card-pdf",
                files={"file": (pdf.name, f.read(), "application/pdf")},
            )
        if r.status_code != 200:
            print(f"  ❌ {pdf.name}: {r.status_code} {r.text[:200]}")
            continue
        body = r.json()
        print(f"  ✓ {pdf.name}: {body['transactions_created']} tx, "
              f"summa={body['invoice_total']:.2f}, "
              f"förfallodag={body['due_date']}")
        breakdown = body.get("cardholders_breakdown", {})
        for holder, amt in breakdown.items():
            print(f"      👤 {holder}: {amt:.2f}")

    # Totala kontosaldon
    print("\n" + "=" * 72)
    print("ALLA SALDON")
    print("=" * 72)
    r = client.get("/balances/")
    body = r.json()
    for a in body["accounts"]:
        print(f"  {a['name']:<40} {a['current_balance']:>12.2f} kr "
              f"({a['bank']}/{a['type']})")
    print(f"  {'TOTALT':<40} {body['total_balance']:>12.2f} kr")

    # Löner
    print("\n" + "=" * 72)
    print("YTD LÖN PER PERSON")
    print("=" * 72)
    r = client.get("/budget/ytd-income")
    ytd = r.json()
    print(f"  År: {ytd['year']}   Kategori-match: {ytd['category_matched']}")
    for k, v in ytd["by_owner"].items():
        print(f"  {k}: {v['total']:.2f} kr ({v['count']} rader)")
    print(f"  Grand total: {ytd['grand_total']:.2f} kr")

    # Månadsbudget per månad
    print("\n" + "=" * 72)
    print("MÅNADSSAMMANFATTNING (jan-apr 2026)")
    print("=" * 72)
    for month in ["2026-01", "2026-02", "2026-03", "2026-04"]:
        r = client.get(f"/budget/{month}")
        if r.status_code != 200:
            print(f"  {month}: {r.status_code} {r.text[:80]}")
            continue
        s = r.json()
        print(f"  {month}: inkomst={s['income']:>10.0f}  "
              f"utgifter={s['expenses']:>10.0f}  "
              f"sparande={s['savings']:>10.0f}  "
              f"sparkvot={s['savings_rate']*100:.1f}%")

    # Ej kategoriserade transaktioner
    print("\n" + "=" * 72)
    print("EJ KATEGORISERADE (top 20)")
    print("=" * 72)
    with SL() as s:
        no_cat = (
            s.query(Transaction)
            .filter(
                Transaction.category_id.is_(None),
                Transaction.is_transfer.is_(False),
            )
            .order_by(Transaction.date.desc())
            .limit(20)
            .all()
        )
        for t in no_cat:
            print(f"  {t.date}  {float(t.amount):>10.2f}  {t.raw_description[:60]}")

    # Kategorisering
    print("\n" + "=" * 72)
    print("KATEGORISERING")
    print("=" * 72)
    with SL() as s:
        total_tx = s.query(Transaction).count()
        no_cat = s.query(Transaction).filter(
            Transaction.category_id.is_(None),
            Transaction.is_transfer.is_(False),
        ).count()
        transfers = s.query(Transaction).filter(
            Transaction.is_transfer.is_(True)
        ).count()
        cats = (
            s.query(Category.name, Transaction.id)
            .join(Transaction, Transaction.category_id == Category.id)
            .all()
        )
        per_cat: dict[str, int] = defaultdict(int)
        for name, _ in cats:
            per_cat[name] += 1
        print(f"  Totalt {total_tx} transaktioner")
        print(f"  Kategoriserade: {total_tx - no_cat - transfers}")
        print(f"  Transfers:      {transfers}")
        print(f"  Okategoriserade: {no_cat}")
        print(f"  Top 10 kategorier:")
        for name, cnt in sorted(per_cat.items(), key=lambda x: -x[1])[:10]:
            print(f"    {name:<30} {cnt} tx")


if __name__ == "__main__":
    main()
