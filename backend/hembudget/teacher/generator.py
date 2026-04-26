"""Månadsvis datagenerator för elevernas övningsdata.

Seeden = hash(student_id, year_month). Ger deterministisk men unik data
per elev. Om samma elev kallas två gånger på samma månad blir datan
identisk (idempotent). Olika elever får olika värden.

Skapar:
- Konton (en gång per elev — återanvänds mellan månader)
- Lån (en gång per elev)
- Månadens lön (1 rad)
- Månadens fakturor/upcoming (4-7 rader)
- Månadens transaktioner (25-45 rader) fördelade över kategorier
- Utility-läsning för el
"""
from __future__ import annotations

import calendar
import hashlib
import logging
import random
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from ..db.base import session_scope
from ..db.models import (
    Account,
    Category,
    Loan,
    Transaction,
    UpcomingTransaction,
    UpcomingTransactionLine,
    UtilityReading,
)
from .fixtures import (
    DEFAULT_ACCOUNTS,
    EMPLOYERS,
    INVOICE_TEMPLATES,
    LOAN_TEMPLATES,
    MERCHANTS,
)

log = logging.getLogger(__name__)


def _hash_str(*parts: Any) -> str:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return h[:32]


class MonthlyDataGenerator:
    def __init__(
        self,
        student_id: int,
        year_month: str,
        seed: int | None = None,
    ) -> None:
        self.student_id = student_id
        self.year_month = year_month
        self.year, self.month = map(int, year_month.split("-"))
        self.seed = seed if seed is not None else (
            abs(hash((student_id, year_month))) & 0xFFFFFFFF
        )
        self.rng = random.Random(self.seed)
        # Egen rng för elevens "identitet" (konton, lön, lån)
        # — identisk över månader så eleven har konsistent ekonomi
        self.identity_rng = random.Random(
            abs(hash(("identity", student_id))) & 0xFFFFFFFF
        )
        self._last_day = calendar.monthrange(self.year, self.month)[1]

    # ---------- Huvudentry ----------

    def generate(self, overwrite: bool = False) -> dict:
        stats: dict = {
            "accounts_created": 0,
            "loans_created": 0,
            "transactions_created": 0,
            "upcoming_created": 0,
            "utility_created": 0,
        }
        with session_scope() as session:
            if overwrite:
                self._clear_month(session, stats)

            accounts = self._ensure_accounts(session, stats)
            self._ensure_loans(session, accounts, stats)
            self._generate_salary(session, accounts, stats)
            self._generate_upcoming(session, accounts, stats)
            self._generate_transactions(session, accounts, stats)
            self._generate_utility(session, stats)

        return stats

    # ---------- Konton ----------

    def _ensure_accounts(self, session, stats) -> dict[str, int]:
        """Skapa default-konton om de inte finns. Bevaras över månader."""
        result: dict[str, int] = {}
        existing = session.query(Account).all()
        existing_by_name = {a.name: a for a in existing}

        for spec in DEFAULT_ACCOUNTS:
            acc = existing_by_name.get(spec["name"])
            if acc is None:
                # Eleven ska ha en realistisk startposition (se DEFAULT_ACCOUNTS-
                # kommentaren) — annars går lönekontot minus innan lönen kommer.
                opening = Decimal(str(spec.get("opening_balance", 0) or 0))
                acc = Account(
                    name=spec["name"],
                    bank=spec["bank"],
                    type=spec["type"],
                    currency="SEK",
                    credit_limit=Decimal(str(spec.get("credit_limit", 0) or 0))
                        if spec.get("credit_limit") else None,
                    opening_balance=opening,
                    opening_balance_date=date(self.year, 1, 1),
                )
                session.add(acc)
                session.flush()
                stats["accounts_created"] += 1
            result[spec["type"]] = acc.id

        # Koppla kreditkort → sparkonto som betalkonto
        kreditkort = session.query(Account).filter(
            Account.type == "credit"
        ).first()
        lonekonto = session.query(Account).filter(
            Account.type == "checking"
        ).first()
        if kreditkort and lonekonto and not kreditkort.pays_credit_account_id:
            kreditkort.pays_credit_account_id = lonekonto.id

        return result

    # ---------- Lån ----------

    def _ensure_loans(self, session, accounts, stats) -> None:
        """Välj 1-2 lån (bolån obligatoriskt, billån/CSN slumpvis) en gång."""
        existing = session.query(Loan).count()
        if existing > 0:
            return
        # Bolån alltid
        bolan_templates = [t for t in LOAN_TEMPLATES if "Bolån" in t["name"]]
        bolan = self.identity_rng.choice(bolan_templates)
        self._create_loan(session, bolan)
        stats["loans_created"] += 1

        # 50% chans till extra lån (bil eller CSN eller renovering)
        if self.identity_rng.random() < 0.5:
            extra = self.identity_rng.choice([
                t for t in LOAN_TEMPLATES if "Bolån" not in t["name"]
            ])
            self._create_loan(session, extra)
            stats["loans_created"] += 1

    def _create_loan(self, session, tpl: dict) -> None:
        principal = Decimal(str(
            self.identity_rng.randint(*tpl["principal_range"])
        ))
        rate = round(self.identity_rng.uniform(*tpl["rate_range"]), 4)
        amort_pct = self.identity_rng.uniform(*tpl["amort_pct_range"])
        monthly_amort = (principal * Decimal(str(amort_pct)) / Decimal(12)).quantize(
            Decimal("1.00")
        )
        # Kategori-id
        category = session.query(Category).filter(
            Category.name == tpl["category"]
        ).first()
        loan = Loan(
            name=tpl["name"],
            lender=tpl["lender"],
            principal_amount=principal,
            current_balance_at_creation=principal,
            start_date=date(self.year - self.identity_rng.randint(1, 8), 1, 1),
            interest_rate=rate,
            binding_type=tpl["binding"],
            amortization_monthly=monthly_amort,
            category_id=category.id if category else None,
            active=True,
        )
        session.add(loan)
        session.flush()

    # ---------- Lön ----------

    def _generate_salary(self, session, accounts, stats) -> None:
        employer_name, lo, hi = self.identity_rng.choice(EMPLOYERS)
        # Lön varierar ±3% mellan månader
        base = self.identity_rng.randint(lo, hi)
        variation = self.rng.uniform(-0.03, 0.03)
        amount = round(base * (1 + variation), 0)
        salary_day = self.identity_rng.choice([25, 26, 27])
        salary_date = self._safe_day(salary_day)
        lonekonto_id = accounts.get("checking")
        if lonekonto_id is None:
            return
        self._add_transaction(
            session,
            account_id=lonekonto_id,
            date_=salary_date,
            amount=Decimal(str(amount)),
            description=f"LÖN {employer_name.upper()}",
            category_name="Lön",
            stats_key="transactions_created",
            stats=stats,
            idempotency=("salary", self.year_month, employer_name),
        )

    # ---------- Fakturor (UpcomingTransaction) ----------

    def _generate_upcoming(self, session, accounts, stats) -> None:
        # Identity-rng väljer vilka leverantörer som återkommer varje månad
        # (t.ex. samma elnätsbolag + bredbandsbolag)
        if not hasattr(self, "_chosen_invoice_names"):
            # Markera per-elev-val i stället för per-månad-slump
            self._chosen_invoice_names = self._pick_invoices()

        debit_acc = accounts.get("checking")

        for tpl in self._chosen_invoice_names:
            amount = self.rng.randint(tpl["min"], tpl["max"])
            due_day = self.identity_rng.randint(5, 28)
            due_date = self._safe_day(due_day)
            category = session.query(Category).filter(
                Category.name == tpl["category"]
            ).first()

            # Idempotens: unik identifier per (elev, månad, leverantör)
            existing = (
                session.query(UpcomingTransaction)
                .filter(
                    UpcomingTransaction.name == tpl["name"],
                    UpcomingTransaction.expected_date >= date(self.year, self.month, 1),
                    UpcomingTransaction.expected_date <= date(
                        self.year, self.month, self._last_day
                    ),
                )
                .first()
            )
            if existing:
                continue

            up = UpcomingTransaction(
                kind="bill",
                name=tpl["name"],
                amount=Decimal(str(amount)),
                expected_date=due_date,
                category_id=category.id if category else None,
                recurring_monthly=True,
                source="manual",
                debit_account_id=debit_acc,
                debit_date=due_date,
                autogiro=self.rng.random() < 0.6,
                invoice_number=f"{self.rng.randint(100_000, 999_999)}",
                bankgiro=f"{self.rng.randint(100, 999)}-{self.rng.randint(1000, 9999)}",
            )
            session.add(up)
            session.flush()
            # En rad per faktura
            session.add(UpcomingTransactionLine(
                upcoming_id=up.id,
                description=tpl["name"],
                amount=Decimal(str(amount)),
                category_id=category.id if category else None,
            ))
            stats["upcoming_created"] += 1

    def _pick_invoices(self) -> list[dict]:
        """Välj per-elev: en el-leverantör, en bredband, ev. hyra,
        ev. försäkring, Radiotjänst. Identity-rng så valet är konstant."""
        picks: list[dict] = []
        el = [t for t in INVOICE_TEMPLATES if t.get("meter") == "electricity"]
        bredband = [t for t in INVOICE_TEMPLATES if "Bredband" in t["name"] or "Com Hem" in t["name"]]
        hyra = [t for t in INVOICE_TEMPLATES if "Hyra" in t["name"]]
        forsakring = [t for t in INVOICE_TEMPLATES if t["category"] == "Försäkring"]
        mobil = [t for t in INVOICE_TEMPLATES if "Mobil" in t["name"]]

        picks.append(self.identity_rng.choice(el))
        picks.append(self.identity_rng.choice(bredband))
        if self.identity_rng.random() < 0.7:
            picks.append(self.identity_rng.choice(hyra))
        if self.identity_rng.random() < 0.6:
            picks.append(self.identity_rng.choice(forsakring))
        if self.identity_rng.random() < 0.8:
            picks.append(self.identity_rng.choice(mobil))
        return picks

    # ---------- Transaktioner ----------

    def _generate_transactions(self, session, accounts, stats) -> None:
        lonekonto = accounts.get("checking")
        kreditkort = accounts.get("credit")
        if lonekonto is None:
            return

        n_tx = self.rng.randint(25, 45)
        categories = list(MERCHANTS.keys())

        for i in range(n_tx):
            cat = self.rng.choice(categories)
            merchant_name, lo, hi = self.rng.choice(MERCHANTS[cat])
            amount = -self.rng.randint(lo, hi)
            day = self.rng.randint(1, self._last_day)
            tx_date = self._safe_day(day)

            # Större köp (shopping/restaurang) går på kreditkort ibland
            use_credit = (
                kreditkort is not None
                and cat in ("Shopping", "Restaurang", "Nöje")
                and self.rng.random() < 0.4
            )
            acc_id = kreditkort if use_credit else lonekonto

            cat_row = session.query(Category).filter(Category.name == cat).first()
            self._add_transaction(
                session,
                account_id=acc_id,
                date_=tx_date,
                amount=Decimal(str(amount)),
                description=f"{merchant_name.upper()} {tx_date.strftime('%d/%m')}",
                category_name=cat,
                stats_key="transactions_created",
                stats=stats,
                idempotency=("tx", self.year_month, i),
            )

    # ---------- Utility ----------

    def _generate_utility(self, session, stats) -> None:
        # En el-läsning per månad
        kwh = self.rng.randint(250, 1200)
        cost = Decimal(str(self.rng.randint(400, 1800)))
        period_start = date(self.year, self.month, 1)
        period_end = date(self.year, self.month, self._last_day)
        # Idempotens: unik på (supplier, period_start)
        existing = (
            session.query(UtilityReading)
            .filter(
                UtilityReading.supplier == "demo_elbolag",
                UtilityReading.period_start == period_start,
            )
            .first()
        )
        if existing:
            return
        session.add(UtilityReading(
            supplier="demo_elbolag",
            meter_type="electricity",
            meter_role="total",
            period_start=period_start,
            period_end=period_end,
            consumption=Decimal(str(kwh)),
            consumption_unit="kWh",
            cost_kr=cost,
            source="manual",
        ))
        stats["utility_created"] += 1

    # ---------- Helpers ----------

    def _safe_day(self, day: int) -> date:
        return date(self.year, self.month, min(day, self._last_day))

    def _add_transaction(
        self,
        session,
        *,
        account_id: int,
        date_: date,
        amount: Decimal,
        description: str,
        category_name: str,
        stats_key: str,
        stats: dict,
        idempotency: tuple,
    ) -> None:
        # Stable hash så samma (elev, månad, index) inte dubblar vid overwrite
        h = _hash_str(self.student_id, *idempotency, description, amount)
        existing = (
            session.query(Transaction).filter(Transaction.hash == h).first()
        )
        if existing:
            return
        cat = session.query(Category).filter(
            Category.name == category_name
        ).first()
        tx = Transaction(
            account_id=account_id,
            date=date_,
            amount=amount,
            currency="SEK",
            raw_description=description,
            normalized_merchant=description.split()[0].title(),
            category_id=cat.id if cat else None,
            user_verified=False,
            hash=h,
            ai_confidence=0.9,
        )
        session.add(tx)
        session.flush()
        stats[stats_key] += 1

    def _clear_month(self, session, stats) -> None:
        """Radera all data i aktuell månad (för overwrite). Behåller
        konton och lån."""
        start = date(self.year, self.month, 1)
        end = date(self.year, self.month, self._last_day)
        # Transaktioner
        session.query(Transaction).filter(
            Transaction.date >= start,
            Transaction.date <= end,
        ).delete(synchronize_session=False)
        # Upcoming
        session.query(UpcomingTransaction).filter(
            UpcomingTransaction.expected_date >= start,
            UpcomingTransaction.expected_date <= end,
        ).delete(synchronize_session=False)
        # Utility
        session.query(UtilityReading).filter(
            UtilityReading.period_start == start,
        ).delete(synchronize_session=False)
        session.flush()
