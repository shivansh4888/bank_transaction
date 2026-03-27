"""
engine.py — Transaction reconciliation engine.
Matches ledger entries against bank/settlement entries and flags gaps.
"""

from decimal import Decimal
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import date

AMOUNT_TOLERANCE = Decimal("0.05")  # minor rounding gap threshold
SLA_DAYS = 3                        # days before a pending txn is AGED_OUT


@dataclass
class LedgerEntry:
    txn_id: str
    date: date
    description: str
    amount: Decimal


@dataclass
class SettlementEntry:
    txn_id: str
    date: date
    description: str
    amount: Decimal
    is_refund: bool = False
    parent_txn_id: Optional[str] = None  # for orphan refund check


@dataclass
class MatchResult:
    txn_id: str
    ledger_amount: Optional[Decimal]
    settled_amount: Optional[Decimal]
    status: str          # MATCHED | MATCHED_WITH_NOTE | DISPUTED | AGED_OUT | DUPLICATE | ORPHAN_REFUND
    note: str = ""
    ledger_date: Optional[date] = None
    settled_date: Optional[date] = None
    description: str = ""


def reconcile(
    ledger: List[LedgerEntry],
    settlements: List[SettlementEntry],
    close_date: date,
) -> dict:
    """
    Run the full reconciliation and return a results dict with:
      - transactions: List[MatchResult]
      - summary: dict of counts and totals
    """
    results: List[MatchResult] = []
    seen_ledger_ids: set = set()
    seen_settled_ids: set = set()
    matched_ids: set = set()

    # Build lookup maps
    ledger_map: dict = {}
    for entry in ledger:
        # Idempotency gate — reject duplicate TXN IDs in ledger
        if entry.txn_id in ledger_map:
            results.append(MatchResult(
                txn_id=entry.txn_id,
                ledger_amount=entry.amount,
                settled_amount=None,
                status="DUPLICATE",
                note="Duplicate TXN-ID in ledger; second occurrence rejected.",
                ledger_date=entry.date,
                description=entry.description,
            ))
            continue
        ledger_map[entry.txn_id] = entry

    settlement_map: dict = {}
    for entry in settlements:
        if entry.txn_id in settlement_map:
            results.append(MatchResult(
                txn_id=entry.txn_id,
                ledger_amount=None,
                settled_amount=entry.amount,
                status="DUPLICATE",
                note="Duplicate TXN-ID in bank statement; second occurrence rejected.",
                settled_date=entry.date,
                description=entry.description,
            ))
            continue
        settlement_map[entry.txn_id] = entry

    # Match ledger → settlement
    for txn_id, l in ledger_map.items():
        s = settlement_map.get(txn_id)

        if s is None:
            # No bank entry found — check SLA
            days_open = (close_date - l.date).days
            if days_open > SLA_DAYS:
                status = "AGED_OUT"
                note = f"No bank entry found. {days_open} days past close date (SLA={SLA_DAYS})."
            else:
                status = "AGED_OUT"
                note = f"No bank entry found within SLA window ({days_open} days)."
            results.append(MatchResult(
                txn_id=txn_id,
                ledger_amount=l.amount,
                settled_amount=None,
                status=status,
                note=note,
                ledger_date=l.date,
                description=l.description,
            ))
        else:
            matched_ids.add(txn_id)
            gap = abs(l.amount - s.amount)
            if gap > AMOUNT_TOLERANCE:
                status = "DISPUTED"
                note = f"Amount gap ${gap:.2f} exceeds tolerance ${AMOUNT_TOLERANCE}."
            elif gap > Decimal("0"):
                status = "MATCHED_WITH_NOTE"
                note = f"Minor rounding gap of ${gap:.2f} (within tolerance). Will accumulate."
            else:
                status = "MATCHED"
                note = ""
            results.append(MatchResult(
                txn_id=txn_id,
                ledger_amount=l.amount,
                settled_amount=s.amount,
                status=status,
                note=note,
                ledger_date=l.date,
                settled_date=s.date,
                description=l.description,
            ))

    # Orphan refunds — settlement entries with no ledger counterpart
    for txn_id, s in settlement_map.items():
        if txn_id not in matched_ids:
            if s.is_refund:
                # Check if parent is in matched set
                parent_ok = s.parent_txn_id in matched_ids if s.parent_txn_id else False
                note = (
                    "Refund parent is matched." if parent_ok
                    else "Orphan refund — parent TXN not found in matched set."
                )
                status = "ORPHAN_REFUND" if not parent_ok else "MATCHED"
            else:
                status = "ORPHAN_REFUND"
                note = "Bank entry has no corresponding ledger record."
            results.append(MatchResult(
                txn_id=txn_id,
                ledger_amount=None,
                settled_amount=s.amount,
                status=status,
                note=note,
                settled_date=s.date,
                description=s.description,
            ))

    # Sum check — total ledger vs total settled (among matched)
    total_ledger = sum(
        r.ledger_amount for r in results
        if r.ledger_amount is not None and r.status in ("MATCHED", "MATCHED_WITH_NOTE")
    )
    total_settled = sum(
        r.settled_amount for r in results
        if r.settled_amount is not None and r.status in ("MATCHED", "MATCHED_WITH_NOTE")
    )
    sum_gap = abs(total_ledger - total_settled)

    # Build summary
    status_counts = {}
    for r in results:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1

    summary = {
        "total_transactions": len(results),
        "status_counts": status_counts,
        "total_ledger_matched": total_ledger,
        "total_settled_matched": total_settled,
        "sum_gap": sum_gap,
        "sum_check_passed": sum_gap <= AMOUNT_TOLERANCE,
    }

    return {"transactions": results, "summary": summary}
