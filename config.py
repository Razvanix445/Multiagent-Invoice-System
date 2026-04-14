XMPP_DOMAIN   = "localhost"
XMPP_PASSWORD = "invoice123"

AGENT_JIDS = {
    "ingestion":     f"ingestion_agent@{XMPP_DOMAIN}",
    "validation":    f"validation_agent@{XMPP_DOMAIN}",
    "decision":      f"decision_agent@{XMPP_DOMAIN}",
    "communication": f"communication_agent@{XMPP_DOMAIN}",
    "audit":         f"audit_agent@{XMPP_DOMAIN}",
}

# Business rules
AUTO_APPROVE_THRESHOLD       = 1000.00
MANAGER_ESCALATION_THRESHOLD = 10_000.00
APPROVER_EMAIL               = "manager@company.com"
FINANCE_TEAM_EMAIL           = "finance@company.com"

APPROVED_VENDORS = {
    "V001": "Acme Supplies SRL",
    "V002": "TechParts GmbH",
    "V003": "Office World SA",
    "V004": "Cloud Services Ltd",
    "V005": "Garmin Romania SRL",
}

ACCEPTED_CURRENCIES = {"EUR", "USD", "RON", "GBP"}

# Audit log
AUDIT_LOG_DIR  = "./audit_logs"
AUDIT_LOG_FILE = "pipeline_audit.jsonl"

# FIPA ACL performatives
PERF_INFORM  = "inform"
PERF_REQUEST = "request"
PERF_CONFIRM = "confirm"
PERF_FAILURE = "failure"

# SPADE message metadata keys
THREAD_INVOICE_PIPELINE = "invoice-pipeline"
META_STAGE              = "stage"

STAGE_INGESTION     = "ingestion"
STAGE_VALIDATION    = "validation"
STAGE_DECISION      = "decision"
STAGE_COMMUNICATION = "communication"
STAGE_AUDIT         = "audit"