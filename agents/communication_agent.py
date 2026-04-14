from datetime import datetime

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from spade.template import Template

from models import InvoiceContext, InvoiceStatus, DecisionOutcome
from config import (
    AGENT_JIDS,
    PERF_INFORM,
    THREAD_INVOICE_PIPELINE, META_STAGE,
    STAGE_COMMUNICATION, STAGE_AUDIT,
    FINANCE_TEAM_EMAIL,
)


class NotificationComposer:
    """Builds email subject and body for each decision outcome."""

    @staticmethod
    def auto_approved(ctx: InvoiceContext) -> dict:
        return {
            "to":      FINANCE_TEAM_EMAIL,
            "subject": f"Invoice Auto-Approved: {ctx.invoice_id}",
            "body": (
                f"Invoice {ctx.invoice_id} from {ctx.vendor_name} has been automatically approved.\n\n"
                f"Amount: {ctx.invoice_total:.2f} {ctx.currency}\n"
                f"Date:   {ctx.invoice_date}\n"
                f"Reason: {ctx.decision_reason}\n\n"
                f"No action required.\nPipeline ID: {ctx.pipeline_id}"
            ),
        }

    @staticmethod
    def escalated(ctx: InvoiceContext) -> dict:
        return {
            "to":      ctx.approver_email,
            "subject": f"Invoice Requires Approval: {ctx.invoice_id}",
            "body": (
                f"An invoice requires your review.\n\n"
                f"Vendor:  {ctx.vendor_name} ({ctx.vendor_id})\n"
                f"Amount:  {ctx.invoice_total:.2f} {ctx.currency}\n"
                f"Date:    {ctx.invoice_date} — Due: {ctx.due_date}\n\n"
                f"Reason:\n{ctx.decision_reason}\n\n"
                f"Pipeline ID: {ctx.pipeline_id}"
            ),
        }

    @staticmethod
    def rejected(ctx: InvoiceContext) -> dict:
        validation_errors = (
            "\n".join(f"  - {e}" for e in ctx.validation.errors)
            if ctx.validation else "  N/A"
        )
        return {
            "to":      FINANCE_TEAM_EMAIL,
            "subject": f"Invoice Rejected: {ctx.invoice_id}",
            "body": (
                f"Invoice {ctx.invoice_id} from {ctx.vendor_name} was REJECTED.\n\n"
                f"Amount: {ctx.invoice_total:.2f} {ctx.currency}\n"
                f"Reason: {ctx.decision_reason}\n\n"
                f"Validation errors:\n{validation_errors}\n\n"
                f"Pipeline ID: {ctx.pipeline_id}"
            ),
        }


class EmailSender:
    """Simulates email sending. In production: it has to be replaced with SendGrid or AWS SES."""

    @staticmethod
    def send(to: str, subject: str, body: str):
        print(f"\n{'─'*60}")
        print(f"📧  EMAIL → {to}")
        print(f"    Subject: {subject}")
        for line in body.splitlines():
            print(f"    {line}")
        print(f"{'─'*60}\n")


class SlackSender:
    """Simulates Slack notification. In production: it has to be replaced with Slack Webhook API."""

    @staticmethod
    def send(channel: str, message: str):
        print(f"\n{'─'*60}")
        print(f"💬  SLACK → #{channel}: {message}")
        print(f"{'─'*60}\n")


class SendNotificationBehaviour(CyclicBehaviour):
    """Receives a decided invoice, sends email + Slack notification, forwards to Audit Agent."""

    async def run(self):
        msg = await self.receive(timeout=10)
        if msg is None:
            return

        self.agent.log(f"[Communication] Received invoice from {msg.sender}")

        try:
            ctx = InvoiceContext.from_json(msg.body)

            if ctx.decision == DecisionOutcome.AUTO_APPROVE:
                notification = NotificationComposer.auto_approved(ctx)
            elif ctx.decision == DecisionOutcome.ESCALATE:
                notification = NotificationComposer.escalated(ctx)
            else:
                notification = NotificationComposer.rejected(ctx)

            EmailSender.send(
                to=notification["to"],
                subject=notification["subject"],
                body=notification["body"],
            )
            SlackSender.send(
                channel="invoice-approvals",
                message=f"Invoice *{ctx.invoice_id}* ({ctx.vendor_name}) | {ctx.invoice_total:.2f} {ctx.currency} | Decision: *{ctx.decision.value.upper()}*",
            )

            ctx.notification_sent = True
            ctx.notification_channel = "email+slack"
            ctx.status = InvoiceStatus.NOTIFIED
            ctx.add_audit(
                agent="CommunicationAgent",
                action="notification_sent",
                detail=f"Email to {notification['to']}, Slack to #invoice-approvals",
            )
            self.agent.log(f"[Communication] Notified for invoice {ctx.invoice_id} → {notification['to']}")

            out = Message(to=AGENT_JIDS["audit"])
            out.set_metadata("performative", PERF_INFORM)
            out.set_metadata("thread", THREAD_INVOICE_PIPELINE)
            out.set_metadata(META_STAGE, STAGE_AUDIT)
            out.body = ctx.to_json()
            await self.send(out)

        except Exception as e:
            self.agent.log(f"[Communication] ERROR: {e}")


class CommunicationAgent(Agent):
    """Sends email and Slack notifications for every invoice decision."""

    def log(self, message: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    async def setup(self):
        self.log("[Communication] Starting up...")
        template = Template()
        template.set_metadata("performative", PERF_INFORM)
        template.set_metadata(META_STAGE, STAGE_COMMUNICATION)
        self.add_behaviour(SendNotificationBehaviour(), template)
        self.log("[Communication] Ready.")