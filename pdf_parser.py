"""
pdf_parser.py — PDF ingestion layer.
Reads a transaction PDF, finds the table, maps flexible column names,
and returns LedgerEntry / SettlementEntry objects the engine can consume.
Uses pdfplumber for reliable table extraction.
"""

import pdfplumber
import pandas as pd
from decimal import Decimal, InvalidOperation
from datetime import date, datetime
from typing import List, Optional
from engine import LedgerEntry, SettlementEntry


# Flexible column name mappings (lowercase aliases → canonical name)
COLUMN_ALIASES = {
    "txn_id":      ["txn_id", "transaction_id", "txnid", "ref", "reference", "id", "trans id", "txn id"],
    "date":        ["date", "txn_date", "transaction_date", "value_date", "trans date"],
    "description": ["description", "desc", "narration", "details", "particulars", "remarks"],
    "amount":      ["amount", "amt", "value", "debit", "credit", "net amount", "transaction amount"],
    "is_refund":   ["is_refund", "refund", "type", "credit/debit"],
    "parent_txn_id": ["parent_txn_id", "parent_id", "original_txn", "ref_txn"],
}


def _find_column(df_columns: List[str], aliases: List[str]) -> Optional[str]:
    """Find the first matching column name (case-insensitive)."""
    lower_cols = {c.lower().strip(): c for c in df_columns}
    for alias in aliases:
        if alias in lower_cols:
            return lower_cols[alias]
    return None


def _parse_amount(value) -> Optional[Decimal]:
    """Convert messy amount strings like '$1,234.56' to Decimal."""
    if value is None:
        return None
    cleaned = str(value).replace(",", "").replace("$", "").replace(" ", "").strip()
    # Handle brackets as negative: (100.00) → -100.00
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_date(value) -> Optional[date]:
    """Try common date formats."""
    if value is None:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d %b %Y", "%b %d %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _extract_dataframe(pdf_path: str) -> pd.DataFrame:
    """Extract all tables from a PDF and combine into one DataFrame."""
    all_rows = []
    headers = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                if not table or len(table) < 2:
                    continue
                if headers is None:
                    headers = [str(h).strip() if h else f"col_{i}" for i, h in enumerate(table[0])]
                    all_rows.extend(table[1:])
                else:
                    # Skip header row if repeated
                    first_row = [str(c).strip().lower() if c else "" for c in table[0]]
                    if first_row == [h.lower() for h in headers]:
                        all_rows.extend(table[1:])
                    else:
                        all_rows.extend(table)

    if not headers or not all_rows:
        raise ValueError(f"No transaction table found in PDF: {pdf_path}")

    df = pd.DataFrame(all_rows, columns=headers)
    df.dropna(how="all", inplace=True)
    return df


def parse_ledger(pdf_path: str) -> List[LedgerEntry]:
    """Parse a ledger PDF and return LedgerEntry objects."""
    df = _extract_dataframe(pdf_path)
    cols = df.columns.tolist()

    txn_col  = _find_column(cols, COLUMN_ALIASES["txn_id"])
    date_col = _find_column(cols, COLUMN_ALIASES["date"])
    desc_col = _find_column(cols, COLUMN_ALIASES["description"])
    amt_col  = _find_column(cols, COLUMN_ALIASES["amount"])

    missing = [name for name, col in [("txn_id", txn_col), ("date", date_col), ("amount", amt_col)] if col is None]
    if missing:
        raise ValueError(f"Ledger PDF missing required columns: {missing}. Found: {cols}")

    entries = []
    for _, row in df.iterrows():
        txn_id  = str(row[txn_col]).strip()
        amount  = _parse_amount(row[amt_col])
        txn_date = _parse_date(row[date_col])
        desc    = str(row[desc_col]).strip() if desc_col else ""

        if not txn_id or amount is None or txn_date is None:
            continue  # skip malformed rows

        entries.append(LedgerEntry(
            txn_id=txn_id,
            date=txn_date,
            description=desc,
            amount=amount,
        ))
    return entries


def parse_settlement(pdf_path: str) -> List[SettlementEntry]:
    """Parse a bank/settlement PDF and return SettlementEntry objects."""
    df = _extract_dataframe(pdf_path)
    cols = df.columns.tolist()

    txn_col      = _find_column(cols, COLUMN_ALIASES["txn_id"])
    date_col     = _find_column(cols, COLUMN_ALIASES["date"])
    desc_col     = _find_column(cols, COLUMN_ALIASES["description"])
    amt_col      = _find_column(cols, COLUMN_ALIASES["amount"])
    refund_col   = _find_column(cols, COLUMN_ALIASES["is_refund"])
    parent_col   = _find_column(cols, COLUMN_ALIASES["parent_txn_id"])

    missing = [name for name, col in [("txn_id", txn_col), ("date", date_col), ("amount", amt_col)] if col is None]
    if missing:
        raise ValueError(f"Settlement PDF missing required columns: {missing}. Found: {cols}")

    entries = []
    for _, row in df.iterrows():
        txn_id   = str(row[txn_col]).strip()
        amount   = _parse_amount(row[amt_col])
        txn_date = _parse_date(row[date_col])
        desc     = str(row[desc_col]).strip() if desc_col else ""

        if not txn_id or amount is None or txn_date is None:
            continue

        # Detect refund from type column or negative amount
        is_refund = False
        if refund_col:
            val = str(row[refund_col]).strip().lower()
            is_refund = val in ("refund", "credit", "true", "1", "yes", "cr")
        elif amount < 0:
            is_refund = True

        parent_txn_id = None
        if parent_col:
            raw = str(row[parent_col]).strip()
            parent_txn_id = raw if raw and raw.lower() not in ("none", "nan", "") else None

        entries.append(SettlementEntry(
            txn_id=txn_id,
            date=txn_date,
            description=desc,
            amount=abs(amount),
            is_refund=is_refund,
            parent_txn_id=parent_txn_id,
        ))
    return entries
