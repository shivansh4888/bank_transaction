"""
app.py — Streamlit UI for the Bank Transaction Reconciliation Tool.
Upload a Ledger PDF and a Bank Statement PDF, pick a close date,
and get a full reconciliation report.
"""

import streamlit as st
import pandas as pd
from datetime import date
import tempfile, os

from pdf_parser import parse_ledger, parse_settlement
from engine import reconcile
from sample_data import generate_sample_ledger, generate_sample_bank

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Bank Reconciliation Tool",
    page_icon="🏦",
    layout="wide",
)

# ── Status styling ───────────────────────────────────────────────────────────
STATUS_COLORS = {
    "MATCHED":           ("✅", "#22c55e"),
    "MATCHED_WITH_NOTE": ("⚠️", "#f59e0b"),
    "DISPUTED":          ("❌", "#ef4444"),
    "AGED_OUT":          ("🕐", "#8b5cf6"),
    "DUPLICATE":         ("🔁", "#64748b"),
    "ORPHAN_REFUND":     ("💸", "#ec4899"),
}

def badge(status: str) -> str:
    icon, color = STATUS_COLORS.get(status, ("❓", "#888"))
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:4px;font-size:0.8em">{icon} {status}</span>'


# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("🏦 Reconciliation Tool")
st.sidebar.markdown("Upload two PDFs and run the match engine.")

close_date = st.sidebar.date_input(
    "Close / Statement Date",
    value=date.today(),
    help="Transactions with no bank entry past this date are marked AGED_OUT.",
)

st.sidebar.markdown("---")
use_sample = st.sidebar.checkbox("Use sample data (no PDFs needed)", value=False)

# ── Main header ───────────────────────────────────────────────────────────────
st.title("Bank Transaction Reconciliation")
st.markdown("Match ledger entries against bank settlements, detect gaps, and generate a report.")

# ── File uploaders ────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    ledger_file = st.file_uploader("📄 Upload Ledger PDF", type=["pdf"])
with col2:
    bank_file = st.file_uploader("🏛️ Upload Bank Statement PDF", type=["pdf"])

run_btn = st.button("▶ Run Reconciliation", type="primary", use_container_width=True)

# ── Run logic ─────────────────────────────────────────────────────────────────
if run_btn or use_sample:
    with st.spinner("Parsing PDFs and running engine…"):
        try:
            if use_sample:
                # Generate sample files on-the-fly into temp dir
                with tempfile.TemporaryDirectory() as tmp:
                    lpath = os.path.join(tmp, "ledger.pdf")
                    bpath = os.path.join(tmp, "bank.pdf")
                    generate_sample_ledger(lpath)
                    generate_sample_bank(bpath)
                    ledger_entries = parse_ledger(lpath)
                    bank_entries   = parse_settlement(bpath)
            elif ledger_file and bank_file:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as lf:
                    lf.write(ledger_file.read())
                    lpath = lf.name
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as bf:
                    bf.write(bank_file.read())
                    bpath = bf.name
                ledger_entries = parse_ledger(lpath)
                bank_entries   = parse_settlement(bpath)
                os.unlink(lpath)
                os.unlink(bpath)
            else:
                st.warning("Please upload both PDFs or enable sample data.")
                st.stop()

            result = reconcile(ledger_entries, bank_entries, close_date)

        except Exception as e:
            st.error(f"Error during processing: {e}")
            st.stop()

    transactions = result["transactions"]
    summary      = result["summary"]

    # ── Summary metrics ───────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📊 Summary")

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total Transactions", summary["total_transactions"])
    m2.metric("Matched",            summary["status_counts"].get("MATCHED", 0))
    m3.metric("Disputed",           summary["status_counts"].get("DISPUTED", 0))
    m4.metric("Aged Out",           summary["status_counts"].get("AGED_OUT", 0))
    m5.metric("Duplicates",         summary["status_counts"].get("DUPLICATE", 0))

    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Ledger (matched)", f"${summary['total_ledger_matched']:,.2f}")
    c2.metric("Total Settled (matched)", f"${summary['total_settled_matched']:,.2f}")
    c3.metric("Sum Gap", f"${summary['sum_gap']:,.2f}")
    check = "✅ Passed" if summary["sum_check_passed"] else "❌ Failed"
    c4.metric("Sum Check", check)

    # ── Gap Breakdown ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("🔍 Gap Breakdown")
    counts = summary["status_counts"]
    gap_df = pd.DataFrame(
        [(s, counts.get(s, 0)) for s in STATUS_COLORS],
        columns=["Status", "Count"]
    )
    st.bar_chart(gap_df.set_index("Status"))

    # ── Transaction Table ─────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📋 Transaction Detail")

    # Filter controls
    all_statuses = list(STATUS_COLORS.keys())
    selected = st.multiselect("Filter by status", all_statuses, default=all_statuses)

    rows = []
    for t in transactions:
        if t.status not in selected:
            continue
        rows.append({
            "TXN ID":          t.txn_id,
            "Description":     t.description,
            "Ledger Date":     str(t.ledger_date) if t.ledger_date else "—",
            "Settled Date":    str(t.settled_date) if t.settled_date else "—",
            "Ledger Amt":      f"${t.ledger_amount:,.2f}"   if t.ledger_amount  is not None else "—",
            "Settled Amt":     f"${t.settled_amount:,.2f}"  if t.settled_amount is not None else "—",
            "Status":          t.status,
            "Note":            t.note,
        })

    if rows:
        df = pd.DataFrame(rows)

        def color_status(val):
            _, color = STATUS_COLORS.get(val, ("", "#888"))
            return f"background-color:{color};color:white;border-radius:4px"

        styled = df.style.applymap(color_status, subset=["Status"])
        st.dataframe(styled, use_container_width=True, height=450)
    else:
        st.info("No transactions match the selected filters.")

    # ── Duplicates List ───────────────────────────────────────────────────────
    duplicates = [t for t in transactions if t.status == "DUPLICATE"]
    if duplicates:
        st.markdown("---")
        st.subheader("🔁 Duplicate Transactions")
        for d in duplicates:
            st.warning(f"**{d.txn_id}** — {d.note} | Amount: {d.ledger_amount or d.settled_amount}")

    # ── Orphan Refunds ────────────────────────────────────────────────────────
    orphans = [t for t in transactions if t.status == "ORPHAN_REFUND"]
    if orphans:
        st.markdown("---")
        st.subheader("💸 Orphan Refunds")
        for o in orphans:
            st.error(f"**{o.txn_id}** — {o.note} | Settled Amount: ${o.settled_amount:,.2f}")

    # ── Download report ───────────────────────────────────────────────────────
    st.markdown("---")
    df_export = pd.DataFrame([{
        "TXN ID":       t.txn_id,
        "Description":  t.description,
        "Ledger Date":  t.ledger_date,
        "Settled Date": t.settled_date,
        "Ledger Amt":   float(t.ledger_amount)  if t.ledger_amount  is not None else None,
        "Settled Amt":  float(t.settled_amount) if t.settled_amount is not None else None,
        "Status":       t.status,
        "Note":         t.note,
    } for t in transactions])

    csv = df_export.to_csv(index=False)
    st.download_button(
        "⬇️ Download Full Report (CSV)",
        data=csv,
        file_name=f"reconciliation_report_{close_date}.csv",
        mime="text/csv",
        use_container_width=True,
    )
