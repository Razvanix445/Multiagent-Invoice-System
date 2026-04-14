import asyncio

import spade

from agents.ingestion_agent import IngestionAgent
from agents.validation_agent import ValidationAgent
from agents.decision_agent import DecisionAgent
from agents.communication_agent import CommunicationAgent
from agents.audit_agent import AuditAgent

from config import (
    AGENT_JIDS, XMPP_PASSWORD
)


async def main():
    """
    Entry point for the Invoice Processing Multi-Agent System.
    """
    ingestion = IngestionAgent(AGENT_JIDS["ingestion"], XMPP_PASSWORD)
    validation = ValidationAgent(AGENT_JIDS["validation"], XMPP_PASSWORD)
    decision = DecisionAgent(AGENT_JIDS["decision"], XMPP_PASSWORD)
    communication = CommunicationAgent(AGENT_JIDS["communication"], XMPP_PASSWORD)
    audit = AuditAgent(AGENT_JIDS["audit"], XMPP_PASSWORD)

    for agent in [ingestion, validation, decision, communication, audit]:
        await agent.start(auto_register=True)

    print("[Main] All agents running. Open http://127.0.0.1:8000 to submit invoices.\n")
    print("[Main] Press Ctrl+C to stop.\n")

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n[Main] Shutting down...")
        for agent in [ingestion, validation, decision, communication, audit]:
            await agent.stop()
        print("[Main] Done.\n")


if __name__ == "__main__":
    spade.run(main())
