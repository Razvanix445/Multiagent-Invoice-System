from datetime import datetime, date
import math
from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from spade.template import Template

from models import (
    InvoiceContext, InvoiceStatus,
    ValidationReport, ValidationResult,
)
from config import (
    AGENT_JIDS,
    PERF_INFORM, PERF_FAILURE,
    THREAD_INVOICE_PIPELINE, META_STAGE,
    STAGE_VALIDATION, STAGE_DECISION,
    APPROVED_VENDORS, ACCEPTED_CURRENCIES,
)


class InvoiceValidator:
    """Runs all validation checks on an InvoiceContext and returns a ValidationReport."""

    def __init__(self, seen_invoice_ids: set):
        self._seen_ids = seen_invoice_ids

    def validate(self, ctx: InvoiceContext) -> ValidationReport:
        """Run all checks independently and aggregate results."""
        report = ValidationReport()
        errors = []
        warnings = []

        # Check 1: Totals consistency
        computed_subtotal = sum(item.get("line_total", 0) for item in ctx.line_items)
        computed_vat = round(computed_subtotal * (ctx.vat_rate / 100), 2)
        computed_total = round(computed_subtotal + computed_vat, 2)
        totals_ok = (
            math.isclose(ctx.subtotal, computed_subtotal, rel_tol=0.01)
            and math.isclose(ctx.invoice_total, computed_total, rel_tol=0.01)
        )
        report.totals_match = totals_ok
        if not totals_ok:
            errors.append(f"Total mismatch: computed={computed_total:.2f}, stated={ctx.invoice_total:.2f}")

        # Check 2: Vendor verification (by ID first, then by name)
        if ctx.vendor_id and ctx.vendor_id in APPROVED_VENDORS:
            report.vendor_known = True
        elif ctx.vendor_name and ctx.vendor_name in APPROVED_VENDORS.values():
            report.vendor_known = True
        else:
            report.vendor_known = False
            errors.append(f"Unknown vendor: '{ctx.vendor_id or ctx.vendor_name}'")

        # Check 3: Duplicate detection
        if ctx.invoice_id in self._seen_ids:
            report.duplicate_detected = True
            errors.append(f"Duplicate invoice ID: '{ctx.invoice_id}'")
        else:
            report.duplicate_detected = False
            self._seen_ids.add(ctx.invoice_id)

        # Check 4: Currency validation
        report.currency_valid = ctx.currency.upper() in ACCEPTED_CURRENCIES
        if not report.currency_valid:
            errors.append(f"Unaccepted currency: '{ctx.currency}'. Accepted: {ACCEPTED_CURRENCIES}")

        # Check 5: Invoice date not in the future
        try:
            inv_date = date.fromisoformat(ctx.invoice_date)
            report.date_valid = inv_date <= date.today()
            if not report.date_valid:
                errors.append(f"Invoice date '{ctx.invoice_date}' is in the future.")
        except ValueError:
            report.date_valid = False
            errors.append(f"Invalid date format: '{ctx.invoice_date}'")

        # Check 6: VAT calculation
        expected_vat = round(ctx.subtotal * (ctx.vat_rate / 100), 2)
        report.vat_valid = math.isclose(ctx.vat_amount, expected_vat, rel_tol=0.01)
        if not report.vat_valid:
            errors.append(f"VAT mismatch: expected={expected_vat:.2f}, stated={ctx.vat_amount:.2f}")

        report.errors = errors
        report.warnings = warnings
        if errors:
            report.overall = ValidationResult.FAIL
        elif warnings:
            report.overall = ValidationResult.WARNING
        else:
            report.overall = ValidationResult.PASS

        return report


class ValidateInvoiceBehaviour(CyclicBehaviour):
    """Receives invoices, runs validation, forwards to Decision Agent."""

    async def run(self):
        msg = await self.receive(timeout=10)
        if msg is None:
            return

        self.agent.log(f"[Validation] Received invoice from {msg.sender}")

        try:
            ctx = InvoiceContext.from_json(msg.body)
            validator = InvoiceValidator(self.agent.seen_invoice_ids)
            report = validator.validate(ctx)
            ctx.validation = report

            if report.overall == ValidationResult.FAIL:
                ctx.status = InvoiceStatus.INVALID
                ctx.add_audit(agent="ValidationAgent", action="validation_failed",
                              detail=f"Errors: {'; '.join(report.errors)}")
                self.agent.log(f"[Validation] FAIL — Invoice {ctx.invoice_id}: {report.errors}")
            else:
                ctx.status = InvoiceStatus.VALID
                ctx.add_audit(agent="ValidationAgent", action="validation_passed",
                              detail=f"Result={report.overall.value}, warnings={report.warnings}")
                self.agent.log(f"[Validation] {report.overall.value.upper()} — Invoice {ctx.invoice_id}")

            await self._forward_to_decision(ctx)

        except Exception as e:
            self.agent.log(f"[Validation] ERROR: {e}")
            err = Message(to=str(msg.sender))
            err.set_metadata("performative", PERF_FAILURE)
            err.body = f"Validation error: {e}"
            await self.send(err)

    async def _forward_to_decision(self, ctx: InvoiceContext):
        out = Message(to=AGENT_JIDS["decision"])
        out.set_metadata("performative", PERF_INFORM)
        out.set_metadata("thread", THREAD_INVOICE_PIPELINE)
        out.set_metadata(META_STAGE, STAGE_DECISION)
        out.body = ctx.to_json()
        await self.send(out)
        self.agent.log(f"[Validation] Forwarded invoice {ctx.invoice_id} to Decision Agent")


class ValidationAgent(Agent):
    """Checks invoice correctness before any approval decision is made."""

    def log(self, message: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    async def setup(self):
        self.log("[Validation] Starting up...")
        self.seen_invoice_ids: set = set()
        template = Template()
        template.set_metadata("performative", PERF_INFORM)
        template.set_metadata(META_STAGE, STAGE_VALIDATION)
        self.add_behaviour(ValidateInvoiceBehaviour(), template)
        self.log("[Validation] Ready.")