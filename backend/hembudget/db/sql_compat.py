"""SQL-dialekthelpers — abstrakterar funktioner som skiljer mellan
SQLite (lokalt + tester) och Postgres (prod via Cloud SQL).

Bakgrund: en lång rad endpoints och services använde func.strftime som
bara fungerar på SQLite. På Postgres returnerade dom tom lista och
Dashboard, prognoser, månadsbudgetar m.m. visade 'ingen data'. Den
här modulen ger ett dialektagnostiskt sätt att uttrycka 'YYYY-MM-
strängen för en datumkolumn'.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session


def month_str(session: Session, date_col: Any) -> Any:
    """Returnera ett SQLAlchemy-uttryck som ger 'YYYY-MM'-strängen för
    `date_col` på den dialekt som `session` är bunden till.

    Användning:
        month_expr = month_str(s, Transaction.date)
        s.query(month_expr.label("m"), func.count())
         .group_by(month_expr).order_by(month_expr).all()
    """
    dialect = session.bind.dialect.name if session.bind else "sqlite"
    if dialect == "postgresql":
        return func.to_char(date_col, "YYYY-MM")
    # SQLite (default): strftime
    return func.strftime("%Y-%m", date_col)
