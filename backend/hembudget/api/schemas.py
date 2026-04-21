from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class TransactionSplitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    description: str
    amount: Decimal
    category_id: Optional[int]
    sort_order: int
    source: str


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    date: date
    amount: Decimal
    currency: str
    raw_description: str
    normalized_merchant: Optional[str]
    category_id: Optional[int]
    tags: Optional[list] = None
    notes: Optional[str] = None
    ai_confidence: Optional[float] = None
    user_verified: bool
    is_transfer: bool = False
    transfer_pair_id: Optional[int] = None
    splits: list[TransactionSplitOut] = []


class TransactionUpdate(BaseModel):
    category_id: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[list] = None
    user_verified: Optional[bool] = None
    create_rule: bool = True
    is_transfer: Optional[bool] = None


class TransferLinkIn(BaseModel):
    tx_a_id: int
    tx_b_id: int


class AccountIn(BaseModel):
    name: str
    bank: str
    type: str = "checking"
    currency: str = "SEK"
    account_number: Optional[str] = None
    opening_balance: Optional[Decimal] = None
    opening_balance_date: Optional[date] = None
    pays_credit_account_id: Optional[int] = None


class AccountOut(AccountIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    account_number: Optional[str] = None
    opening_balance: Optional[Decimal] = None
    opening_balance_date: Optional[date] = None
    pays_credit_account_id: Optional[int] = None


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    parent_id: Optional[int]
    budget_monthly: Optional[Decimal]
    color: Optional[str]
    icon: Optional[str]


class CategoryIn(BaseModel):
    name: str
    parent_id: Optional[int] = None
    color: Optional[str] = None
    icon: Optional[str] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[int] = None
    color: Optional[str] = None
    icon: Optional[str] = None
    budget_monthly: Optional[Decimal] = None


class BudgetIn(BaseModel):
    month: str
    category_id: int
    planned_amount: Decimal


class ChatMessageIn(BaseModel):
    session_id: str
    content: str


class ScenarioIn(BaseModel):
    name: str
    kind: str
    params: dict[str, Any]


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    kind: str
    params: dict
    result: Optional[dict]
    created_at: datetime


class LoginIn(BaseModel):
    password: str


class LoginOut(BaseModel):
    token: str
    initialized: bool
