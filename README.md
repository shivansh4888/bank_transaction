# Bank Transaction Reconciliation Tool

A Python + Streamlit app that matches ledger transactions against bank statements and generates a detailed gap report.

---

## Files

| File | Purpose |
|------|---------|
| `engine.py` | Core matching logic — idempotency gate, SLA clock, amount check, sum check, orphan refund detection |
| `pdf_parser.py` | Reads ledger and bank PDFs, maps flexible column names, returns typed entries |
| `sample_data.py` | Generates two demo PDFs with all 4 gap types planted |
| `app.py` | Streamlit UI — upload PDFs, pick close date, view report, download CSV |
| `requirements.txt` | Pinned Python dependencies |

---

## Quick Start (local)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501 in your browser.  
Tick **"Use sample data"** in the sidebar to try it instantly without any PDFs.

---

## Deploy to Streamlit Cloud (free)

1. Push this folder to a GitHub repository.
2. Go to [share.streamlit.io](https://share.streamlit.io) → New app.
3. Point it at your repo and set **Main file path** to `app.py`.
4. Click Deploy — done.

---

## PDF Column Requirements

Your PDFs must have a transaction table with at least these columns  
(exact names are flexible — the parser recognises common aliases):

| Canonical | Accepted aliases |
|-----------|-----------------|
| `txn_id` | transaction_id, ref, reference, id, trans id |
| `date` | txn_date, transaction_date, value_date |
| `description` | desc, narration, details, particulars |
| `amount` | amt, value, debit, credit, net amount |
| `type` *(bank only, optional)* | is_refund, credit/debit — values: refund/credit/debit |
| `parent_txn_id` *(optional)* | parent_id, original_txn — for orphan refund linking |

---

## Rules the Engine Enforces

| Rule | Behaviour |
|------|-----------|
| **Idempotency gate** | Same TXN-ID twice → second one flagged DUPLICATE and rejected |
| **SLA clock** | Ledger entry with no bank match past close date → AGED_OUT |
| **Amount check** | Gap > $0.05 → DISPUTED; gap ≤ $0.05 → MATCHED_WITH_NOTE |
| **Sum check** | Total ledger vs total settled after matching; catches rounding accumulation |
| **Orphan refund** | Bank refund with no ledger parent → ORPHAN_REFUND |
| **Decimal math** | All amounts use Python `Decimal` — no floating-point drift |

---

## Gap Types in Sample Data

| TXN | Gap Type |
|-----|----------|
| TXN003 | MATCHED_WITH_NOTE — $0.02 rounding gap |
| TXN004 | DISPUTED — $75 amount mismatch |
| TXN005 | AGED_OUT — no bank entry, past SLA |
| TXN006 | DUPLICATE — same TXN-ID appears twice in ledger |
| TXN008 | ORPHAN_REFUND — bank refund with no ledger parent |
