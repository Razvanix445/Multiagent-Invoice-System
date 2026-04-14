from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import json
import uuid


class InvoiceStatus(Enum):
    RECEIVED     = "received"
    EXTRACTED    = "extracted"
    VALID        = "valid"
    INVALID      = "invalid"
    AUTO_APPROVED = "auto_approved"
    ESCALATED    = "escalated"
    NOTIFIED     = "notified"
    ARCHIVED     = "archived"


class ValidationResult(Enum):
    PASS    = "pass"
    FAIL    = "fail"
    WARNING = "warning"


class DecisionOutcome(Enum):
    AUTO_APPROVE = "auto_approve"
    ESCALATE     = "escalate"
    REJECT       = "reject"


@dataclass
class ValidationReport:
    """Results of all validation checks performed on an invoice."""
    totals_match:       bool = False
    vendor_known:       bool = False
    duplicate_detected: bool = False
    currency_valid:     bool = False
    date_valid:         bool = False
    vat_valid:          bool = False
    errors:             list = field(default_factory=list)
    warnings:           list = field(default_factory=list)
    overall:            ValidationResult = ValidationResult.FAIL

    def to_dict(self) -> dict:
        return {
            "totals_match":       self.totals_match,
            "vendor_known":       self.vendor_known,
            "duplicate_detected": self.duplicate_detected,
            "currency_valid":     self.currency_valid,
            "date_valid":         self.date_valid,
            "vat_valid":          self.vat_valid,
            "errors":             self.errors,
            "warnings":           self.warnings,
            "overall":            self.overall.value,
        }


@dataclass
class InvoiceContext:
    """Shared data model passed between all pipeline agents via XMPP messages."""

    pipeline_id:          str   = field(default_factory=lambda: str(uuid.uuid4())[:8])
    invoice_id:           str   = ""
    source:               str   = ""
    vendor_name:          str   = ""
    vendor_id:            str   = ""
    invoice_date:         str   = ""
    due_date:             str   = ""
    currency:             str   = ""
    line_items:           list  = field(default_factory=list)
    subtotal:             float = 0.0
    vat_rate:             float = 0.0
    vat_amount:           float = 0.0
    invoice_total:        float = 0.0
    raw_text:             str   = ""
    validation:           Optional[ValidationReport] = None
    decision:             Optional[DecisionOutcome]  = None
    decision_reason:      str   = ""
    approver_email:       str   = ""
    notification_sent:    bool  = False
    notification_channel: str   = ""
    audit_log:            list  = field(default_factory=list)
    status:               InvoiceStatus = InvoiceStatus.RECEIVED
    created_at:           str   = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at:           str   = field(default_factory=lambda: datetime.utcnow().isoformat())

    def add_audit(self, agent: str, action: str, detail: str = ""):
        """Append a timestamped audit entry to the log."""
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "agent":     agent,
            "action":    action,
            "detail":    detail,
            "status":    self.status.value,
        }
        self.audit_log.append(entry)
        self.updated_at = entry["timestamp"]

    def to_json(self) -> str:
        """Serialize to JSON string for SPADE message transport."""
        return json.dumps({
            "pipeline_id":          self.pipeline_id,
            "invoice_id":           self.invoice_id,
            "source":               self.source,
            "vendor_name":          self.vendor_name,
            "vendor_id":            self.vendor_id,
            "invoice_date":         self.invoice_date,
            "due_date":             self.due_date,
            "currency":             self.currency,
            "line_items":           self.line_items,
            "subtotal":             self.subtotal,
            "vat_rate":             self.vat_rate,
            "vat_amount":           self.vat_amount,
            "invoice_total":        self.invoice_total,
            "raw_text":             self.raw_text,
            "validation":           self.validation.to_dict() if self.validation else None,
            "decision":             self.decision.value if self.decision else None,
            "decision_reason":      self.decision_reason,
            "approver_email":       self.approver_email,
            "notification_sent":    self.notification_sent,
            "notification_channel": self.notification_channel,
            "audit_log":            self.audit_log,
            "status":               self.status.value,
            "created_at":           self.created_at,
            "updated_at":           self.updated_at,
        }, indent=2)

    @staticmethod
    def from_json(raw: str) -> "InvoiceContext":
        """Deserialize from a JSON string received in a SPADE message."""
        d   = json.loads(raw)
        ctx = InvoiceContext(
            pipeline_id          = d["pipeline_id"],
            invoice_id           = d["invoice_id"],
            source               = d["source"],
            vendor_name          = d["vendor_name"],
            vendor_id            = d["vendor_id"],
            invoice_date         = d["invoice_date"],
            due_date             = d["due_date"],
            currency             = d["currency"],
            line_items           = d["line_items"],
            subtotal             = d["subtotal"],
            vat_rate             = d["vat_rate"],
            vat_amount           = d["vat_amount"],
            invoice_total        = d["invoice_total"],
            raw_text             = d["raw_text"],
            decision_reason      = d["decision_reason"],
            approver_email       = d["approver_email"],
            notification_sent    = d["notification_sent"],
            notification_channel = d["notification_channel"],
            audit_log            = d["audit_log"],
            status               = InvoiceStatus(d["status"]),
            created_at           = d["created_at"],
            updated_at           = d["updated_at"],
        )
        if d["validation"]:
            v = d["validation"]
            ctx.validation = ValidationReport(
                totals_match       = v["totals_match"],
                vendor_known       = v["vendor_known"],
                duplicate_detected = v["duplicate_detected"],
                currency_valid     = v["currency_valid"],
                date_valid         = v["date_valid"],
                vat_valid          = v["vat_valid"],
                errors             = v["errors"],
                warnings           = v["warnings"],
                overall            = ValidationResult(v["overall"]),
            )
        if d["decision"]:
            ctx.decision = DecisionOutcome(d["decision"])
        return ctx