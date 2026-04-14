import asyncio
import base64
import json
import uuid
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from config import (
    AGENT_JIDS, XMPP_PASSWORD,
    PERF_REQUEST, THREAD_INVOICE_PIPELINE,
    AUDIT_LOG_DIR, AUDIT_LOG_FILE,
)

app = FastAPI(title="Invoice Processing Pipeline API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    """Tracks all connected WebSocket clients globally."""

    def __init__(self):
        self.clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.clients:
            self.clients.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.clients:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.remove(ws)


manager = ConnectionManager()


async def send_to_ingestion_agent(payload: dict) -> str:
    """Spawn a temporary SPADE agent to forward the invoice payload via XMPP."""
    from spade.agent import Agent
    from spade.behaviour import OneShotBehaviour
    from spade.message import Message

    pipeline_id = str(uuid.uuid4())[:8]
    payload["pipeline_id"] = pipeline_id

    class SenderAgent(Agent):
        async def setup(self):
            class SendBehaviour(OneShotBehaviour):
                async def run(self):
                    msg = Message(to=AGENT_JIDS["ingestion"])
                    msg.set_metadata("performative", PERF_REQUEST)
                    msg.set_metadata("thread", THREAD_INVOICE_PIPELINE)
                    msg.body = json.dumps(payload)
                    await self.send(msg)
            self.add_behaviour(SendBehaviour())

    sender = SenderAgent("api_gateway@localhost", XMPP_PASSWORD)
    await sender.start(auto_register=True)
    await asyncio.sleep(1)
    await sender.stop()

    return pipeline_id


def read_audit_log(limit: int = 100, search: str = "") -> list[dict]:
    """Read pipeline_audit.jsonl, optionally filtering by search term."""
    log_path = Path(AUDIT_LOG_DIR) / AUDIT_LOG_FILE
    if not log_path.exists():
        return []

    records = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if search:
                    s = search.lower()
                    if not any(
                        s in str(record.get(field, "")).lower()
                        for field in ("invoice_id", "vendor_name", "decision", "pipeline_id")
                    ):
                        continue
                records.append(record)
            except json.JSONDecodeError:
                continue

    records.reverse()
    return records[:limit]


def compute_stats() -> dict:
    """Compute aggregate statistics from the audit log."""
    records = read_audit_log(limit=10000)
    if not records:
        return {"total": 0, "auto_approved": 0, "escalated": 0, "rejected": 0,
                "total_value": 0.0, "avg_value": 0.0, "success_rate": 0.0}

    decisions = [r.get("decision", "") for r in records]
    totals = [float(r.get("invoice_total", 0)) for r in records]
    total_val = sum(totals)
    approved = decisions.count("auto_approve")
    escalated = decisions.count("escalate")

    return {
        "total":         len(records),
        "auto_approved": approved,
        "escalated":     escalated,
        "rejected":      decisions.count("reject"),
        "total_value":   round(total_val, 2),
        "avg_value":     round(total_val / len(records), 2),
        "success_rate":  round((approved + escalated) / len(records) * 100, 1),
    }


@app.get("/")
async def root():
    return FileResponse("frontend/index.html")


@app.post("/upload/pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """Accept a PDF upload and submit it to the agent pipeline."""
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    pdf_bytes   = await file.read()
    b64_content = base64.b64encode(pdf_bytes).decode()
    pipeline_id = await send_to_ingestion_agent({
        "type": "pdf", "filename": file.filename, "data": b64_content
    })

    return {
        "pipeline_id": pipeline_id,
        "filename":    file.filename,
        "ws_url":      f"ws://localhost:8000/ws/{pipeline_id}",
    }


@app.post("/upload/text")
async def upload_text(payload: dict):
    """Accept raw invoice text and submit it to the agent pipeline."""
    pipeline_id = await send_to_ingestion_agent({"type": "text", "text": payload.get("text", "")})
    return {"pipeline_id": pipeline_id}


@app.get("/history")
async def get_history(limit: int = 50, search: str = ""):
    return read_audit_log(limit=limit, search=search)


@app.get("/stats")
async def get_stats():
    return compute_stats()


@app.get("/invoice/{pipeline_id}")
async def get_invoice(pipeline_id: str):
    for r in read_audit_log(limit=10000):
        if r.get("pipeline_id") == pipeline_id:
            return r
    raise HTTPException(status_code=404, detail="Invoice not found.")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Global WebSocket channel for all pipeline events."""
    await manager.connect(websocket)
    try:
        await websocket.send_json({"event": "connected"})
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.send_json({"event": "ping"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/internal/complete")
async def pipeline_complete(event: dict):
    await manager.broadcast({"event": "pipeline_complete", **event})
    await manager.broadcast({"event": "stats_update", "stats": compute_stats()})
    return {"ok": True}

@app.post("/internal/progress")
async def pipeline_progress(event: dict):
    await manager.broadcast({"event": "pipeline_update", **event})
    return {"ok": True}