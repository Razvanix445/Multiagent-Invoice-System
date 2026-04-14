from datetime import datetime

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from spade.template import Template

from models import (
    InvoiceContext, InvoiceStatus,
    ValidationResult, DecisionOutcome,
)
from config import (
    AGENT_JIDS,
    PERF_INFORM, PERF_FAILURE,
    THREAD_INVOICE_PIPELINE, META_STAGE,
    STAGE_DECISION, STAGE_COMMUNICATION, STAGE_AUDIT,
    AUTO_APPROVE_THRESHOLD, MANAGER_ESCALATION_THRESHOLD,
    APPROVER_EMAIL, FINANCE_TEAM_EMAIL,
)


class DecisionEngine:
    """
    Rule-based engine that decides the outcome for each invoice.

    Rules (in order):
      1. Validation FAIL           → REJECT
      2. Total > manager threshold → ESCALATE to manager
      3. Total > auto threshold    → ESCALATE to finance team
      4. Validation WARNING        → ESCALATE to finance team
      5. All clear                 → AUTO_APPROVE
    """

    def decide(self, ctx: InvoiceContext) -> tuple[DecisionOutcome, str, str]:
        """Returns (outcome, reason, approver_email)."""
        val = ctx.validation

        if val and val.overall == ValidationResult.FAIL:
            return (
                DecisionOutcome.REJECT,
                f"Invoice failed validation. Errors: {'; '.join(val.errors)}",
                FINANCE_TEAM_EMAIL,
            )

        if ctx.invoice_total > MANAGER_ESCALATION_THRESHOLD:
            return (
                DecisionOutcome.ESCALATE,
                f"Invoice total {ctx.invoice_total:.2f} {ctx.currency} exceeds manager threshold ({MANAGER_ESCALATION_THRESHOLD:.2f}). Requires senior approval.",
                APPROVER_EMAIL,
            )

        if ctx.invoice_total > AUTO_APPROVE_THRESHOLD:
            return (
                DecisionOutcome.ESCALATE,
                f"Invoice total {ctx.invoice_total:.2f} {ctx.currency} exceeds auto-approval limit ({AUTO_APPROVE_THRESHOLD:.2f}). Assigned to finance team.",
                FINANCE_TEAM_EMAIL,
            )

        if val and val.overall == ValidationResult.WARNING:
            return (
                DecisionOutcome.ESCALATE,
                f"Invoice passed with warnings: {'; '.join(val.warnings)}. Manual review recommended.",
                FINANCE_TEAM_EMAIL,
            )

        return (
            DecisionOutcome.AUTO_APPROVE,
            f"Invoice total {ctx.invoice_total:.2f} {ctx.currency} is within auto-approval threshold. Vendor '{ctx.vendor_name}' verified. All checks passed.",
            "",
        )


class MakeDecisionBehaviour(CyclicBehaviour):
    """Applies decision rules and forwards to Communication and Audit agents."""

    async def run(self):
        msg = await self.receive(timeout=10)
        if msg is None:
            return

        self.agent.log(f"[Decision] Received invoice from {msg.sender}")

        try:
            ctx = InvoiceContext.from_json(msg.body)
            outcome, reason, approver = DecisionEngine().decide(ctx)

            ctx.decision = outcome
            ctx.decision_reason = reason
            ctx.approver_email = approver
            ctx.status = InvoiceStatus.AUTO_APPROVED if outcome == DecisionOutcome.AUTO_APPROVE else InvoiceStatus.ESCALATED

            ctx.add_audit(agent="DecisionAgent", action=f"decision_{outcome.value}", detail=reason)
            self.agent.log(f"[Decision] Invoice {ctx.invoice_id}: {outcome.value.upper()} — {reason[:80]}...")

            await self._forward(AGENT_JIDS["communication"], STAGE_COMMUNICATION, ctx)
            await self._forward(AGENT_JIDS["audit"], STAGE_AUDIT, ctx)

        except Exception as e:
            self.agent.log(f"[Decision] ERROR: {e}")

    async def _forward(self, to: str, stage: str, ctx: InvoiceContext):
        out = Message(to=to)
        out.set_metadata("performative", PERF_INFORM)
        out.set_metadata("thread", THREAD_INVOICE_PIPELINE)
        out.set_metadata(META_STAGE, stage)
        out.body = ctx.to_json()
        await self.send(out)


class DecisionAgent(Agent):
    """Applies business rules to decide what happens to each invoice."""

    def log(self, message: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    async def setup(self):
        self.log("[Decision] Starting up...")
        template = Template()
        template.set_metadata("performative", PERF_INFORM)
        template.set_metadata(META_STAGE, STAGE_DECISION)
        self.add_behaviour(MakeDecisionBehaviour(), template)
        self.log("[Decision] Ready.")