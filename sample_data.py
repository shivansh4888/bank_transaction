"""
sample_data.py — Generates two sample PDFs (ledger + bank statement)
with all 4 gap types planted for testing and demo purposes.
Run this standalone: python sample_data.py
"""

from fpdf import FPDF
from datetime import date


def _make_pdf(filename: str, title: str, headers: list, rows: list):
    """Create a simple table PDF using fpdf2."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, title, ln=True, align="C")
    pdf.ln(4)

    # Column widths
    col_widths = [35, 28, 70, 35, 25]
    # Trim to number of headers
    col_widths = col_widths[: len(headers)]

    # Header row
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(50, 50, 50)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers):
        pdf.cell(col_widths[i], 8, h, border=1, fill=True)
    pdf.ln()

    # Data rows
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)
    for row in rows:
        for i, cell in enumerate(row):
            pdf.cell(col_widths[i], 7, str(cell), border=1)
        pdf.ln()

    pdf.output(filename)
    print(f"Created: {filename}")


def generate_sample_ledger(filename="sample_ledger.pdf"):
    headers = ["TXN_ID", "Date", "Description", "Amount"]
    rows = [
        # Normal match
        ["TXN001", "2024-01-05", "Invoice Payment - Acme",      "500.00"],
        ["TXN002", "2024-01-06", "Software License",             "120.00"],
        # Minor rounding gap (MATCHED_WITH_NOTE)
        ["TXN003", "2024-01-07", "Cloud Hosting Fee",             "99.99"],
        # Large gap → DISPUTED
        ["TXN004", "2024-01-08", "Office Supplies",              "250.00"],
        # No bank entry → AGED_OUT
        ["TXN005", "2024-01-02", "Consulting Fee",               "800.00"],
        # Duplicate TXN ID in ledger
        ["TXN006", "2024-01-09", "Marketing Campaign",           "300.00"],
        ["TXN006", "2024-01-09", "Marketing Campaign (dup)",     "300.00"],
        # Normal match 2
        ["TXN007", "2024-01-10", "Vendor Payment - XYZ",         "450.00"],
    ]
    _make_pdf(filename, "Company Ledger — January 2024", headers, rows)


def generate_sample_bank(filename="sample_bank.pdf"):
    headers = ["TXN_ID", "Date", "Description", "Amount", "Type"]
    rows = [
        # Matches TXN001
        ["TXN001", "2024-01-05", "Payment received - Acme",     "500.00",  "debit"],
        # Matches TXN002
        ["TXN002", "2024-01-06", "Software License",             "120.00",  "debit"],
        # Matches TXN003 with minor rounding gap
        ["TXN003", "2024-01-07", "Cloud Hosting Fee",             "100.01",  "debit"],
        # Matches TXN004 with large gap
        ["TXN004", "2024-01-08", "Office Supplies",              "175.00",  "debit"],
        # TXN005 absent → AGED_OUT on ledger side
        # Orphan refund — no ledger counterpart
        ["TXN008", "2024-01-11", "Refund - cancelled order",     "60.00",   "refund"],
        # Matches TXN007
        ["TXN007", "2024-01-10", "Vendor Payment - XYZ",         "450.00",  "debit"],
    ]
    _make_pdf(filename, "Bank Statement — January 2024", headers, rows)


if __name__ == "__main__":
    generate_sample_ledger()
    generate_sample_bank()
    print("\nSample PDFs ready. Upload them in the app to see the reconciliation report.")
