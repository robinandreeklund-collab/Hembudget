"""End-to-end test för TransferDetector mot en äkta in-memory SQLite."""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hembudget.db.models import Account, Base, Transaction
from hembudget.transfers.detector import TransferDetector


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _tx(session, account_id, d, amount, desc, **kw) -> Transaction:
    t = Transaction(
        account_id=account_id,
        date=d,
        amount=Decimal(str(amount)),
        currency="SEK",
        raw_description=desc,
        hash=f"{account_id}-{d}-{amount}-{desc}",
        **kw,
    )
    session.add(t)
    session.flush()
    return t


def _acc(session, name, bank, type_) -> Account:
    a = Account(name=name, bank=bank, type=type_)
    session.add(a)
    session.flush()
    return a


def test_amex_payment_from_nordea_marked_and_paired(session):
    nordea = _acc(session, "Nordea", "nordea", "checking")
    amex = _acc(session, "Amex Eurobonus", "amex", "credit")

    # Betalningen från Nordea till Amex
    payment = _tx(session, nordea.id, date(2026, 3, 25), -15000, "AMEX AUTOGIRO")
    # Återbetalningen på Amex-kontot (positivt belopp)
    repayment = _tx(session, amex.id, date(2026, 3, 26), 15000, "AMEX ÅTERBETALNING TACK")
    # En äkta utgift på Amex som inte ska påverkas
    purchase = _tx(session, amex.id, date(2026, 3, 10), -542.50, "ICA NÄRA STOCKHOLM")

    result = TransferDetector(session).detect_and_link([payment, repayment, purchase])

    assert result.marked == 1   # bara betalningen markeras direkt
    assert result.paired == 1   # återbetalningen paras ihop
    session.refresh(payment); session.refresh(repayment); session.refresh(purchase)

    assert payment.is_transfer is True
    assert payment.transfer_pair_id == repayment.id
    assert repayment.is_transfer is True
    assert repayment.transfer_pair_id == payment.id
    assert purchase.is_transfer is False  # äkta utgifter lämnas ifred


def test_seb_kort_variants_match(session):
    nordea = _acc(session, "Nordea", "nordea", "checking")
    seb = _acc(session, "SEB Kort", "seb_kort", "credit")

    p1 = _tx(session, nordea.id, date(2026, 3, 28), -4500, "SEBKORT AUTOGIRO")
    p2 = _tx(session, nordea.id, date(2026, 4, 28), -5200, "SEB MASTERCARD")

    result = TransferDetector(session).detect_and_link([p1, p2])

    assert result.marked == 2
    session.refresh(p1); session.refresh(p2)
    assert p1.is_transfer is True
    assert p2.is_transfer is True


def test_no_match_without_credit_account(session):
    nordea = _acc(session, "Nordea", "nordea", "checking")
    # Ingen Amex-konto upplagt
    payment = _tx(session, nordea.id, date(2026, 3, 25), -15000, "AMEX AUTOGIRO")

    result = TransferDetector(session).detect_and_link([payment])

    session.refresh(payment)
    assert result.marked == 1                     # fortfarande markerad som transfer
    assert result.paired == 0                     # men ingen att para med
    assert payment.is_transfer is True
    assert payment.transfer_pair_id is None


def test_positive_transactions_not_flagged(session):
    nordea = _acc(session, "Nordea", "nordea", "checking")
    amex = _acc(session, "Amex", "amex", "credit")

    # Lön — ska inte markeras
    salary = _tx(session, nordea.id, date(2026, 3, 25), 30000, "Lön mars")

    result = TransferDetector(session).detect_and_link([salary])

    assert result.marked == 0
    session.refresh(salary)
    assert salary.is_transfer is False


def test_amount_tolerance(session):
    nordea = _acc(session, "Nordea", "nordea", "checking")
    amex = _acc(session, "Amex", "amex", "credit")

    # Belopp skiljer 1 % — inom tolerans
    payment = _tx(session, nordea.id, date(2026, 3, 25), -15000, "AMEX AUTOGIRO")
    repayment = _tx(session, amex.id, date(2026, 3, 26), 14850, "AMEX INBETALNING")

    result = TransferDetector(session).detect_and_link([payment, repayment])

    assert result.paired == 1


