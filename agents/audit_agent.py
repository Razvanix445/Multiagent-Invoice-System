import json
import httpx
from datetime import datetime
from pathlib import Path

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour, PeriodicBehaviour
from spade.template import Template

from models import InvoiceContext, InvoiceStatus
from config import (
    PERF_INFORM, META_STAGE,
    STAGE_AUDIT,
    AUDIT_LOG_DIR, AUDIT_LOG_FILE,
)

API_BASE = "http://localhost:8000"


async def notify_api(endpoint: str, payload: dict):
    """POST a progress update to FastAPI, which pushes it to the browser via WebSocket."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{API_BASE}{endpoint}", json=payload)
    except Exception as e:
        print(f"[Audit] Could not notify API: {e}")


class AuditWriter:
    """Handles all file I/O for the JSONL audit logs."""

    def __init__(self, log_dir: str, log_file: str):
        self.log_dir = Path(log_dir)
        self.log_path = self.log_dir / log_file
        self.event_path = self.log_dir / "audit_events.jsonl"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def write_invoice_record(self, ctx: InvoiceContext):
        """Append a full invoice lifecycle record to the main audit log."""
        record = json.loads(ctx.to_json())
        record["_archived_at"] = datetime.utcnow().isoformat()
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def write_event(self, event: dict):
        """Append a single audit event to the events log."""
        with open(self.event_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def get_stats(self) -> dict:
        """Read the audit log and return aggregate statistics."""
        if not self.log_path.exists():
            return {"total": 0}
        records = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
        decisions = [r.get("decision", "") for r in records]
        totals = [float(r.get("invoice_total", 0)) for r in records]
        return {
            "total":         len(records),
            "auto_approved": decisions.count("auto_approve"),
            "escalated":     decisions.count("escalate"),
            "rejected":      decisions.count("reject"),
            "total_value":   sum(totals),
            "avg_value":     sum(totals) / len(totals) if totals else 0,
        }


class ArchiveInvoiceBehaviour(CyclicBehaviour):
    """Receives invoice records, writes them to JSONL, and notifies the web dashboard."""

    async def run(self):
        msg = await self.receive(timeout=10)
        if msg is None:
            return

        self.agent.log(f"[Audit] Received record from {msg.sender}")

        try:
            ctx = InvoiceContext.from_json(msg.body)

            if ctx.pipeline_id in self.agent.archived_ids:
                self.agent.log(f"[Audit] Skipping duplicate {ctx.pipeline_id}")
                return

            ctx.status = InvoiceStatus.ARCHIVED
            ctx.add_audit(agent="AuditAgent", action="archived", detail=f"Written to {AUDIT_LOG_FILE}")

            self.agent.writer.write_invoice_record(ctx)
            for event in ctx.audit_log:
                event["pipeline_id"] = ctx.pipeline_id
                event["invoice_id"]  = ctx.invoice_id
                self.agent.writer.write_event(event)

            self.agent.archived_ids.add(ctx.pipeline_id)
            self._print_summary(ctx)

            await notify_api("/internal/complete", {
                "pipeline_id":     ctx.pipeline_id,
                "invoice_id":      ctx.invoice_id,
                "decision":        ctx.decision.value if ctx.decision else None,
                "decision_reason": ctx.decision_reason,
                "vendor_name":     ctx.vendor_name,
                "invoice_total":   ctx.invoice_total,
                "currency":        ctx.currency,
            })

            self.agent.log(f"[Audit] Archived {ctx.invoice_id} ({ctx.pipeline_id})")

        except Exception as e:
            self.agent.log(f"[Audit] ERROR: {e}")

    def _print_summary(self, ctx: InvoiceContext):
        sep = "═" * 65
        print(f"\n{sep}\n  AUDIT SUMMARY — {ctx.invoice_id}\n{sep}")
        print(f"  Vendor   : {ctx.vendor_name}")
        print(f"  Amount   : {ctx.invoice_total:.2f} {ctx.currency}")
        print(f"  Decision : {ctx.decision.value.upper() if ctx.decision else 'N/A'}")
        for i, e in enumerate(ctx.audit_log, 1):
            print(f"  {i}. [{e['timestamp'][11:19]}] {e['agent']:20s} | {e['action']}")
        print(f"{sep}\n")


class PeriodicReportBehaviour(PeriodicBehaviour):
    """Prints pipeline statistics to console every 60 seconds."""

    async def run(self):
        stats = self.agent.writer.get_stats()
        if stats["total"] == 0:
            return
        print(f"\n== STATS [{datetime.now().strftime('%H:%M:%S')}] ==")
        print(f"  Total: {stats['total']} | Approved: {stats['auto_approved']} | "
              f"Escalated: {stats['escalated']} | Rejected: {stats['rejected']}")
        print(f"  Total value: {stats['total_value']:.2f} EUR\n")


class AuditAgent(Agent):
    """Persists all invoice records to JSONL and notifies the web dashboard on completion."""

    def log(self, message: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    async def setup(self):
        self.log("[Audit] Starting up...")
        self.writer = AuditWriter(AUDIT_LOG_DIR, AUDIT_LOG_FILE)
        self.archived_ids: set = set()
        template = Template()
        template.set_metadata("performative", PERF_INFORM)
        template.set_metadata(META_STAGE, STAGE_AUDIT)
        self.add_behaviour(ArchiveInvoiceBehaviour(), template)
        self.add_behaviour(PeriodicReportBehaviour(period=60))
        self.log(f"[Audit] Ready → {self.writer.log_path}")
