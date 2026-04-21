"""End-to-end-test mot användarens riktiga CSV/XLSX-data.

Syfte: simulera hela användarflödet med verkliga filer från data/-mappen
och verifiera att parsing, matchning och saldo-beräkningar stämmer.

Körs via TestClient mot FastAPI-appen — INGEN LLM behövs (kategorisering
använder regler + historik men inga LLM-fallbacks).

Returnerar en rapport med:
- Antal importerade rader per fil
- Saldon per konto
- Antal matchade transfers
- Antal okategoriserade (förvantat hög utan LLM)
- Budget-summering per månad
- Eventuella fel/avvikelser
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

os.environ["HEMBUDGET_DATA_DIR"] = "/tmp/hembudget-e2e"

import shutil
if os.path.exists("/tmp/hembudget-e2e"):
    shutil.rmtree("/tmp/hembudget-e2e")

from fastapi.testclient import TestClient
from hembudget.main import app


def main() -> int:
    client = TestClient(app)
    report: dict = {"errors": []}

    # Initiera + logga in
    r = client.get("/status")
    print(f"/status: {r.status_code}")

    r = client.post("/init", json={"password": "testtest"})
    if r.status_code != 200:
        # Redan initialiserad — logga in
        r = client.post("/login", json={"password": "testtest"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    print("✓ Init/login OK")

    # Skapa 3 konton
    def create_acc(name, bank, type_, account_number=None):
        payload = {
            "name": name, "bank": bank, "type": type_,
            "account_number": account_number,
        }
        r = client.post("/accounts", headers=h, json=payload)
        assert r.status_code == 200, r.text
        return r.json()["id"]

    lonekonto_id = create_acc("Nordea lönekonto", "nordea", "checking", "1709 20 72840")
    gemensamt_id = create_acc("Nordea gemensamt", "nordea", "shared", "1722 20 34439")
    sebkort_id = create_acc("SEB Kort", "seb_kort", "credit")
    print(f"✓ Skapade konton: löne={lonekonto_id}, gemensamt={gemensamt_id}, seb={sebkort_id}")

    # Koppla SEB Kort → betalas från Gemensamt
    r = client.patch(f"/accounts/{sebkort_id}", headers=h,
                     json={"pays_credit_account_id": gemensamt_id})
    assert r.status_code == 200, r.text
    print("✓ SEB Kort betalas från Gemensamt")

    data_root = Path(__file__).parent / "data"

    # Importera Nordea lönekonto
    lonekonto_files = sorted((data_root / "Nordea" / "1709 20 72840").glob("*.csv"))
    for f in lonekonto_files:
        with open(f, "rb") as fh:
            r = client.post("/import/csv", headers=h,
                            files={"file": (f.name, fh, "text/csv")},
                            data={"account_id": str(lonekonto_id), "bank": "nordea"})
        if r.status_code != 200:
            report["errors"].append(f"Import {f.name}: {r.status_code} {r.text[:200]}")
            continue
        j = r.json()
        print(f"  Löne {f.name}: parsed={j['rows_parsed']} inserted={j['rows_inserted']} "
              f"cats={j['categorized']} transfers={j['transfers_marked']}")

    # Importera Nordea gemensamt
    gemensamt_files = sorted((data_root / "Nordea" / "1722 20 34439").glob("*.csv"))
    for f in gemensamt_files:
        with open(f, "rb") as fh:
            r = client.post("/import/csv", headers=h,
                            files={"file": (f.name, fh, "text/csv")},
                            data={"account_id": str(gemensamt_id), "bank": "nordea"})
        if r.status_code != 200:
            report["errors"].append(f"Import {f.name}: {r.status_code} {r.text[:200]}")
            continue
        j = r.json()
        print(f"  Gem   {f.name}: parsed={j['rows_parsed']} inserted={j['rows_inserted']} "
              f"cats={j['categorized']} transfers={j['transfers_marked']}")

    # Importera SEB Kort XLSX
    seb_files = sorted((data_root / "seb").glob("*.xlsx"))
    for f in seb_files:
        with open(f, "rb") as fh:
            r = client.post("/import/csv", headers=h,
                            files={"file": (f.name, fh,
                                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                            data={"account_id": str(sebkort_id), "bank": "seb_kort"})
        if r.status_code != 200:
            report["errors"].append(f"Import {f.name}: {r.status_code} {r.text[:200]}")
            continue
        j = r.json()
        print(f"  SEB   {f.name}: parsed={j['rows_parsed']} inserted={j['rows_inserted']} "
              f"cats={j['categorized']} transfers={j['transfers_marked']}")

    # Kör transfer-scan
    r = client.post("/admin/scan-transfers", headers=h)
    assert r.status_code == 200, r.text
    print(f"✓ Transfer scan: {r.json()}")

    # Omkategorisera (använder nya seed-regler)
    r = client.post("/admin/recategorize", headers=h)
    print(f"✓ Recategorize: {r.json()}")

    # Hämta balances
    r = client.get("/balances/", headers=h)
    assert r.status_code == 200, r.text
    balances = r.json()
    print(f"\n=== SALDON (as_of {balances['as_of']}) ===")
    for a in balances["accounts"]:
        print(f"  {a['name']:30s}  {a['current_balance']:>12,.2f}  "
              f"(rörelse {a['movement_since_opening']:>+12,.2f})")
    print(f"  TOTAL: {balances['total_balance']:>12,.2f}")

    # Budget-månader
    r = client.get("/budget/months", headers=h)
    months = r.json().get("months", [])
    print(f"\n=== MÅNADER MED DATA ({len(months)}) ===")
    for m in months:
        print(f"  {m['month']}: {m['count']} transaktioner")

    # Budget för varje månad
    for m in months:
        r = client.get(f"/budget/{m['month']}", headers=h)
        b = r.json()
        print(f"\n  {m['month']}: inkomst={b['income']:>10,.0f}  utgifter={b['expenses']:>10,.0f}  "
              f"netto={b['savings']:>+10,.0f}")

    # Transfers — parade + opparerade
    r = client.get("/transfers/paired", headers=h)
    paired = r.json()
    print(f"\n=== TRANSFERS ===")
    print(f"  Parade: {paired['count']}")
    r = client.get("/transfers/unpaired", headers=h)
    unpaired = r.json()
    print(f"  Opparerade (markerade): {unpaired['count']}")
    r = client.get("/transfers/suggestions", headers=h)
    sugg = r.json()
    print(f"  Förslag: {sugg['count']}")

    # Abonnemang
    r = client.post("/budget/subscriptions/detect", headers=h)
    subs = r.json()
    print(f"\n=== ABONNEMANG ({subs['count']}) ===")
    for s in subs.get("subscriptions", [])[:5]:
        print(f"  {s['merchant']:40s}  {s['amount']:>8,.0f} kr  var {s['interest_days'] if 'interest_days' in s else s.get('interval_days')}e dag "
              f"(nästa {s['next_expected_date']})")

    # Sammanfattning
    print("\n" + "=" * 60)
    print("SLUTRAPPORT")
    print("=" * 60)

    total_tx_r = client.get("/transactions?limit=2000", headers=h)
    all_tx = total_tx_r.json()
    print(f"Totalt transaktioner: {len(all_tx)}")
    categorized = sum(1 for t in all_tx if t["category_id"] is not None)
    uncategorized = sum(1 for t in all_tx if t["category_id"] is None and not t["is_transfer"])
    transfers = sum(1 for t in all_tx if t["is_transfer"])
    print(f"  - Kategoriserade: {categorized}")
    print(f"  - Transfer:       {transfers}")
    print(f"  - Okategoriserade (icke-transfer): {uncategorized}")

    # Topp-20 okategoriserade merchants för att förbättra seed-rules
    from collections import Counter
    uncat_merchants = Counter()
    for t in all_tx:
        if t["category_id"] is None and not t["is_transfer"]:
            uncat_merchants[t["normalized_merchant"] or t["raw_description"]] += 1
    print("\n=== TOPP 30 OKATEGORISERADE ===")
    for merchant, count in uncat_merchants.most_common(30):
        print(f"  {count:3d}×  {merchant[:100]}")

    if report["errors"]:
        print("\nFEL:")
        for e in report["errors"]:
            print(f"  - {e}")
    else:
        print("\n✓ Inga fel under importen.")

    return 0 if not report["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