def test_manual_link_and_unlink(session):
    nordea = _acc(session, "Nordea", "nordea", "checking")
    savings = _acc(session, "Sparkonto", "nordea", "savings")

    out = _tx(session, nordea.id, date(2026, 3, 25), -5000, "Till sparkonto")
    inn = _tx(session, savings.id, date(2026, 3, 25), 5000, "Insättning")

    det = TransferDetector(session)
    det.link_manual(out.id, inn.id)
    session.refresh(out); session.refresh(inn)
    assert out.is_transfer and out.transfer_pair_id == inn.id
    assert inn.is_transfer and inn.transfer_pair_id == out.id

    det.unlink(out.id)
    session.refresh(out); session.refresh(inn)
    assert out.is_transfer is False and out.transfer_pair_id is None
    assert inn.is_transfer is False and inn.transfer_pair_id is None


def test_internal_transfer_same_day_pairs(session):
    lon = _acc(session, "Lönekonto", "nordea", "checking")
    gem = _acc(session, "Gemensamt", "nordea", "checking")

    out = _tx(session, lon.id, date(2026, 3, 25), -15000, "Till gemensamt")
    inn = _tx(session, gem.id, date(2026, 3, 25), 15000, "Från Robin")

    r = TransferDetector(session).detect_internal_transfers()

    assert r.pairs == 1
    assert r.ambiguous == 0
    assert out.is_transfer and inn.is_transfer
    assert out.transfer_pair_id == inn.id
    assert inn.transfer_pair_id == out.id
    assert out.category_id is None


def test_internal_transfer_date_tolerance(session):
    a = _acc(session, "A", "nordea", "checking")
    b = _acc(session, "B", "nordea", "savings")

    out = _tx(session, a.id, date(2026, 3, 25), -5000, "Överföring")
    # 2 dagars fördröjning — ska fortfarande paras
    inn = _tx(session, b.id, date(2026, 3, 27), 5000, "Insättning")

    r = TransferDetector(session).detect_internal_transfers()
    assert r.pairs == 1


def test_internal_transfer_skips_ambiguous(session):
    a = _acc(session, "A", "nordea", "checking")
    b = _acc(session, "B", "nordea", "savings")
    c = _acc(session, "C", "nordea", "savings")

    out = _tx(session, a.id, date(2026, 3, 25), -5000, "Överföring")
    # Två möjliga destinationer, ingen på exakt samma dag → tvetydigt
    inn1 = _tx(session, b.id, date(2026, 3, 26), 5000, "Insättning")
    inn2 = _tx(session, c.id, date(2026, 3, 26), 5000, "Insättning")

    r = TransferDetector(session).detect_internal_transfers()
    assert r.pairs == 0
    assert r.ambiguous == 1
    assert out.is_transfer is False


def test_internal_transfer_same_day_disambiguates(session):
    a = _acc(session, "A", "nordea", "checking")
    b = _acc(session, "B", "nordea", "savings")
    c = _acc(session, "C", "nordea", "savings")

    out = _tx(session, a.id, date(2026, 3, 25), -5000, "Överföring")
    inn1 = _tx(session, b.id, date(2026, 3, 25), 5000, "Samma dag — denna")  # vinner
    inn2 = _tx(session, c.id, date(2026, 3, 27), 5000, "2 dagar bort")

    r = TransferDetector(session).detect_internal_transfers()
    assert r.pairs == 1
    assert out.transfer_pair_id == inn1.id
    assert inn2.is_transfer is False


