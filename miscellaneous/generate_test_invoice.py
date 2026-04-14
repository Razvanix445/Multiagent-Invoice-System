from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from datetime import date, timedelta

def generate_invoice(filename="test_invoice.pdf"):
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    # Header
    c.setFont("Helvetica-Bold", 20)
    c.drawString(50, height - 60, "INVOICE")

    # Invoice details
    c.setFont("Helvetica", 12)
    details = [
        ("Invoice Number:", "INV-2024-007"),
        ("Vendor Name:",    "Acme Supplies SRL"),
        ("Vendor ID:",      "V001"),
        ("Invoice Date:",   date.today().isoformat()),
        ("Due Date:",       (date.today() + timedelta(days=30)).isoformat()),
        ("Currency:",       "EUR"),
    ]
    y = height - 120
    for label, value in details:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(50, y, label)
        c.setFont("Helvetica", 11)
        c.drawString(200, y, value)
        y -= 22

    # Line items header
    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(50,  y, "Description")
    c.drawString(300, y, "Qty")
    c.drawString(370, y, "Unit Price")
    c.drawString(460, y, "Line Total")
    c.line(50, y - 5, 550, y - 5)

    # Line items
    items = [
        ("Software License",  3, 200.00),
        ("Support Package",   1, 450.00),
        ("Training Session",  2,  75.00),
    ]
    y -= 25
    c.setFont("Helvetica", 11)
    for desc, qty, price in items:
        total = qty * price
        c.drawString(50,  y, desc)
        c.drawString(300, y, str(qty))
        c.drawString(370, y, f"{price:.2f}")
        c.drawString(460, y, f"{total:.2f}")
        y -= 22

    # Totals
    subtotal = sum(qty * price for _, qty, price in items)
    vat_rate = 19.0
    vat_amount = round(subtotal * vat_rate / 100, 2)
    total = round(subtotal + vat_amount, 2)

    y -= 20
    c.line(50, y, 550, y)
    y -= 20
    c.setFont("Helvetica", 11)
    c.drawString(370, y, "Subtotal:");    c.drawString(460, y, f"{subtotal:.2f}")
    y -= 22
    c.drawString(370, y, f"VAT Rate:");  c.drawString(460, y, f"{vat_rate}%")
    y -= 22
    c.drawString(370, y, "VAT Amount:"); c.drawString(460, y, f"{vat_amount:.2f}")
    y -= 22
    c.setFont("Helvetica-Bold", 12)
    c.drawString(370, y, "Total:");      c.drawString(460, y, f"{total:.2f}")

    c.save()
    print(f"Generated: {filename}")
    print(f"Subtotal: {subtotal}, VAT: {vat_amount}, Total: {total}")

generate_invoice()