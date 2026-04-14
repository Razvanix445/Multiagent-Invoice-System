from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import date, timedelta


def generate_invoice(filename, invoice_number, vendor_name, vendor_id,
                     currency, items, vat_rate, invoice_date, due_date):
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 60, "INVOICE")

    details = [
        ("Invoice Number:", invoice_number),
        ("Vendor Name:",    vendor_name),
        ("Vendor ID:",      vendor_id),
        ("Invoice Date:",   invoice_date),
        ("Due Date:",       due_date),
        ("Currency:",       currency),
    ]
    y = height - 120
    for label, value in details:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, label)
        c.setFont("Helvetica", 11)
        c.drawString(200, y, value)
        y -= 22

    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50,  y, "Description")
    c.drawString(300, y, "Qty")
    c.drawString(370, y, "Unit Price")
    c.drawString(460, y, "Line Total")
    c.line(50, y - 5, 550, y - 5)

    y -= 25
    c.setFont("Helvetica", 11)
    for desc, qty, price in items:
        total = qty * price
        c.drawString(50,  y, desc)
        c.drawString(300, y, str(qty))
        c.drawString(370, y, f"{price:.2f}")
        c.drawString(460, y, f"{total:.2f}")
        y -= 22

    subtotal   = sum(qty * price for _, qty, price in items)
    vat_amount = round(subtotal * vat_rate / 100, 2)
    total      = round(subtotal + vat_amount, 2)

    y -= 20
    c.line(50, y, 550, y)
    y -= 20
    c.setFont("Helvetica", 11)
    c.drawString(370, y, "Subtotal:");    c.drawString(460, y, f"{subtotal:.2f}")
    y -= 22
    c.drawString(370, y, "VAT Rate:");   c.drawString(460, y, f"{vat_rate}%")
    y -= 22
    c.drawString(370, y, "VAT Amount:"); c.drawString(460, y, f"{vat_amount:.2f}")
    y -= 22
    c.setFont("Helvetica-Bold", 12)
    c.drawString(370, y, "Total:");      c.drawString(460, y, f"{total:.2f}")

    c.save()
    print(f"Generated: {filename} — Subtotal: {subtotal}, VAT: {vat_amount}, Total: {total}")


today      = date.today().isoformat()
next_month = (date.today() + timedelta(days=30)).isoformat()
last_year  = "2023-01-15"  # past date — will fail date check if future needed

# ── Invoice 1: AUTO-APPROVED ──────────────────────────────────────────────────
# Known vendor, valid currency, correct totals, amount < €1000
generate_invoice(
    filename       = "invoice_approved.pdf",
    invoice_number = "INV-2024-010",
    vendor_name    = "Acme Supplies SRL",
    vendor_id      = "V001",
    currency       = "EUR",
    invoice_date   = today,
    due_date       = next_month,
    items          = [
        ("Office Supplies",  2, 50.00),
        ("Printer Paper",    5, 12.00),
        ("Pens and Markers", 3, 15.00),
    ],
    vat_rate       = 19.0,
)

# ── Invoice 2: REJECTED ───────────────────────────────────────────────────────
# Unknown vendor (V999), unaccepted currency (XYZ), future date, wrong totals
generate_invoice(
    filename       = "invoice_rejected.pdf",
    invoice_number = "INV-2024-011",
    vendor_name    = "Unknown Corp",
    vendor_id      = "V999",
    currency       = "XYZ",
    invoice_date   = "2027-06-01",   # future date
    due_date       = "2027-07-01",
    items          = [
        ("Mystery Item", 1, 200.00),
    ],
    vat_rate       = 19.0,
)