def test_internal_transfer_one_to_one_pairing_for_identical_amounts(session):
    """Regression för användarklagomål: två swishar samma dag, samma belopp,
    till gemensamma kontot ska paras ihop 1:1 istället för att markeras
    som tvetydiga och hoppas över."""
    lon = _acc(session, "Lönekonto", "nordea", "checking")
    gem = _acc(session, "Gemensamt", "nordea", "checking")

    out1 = _tx(session, lon.id, date(2026, 3, 25), -5000, "Överföring 1")
    out2 = _tx(session, lon.id, date(2026, 3, 25), -5000, "Överföring 2")
    inn1 = _tx(session, gem.id, date(2026, 3, 25), 5000, "Insättning 1")
    inn2 = _tx(session, gem.id, date(2026, 3, 25), 5000, "Insättning 2")

    r = TransferDetector(session).detect_internal_transfers()

    # Båda sourcer paras ihop i tur och ordning
    assert r.pairs == 2
    assert r.ambiguous == 0
    session.refresh(out1); session.refresh(out2)
    session.refresh(inn1); session.refresh(inn2)
    assert all(tx.is_transfer for tx in (out1, out2, inn1, inn2))
    # Verifiera att varje har en parning
    assert out1.transfer_pair_id in (inn1.id, inn2.id)
    assert out2.transfer_pair_id in (inn1.id, inn2.id)
    assert out1.transfer_pair_id != out2.transfer_pair_id


def test_internal_transfer_no_match_amount_off(session):
    a = _acc(session, "A", "nordea", "checking")
    b = _acc(session, "B", "nordea", "savings")

    out = _tx(session, a.id, date(2026, 3, 25), -5000, "Överföring")
    inn = _tx(session, b.id, date(2026, 3, 25), 4500, "Annat belopp")  # 10 % off

    r = TransferDetector(session).detect_internal_transfers()
    assert r.pairs == 0
    assert out.is_transfer is False


def test_internal_transfer_pairs_generic_marked(session):
    """Regression: a row that the generic-pattern pass flagged as transfer
    (e.g. 'Överföring 3435 20 01910' on Nordea) must still be pairable with
    its matching destination in detect_internal_transfers()."""
    lon = _acc(session, "Lönekonto", "nordea", "checking")
    gem = _acc(session, "Gemensamt", "nordea", "checking")

    src = _tx(session, lon.id, date(2026, 3, 25), -10000, "Överföring 3435 20 01910")
    dst = _tx(session, gem.id, date(2026, 3, 25), 10000, "Insättning")

    # First pass: generic pattern flags src as transfer but without a pair
    r1 = TransferDetector(session).detect_and_link([src, dst])
    assert src.is_transfer is True
    assert src.transfer_pair_id is None   # unpaired
    assert dst.is_transfer is False        # not matched by generic pattern

    # Second pass: internal matching should now pair them
    r2 = TransferDetector(session).detect_internal_transfers()
    assert r2.pairs == 1
    assert src.transfer_pair_id == dst.id
    assert dst.is_transfer is True
    assert dst.transfer_pair_id == src.id


def test_internal_transfer_skips_already_paired(session):
    a = _acc(session, "A", "nordea", "checking")
    b = _acc(session, "B", "nordea", "savings")
    c = _acc(session, "C", "nordea", "savings")

    # Redan paret paired — ska inte röras
    out = _tx(session, a.id, date(2026, 3, 25), -5000, "Överföring", is_transfer=True)
    done = _tx(session, b.id, date(2026, 3, 25), 5000, "Redan länkad", is_transfer=True)
    out.transfer_pair_id = done.id
    done.transfer_pair_id = out.id
    session.flush()

    # En kandidat på ett tredje konto — ska INTE få paras med den redan-länkade
    other = _tx(session, c.id, date(2026, 3, 25), 5000, "Annan")

    r = TransferDetector(session).detect_internal_transfers()
    assert r.pairs == 0
    assert other.is_transfer is False
    assert out.transfer_pair_id == done.id   # oförändrat


def test_generic_transfer_pattern_marks_but_doesnt_pair(session):
    nordea = _acc(session, "Nordea", "nordea", "checking")
    savings = _acc(session, "Sparkonto", "nordea", "savings")

    tx = _tx(session, nordea.id, date(2026, 3, 25), -5000, "Överföring till sparkonto")

    result = TransferDetector(session).detect_and_link([tx])

    session.refresh(tx)
    assert result.marked == 1
    assert result.paired == 0
    assert tx.is_transfer is True
    assert tx.category_id is None
