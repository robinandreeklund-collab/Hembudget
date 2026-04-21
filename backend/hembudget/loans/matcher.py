"""Matcha transaktioner mot registrerade lån.

Tre nivåer:
1. Schemabaserad matchning (PRIMÄR) — användaren har lagt in planerade
   betalningar med exakt datum och belopp. Vi parar ihop en kommande
   transaktion som matchar (±3 dagar, ±1 kr). Nästan aldrig fel.
2. `match_pattern` — fritextsträng på låneposten som matchas mot
   transaktionens beskrivning (case-insensitivt).
3. Klassificering — när en transaktion matchar ett lån (inte via schema),
   avgör vi om det är ränta eller amortering via nyckelord.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from ..db.models import Category, Loan, LoanPayment, LoanScheduleEntry, Transaction

log = logging.getLogger(__name__)


INTEREST_KEYWORDS = (
    "ränta",
    "bolåneränta",
    "räntebetalning",
    "kreditavgift",
    "interest",
)

AMORTIZATION_KEYWORDS = (
    "amort",          # matchar amortering, amort
    "amortisation",
    "amortization",
    "kapital",        # "kapitalbelopp" används ibland
)


def _shift_month(base, months: int, day_of_month: int):
    from datetime import date as _date
    import calendar
    m = base.month - 1 + months
    year = base.year + m // 12
    month = m % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(day_of_month, last_day)
    return _date(year, month, day)


def classify_payment(description: str) -> str | None:
    """Return 'interest', 'amortization', or None if unclear."""
    s = (description or "").lower()
    for kw in AMORTIZATION_KEYWORDS:
        if kw in s:
            return "amortization"
    for kw in INTEREST_KEYWORDS:
        if kw in s:
            return "interest"
    return None


@dataclass
class LoanLinkResult:
    linked: int
    unclassified: int      # matchade lån men vi kunde inte avgöra ränta/amort
    matched_via_schedule: int = 0
    matched_via_pattern: int = 0


class LoanMatcher:
    # Matchningstolerans för schema-baserad koppling
    SCHEDULE_DATE_TOLERANCE_DAYS = 5
    SCHEDULE_AMOUNT_TOLERANCE = Decimal("1.00")   # ±1 kr

    def __init__(self, session: Session):
        self.session = session

    def match_and_classify(self, transactions: list[Transaction]) -> LoanLinkResult:
        loans: list[Loan] = (
            self.session.query(Loan).filter(Loan.active.is_(True)).all()
        )
        if not loans:
            return LoanLinkResult(0, 0)

        category_interest = self._category_id("Bolåneränta")
        category_amort = self._category_id("Amortering")

        # Fas 1: schema-baserad matchning. Exakt belopp + nära datum räcker —
        # behöver inte ens textmönstret stämma.
        via_schedule = self._match_via_schedule(
            transactions, category_interest, category_amort
        )

        linked = via_schedule
        unclassified = 0
        via_pattern = 0

        # Fas 2: pattern-baserad fallback för rader som schedulen inte täckte
        for tx in transactions:
            if tx.amount >= 0 or tx.is_transfer:
                continue
            if self._already_linked(tx.id):
                continue
            loan = self._find_loan(loans, tx)
            if loan is None:
                continue
            ptype = classify_payment(tx.raw_description)
            if ptype is None:
                unclassified += 1
                continue
            self.session.add(
                LoanPayment(
                    loan_id=loan.id,
                    transaction_id=tx.id,
                    date=tx.date,
                    amount=-tx.amount,
                    payment_type=ptype,
                )
            )
            if ptype == "interest" and category_interest is not None:
                tx.category_id = category_interest
            elif ptype == "amortization" and category_amort is not None:
                tx.category_id = category_amort
            linked += 1
            via_pattern += 1

        if linked > 0:
            self.session.flush()
        return LoanLinkResult(
            linked=linked,
            unclassified=unclassified,
            matched_via_schedule=via_schedule,
            matched_via_pattern=via_pattern,
        )

    def _match_via_schedule(
        self,
        transactions: list[Transaction],
        category_interest: int | None,
        category_amort: int | None,
    ) -> int:
        """Para transaktioner med planerade schema-rader.

        Två nivåer:
        a) Enskild rad: exakt belopp + datum (traditionellt).
        b) **Kombinerad betalning:** om en bankrad matchar SUMMAN av flera
           schema-rader för samma (loan_id, due_date) — typ Nordeas
           "Omsättning lån" som dras i ETT svep om 4 662 kr men schemat
           har amortering 2 700 + ränta 1 962 = 4 662. Då parar vi
           bankraden mot ALLA schema-raderna och skapar en LoanPayment
           per typ.
        """
        open_entries: list[LoanScheduleEntry] = (
            self.session.query(LoanScheduleEntry)
            .filter(LoanScheduleEntry.matched_transaction_id.is_(None))
            .all()
        )
        if not open_entries:
            return 0

        matched = 0
        for tx in transactions:
            # OBS: is_transfer-flaggan ignoreras här med flit — LoanMatcher
            # körs före transfer-detektorn så flaggan är inte satt än, och
            # en rad som matchas mot lånet ska inte senare bli transfer.
            if tx.amount >= 0:
                continue
            if self._already_linked(tx.id):
                continue
            abs_amount = -tx.amount

            # a) Enskild rad
            singles = [
                e for e in open_entries
                if e.matched_transaction_id is None
                and abs(e.amount - abs_amount) <= self.SCHEDULE_AMOUNT_TOLERANCE
                and abs((e.due_date - tx.date).days) <= self.SCHEDULE_DATE_TOLERANCE_DAYS
            ]
            if singles:
                singles.sort(key=lambda e: abs((e.due_date - tx.date).days))
                entry = singles[0]
                self._link_schedule_entry(
                    entry, tx, abs_amount, category_interest, category_amort,
                )
                matched += 1
                continue

            # b) Kombinerad betalning: hitta (loan_id, due_date)-grupp vars
            #    summa matchar abs_amount inom toleransen
            buckets: dict[tuple[int, "date"], list[LoanScheduleEntry]] = {}
            for e in open_entries:
                if e.matched_transaction_id is not None:
                    continue
                if abs((e.due_date - tx.date).days) > self.SCHEDULE_DATE_TOLERANCE_DAYS:
                    continue
                buckets.setdefault((e.loan_id, e.due_date), []).append(e)

            best_bucket = None
            best_key = None
            for key, entries in buckets.items():
                if len(entries) < 2:
                    continue
                total = sum((e.amount for e in entries), Decimal("0"))
                if abs(total - abs_amount) <= self.SCHEDULE_AMOUNT_TOLERANCE:
                    # Välj det bucket vars due_date ligger närmast tx.date
                    due_date = key[1]
                    score = abs((due_date - tx.date).days)
                    if best_bucket is None or score < abs(
                        (best_key[1] - tx.date).days
                    ):
                        best_bucket = entries
                        best_key = key

            if best_bucket is not None:
                for entry in best_bucket:
                    self._link_schedule_entry(
                        entry, tx, entry.amount,
                        category_interest, category_amort,
                    )
                # Kategorin på själva transaktionen: om både amort + ränta
                # finns, välj amortering (oftare större belopp, tydligare
                # signal att det är en lånebetalning totalt sett).
                types = {e.payment_type for e in best_bucket}
                if "amortization" in types and category_amort is not None:
                    tx.category_id = category_amort
                elif "interest" in types and category_interest is not None:
                    tx.category_id = category_interest
                matched += 1

        if matched:
            self.session.flush()
        return matched

    def _link_schedule_entry(
        self,
        entry: LoanScheduleEntry,
        tx: Transaction,
        pay_amount: Decimal,
        category_interest: int | None,
        category_amort: int | None,
    ) -> None:
        """Koppla en schema-rad till en transaktion + skapa LoanPayment."""
        entry.matched_transaction_id = tx.id
        entry.matched_at = datetime.utcnow()
        self.session.add(
            LoanPayment(
                loan_id=entry.loan_id,
                transaction_id=tx.id,
                date=tx.date,
                amount=pay_amount,
                payment_type=entry.payment_type,
            )
        )
        # Sätt kategori endast om det är en single-row-match (kombo-fallet
        # hanteras av anroparen efter att alla raderna länkats)
        if entry.payment_type == "interest" and category_interest is not None:
            if tx.category_id is None:
                tx.category_id = category_interest
        elif entry.payment_type == "amortization" and category_amort is not None:
            if tx.category_id is None:
                tx.category_id = category_amort

    def generate_schedule(
        self,
        loan: Loan,
        months: int = 3,
        day_of_month: int | None = None,
    ) -> list[LoanScheduleEntry]:
        """Projicera framtida schema-rader baserat på lånets villkor.
        Genererar två rader per månad: ränta + amortering.
        """
        if day_of_month is None:
            # Gissa senaste rampdag från befintliga betalningar, annars 25:e
            last = (
                self.session.query(LoanPayment)
                .filter(LoanPayment.loan_id == loan.id)
                .order_by(LoanPayment.date.desc())
                .first()
            )
            day_of_month = last.date.day if last else 25

        entries: list[LoanScheduleEntry] = []
        today = datetime.utcnow().date()
        balance = self.outstanding_balance(loan)
        monthly_rate = Decimal(str(loan.interest_rate)) / Decimal("12")

        for i in range(1, months + 1):
            due = _shift_month(today, i, day_of_month)
            interest_amt = (balance * monthly_rate).quantize(Decimal("0.01"))
            amort_amt = loan.amortization_monthly or Decimal("0")

            if interest_amt > 0:
                entries.append(LoanScheduleEntry(
                    loan_id=loan.id, due_date=due,
                    amount=interest_amt, payment_type="interest",
                ))
            if amort_amt and amort_amt > 0:
                entries.append(LoanScheduleEntry(
                    loan_id=loan.id, due_date=due,
                    amount=amort_amt, payment_type="amortization",
                ))
                balance -= amort_amt  # simulera nedräkning

        for e in entries:
            self.session.add(e)
        self.session.flush()
        return entries

    def outstanding_balance(self, loan: Loan) -> Decimal:
        """Aktuellt lånesaldo.

        Om current_balance_at_creation är satt (från bankens egna siffra via
        vision) används det som utgångspunkt och endast amorteringar EFTER
        det datumet dras av. Annars fallback till principal − alla
        matchade amorteringar (bakåtkompatibelt).
        """
        if loan.current_balance_at_creation is not None:
            base = loan.current_balance_at_creation
            cutoff = loan.created_at.date() if loan.created_at else loan.start_date
            rows = (
                self.session.query(LoanPayment)
                .filter(
                    LoanPayment.loan_id == loan.id,
                    LoanPayment.payment_type == "amortization",
                    LoanPayment.date > cutoff,
                )
                .all()
            )
        else:
            base = loan.principal_amount
            rows = (
                self.session.query(LoanPayment)
                .filter(
                    LoanPayment.loan_id == loan.id,
                    LoanPayment.payment_type == "amortization",
                    LoanPayment.date >= loan.start_date,
                )
                .all()
            )
        amortized = sum((p.amount for p in rows), Decimal("0"))
        return (base - amortized).quantize(Decimal("0.01"))

    def total_interest_paid(self, loan: Loan) -> Decimal:
        """Total betald ränta från två källor:
        1. Matchade bankbetalningar (LoanPayment) — säkraste signalen.
        2. Historiska, omatchade schemaposter i förflutet — representerar
           betalningar som banken bekräftat genom sin Transaktioner-vy men
           som användaren ännu inte importerat CSV för. När CSV:n kommer
           och matchern paras ihop får schemaposten matched_transaction_id
           satt och utesluts ur denna summering (medan en ny LoanPayment
           tas med istället — ingen dubbelräkning).
        """
        from datetime import date as _date

        from_payments: Decimal = sum(
            (
                p.amount
                for p in self.session.query(LoanPayment)
                .filter(
                    LoanPayment.loan_id == loan.id,
                    LoanPayment.payment_type == "interest",
                )
                .all()
            ),
            Decimal("0"),
        )

        today = _date.today()
        from_schedule: Decimal = sum(
            (
                e.amount
                for e in self.session.query(LoanScheduleEntry)
                .filter(
                    LoanScheduleEntry.loan_id == loan.id,
                    LoanScheduleEntry.payment_type == "interest",
                    LoanScheduleEntry.due_date < today,
                    LoanScheduleEntry.matched_transaction_id.is_(None),
                )
                .all()
            ),
            Decimal("0"),
        )
        return (from_payments + from_schedule).quantize(Decimal("0.01"))

    def _category_id(self, name: str) -> int | None:
        c = self.session.query(Category).filter(Category.name == name).first()
        return c.id if c else None

    def _find_loan(self, loans: list[Loan], tx: Transaction) -> Loan | None:
        """match_pattern kan vara flera alternativ separerade med '|'.
        Vi matchar case-insensitivt om NÅGOT av mönstren finns i beskrivningen."""
        desc = (tx.raw_description or "").lower()
        for loan in loans:
            if not loan.match_pattern:
                continue
            patterns = [p.strip().lower() for p in loan.match_pattern.split("|") if p.strip()]
            for p in patterns:
                if p in desc:
                    return loan
        return None

    def _already_linked(self, tx_id: int) -> bool:
        return (
            self.session.query(LoanPayment)
            .filter(LoanPayment.transaction_id == tx_id)
            .first()
            is not None
        )
