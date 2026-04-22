"""Logique pure des corporate actions (splits, dividendes, M&A, etc.)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Optional


ActionType = Literal[
    "SPLIT", "REVERSE_SPLIT", "DIVIDEND", "SPINOFF",
    "MERGER_CASH", "MERGER_STOCK", "DELISTING", "SUSPENSION",
]
Side = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class Position:
    ticker: str
    side: Side
    shares: float
    entry_price: float
    entry_date: date


@dataclass(frozen=True)
class CorporateEvent:
    ticker: str
    action_type: ActionType
    effective_date: date
    details: dict


@dataclass(frozen=True)
class ActionResult:
    new_position: Optional[Position]
    cash_delta: float
    log_entry: dict
    warning: Optional[str] = None


def apply_split(position: Position, event: CorporateEvent) -> ActionResult:
    """Ajuste shares/entry_price selon ratio_new/ratio_old. NAV préservé."""
    raise NotImplementedError


def apply_dividend(position: Position, event: CorporateEvent) -> ActionResult:
    """Crédit LONG / débit SHORT du cash. Fallback ADR si ex_date null."""
    raise NotImplementedError


def apply_delisting(position: Position, event: CorporateEvent) -> ActionResult:
    """Liquide au last_price ; new_position=None."""
    raise NotImplementedError


def apply_spinoff(position: Position, event: CorporateEvent) -> ActionResult:
    """Policy: liquidation totale. action='CORPORATE_ACTION_LIQUIDATION',
    details.corporate_action_type='SPINOFF'.
    """
    raise NotImplementedError


def apply_merger(position: Position, event: CorporateEvent) -> ActionResult:
    """MERGER_CASH ferme au prix annoncé ; MERGER_STOCK convertit ou liquide."""
    raise NotImplementedError


def apply_suspension(position: Position, event: CorporateEvent) -> ActionResult:
    """SUSPENSION_START / SUSPENSION_END uniquement. nav.py gère le freeze
    via last_known_price (contrat documenté dans nav.py).
    """
    raise NotImplementedError


def apply_event(position: Position, event: CorporateEvent) -> ActionResult:
    """Dispatcher central."""
    raise NotImplementedError


def resolve_effective_date(event: CorporateEvent) -> tuple[date, Optional[str]]:
    """Retourne (date_applicable, warning_ou_None). Fallback ADR : ex_date null
    → payment_date - 1 business day, warning='EX_DATE_MISSING'.
    """
    raise NotImplementedError
