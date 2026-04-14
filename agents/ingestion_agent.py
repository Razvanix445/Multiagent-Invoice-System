import base64
import io
import json
import re
import httpx
import pdfplumber
from datetime import datetime

from spade.agent import Agent
from spade.behaviour import CyclicBehaviour
from spade.message import Message
from spade.template import Template

from models import InvoiceContext, InvoiceStatus
from config import (
    AGENT_JIDS,
    PERF_INFORM, PERF_REQUEST, PERF_FAILURE,
    THREAD_INVOICE_PIPELINE, META_STAGE,
    STAGE_VALIDATION,
)

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:1b"

EXTRACTION_PROMPT = """You are an invoice data extraction assistant.
Extract all invoice fields from the text below and return only a valid JSON object.
No explanation, no markdown, no code fences, just the raw JSON.

Required JSON structure:
{{
  "invoice_id":    "string",
  "vendor_name":   "string",
  "vendor_id":     "string",
  "invoice_date":  "string — YYYY-MM-DD",
  "due_date":      "string — YYYY-MM-DD or empty",
  "currency":      "string — 3-letter code e.g. EUR",
  "line_items":    [{{"description": "string", "quantity": number, "unit_price": number, "line_total": number}}],
  "subtotal":      number,
  "vat_rate":      number,
  "vat_amount":    number,
  "invoice_total": number
}}

Invoice text:
{raw_text}
"""


def pdf_to_text(pdf_bytes: bytes) -> str:
    """Extract text from a digital PDF using pdfplumber."""
    pages_text = []
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
    return "\n\n--- PAGE BREAK ---\n\n".join(pages_text)


async def extract_with_ollama(raw_text: str) -> dict:
    """Send invoice text to local Ollama LLM and return structured JSON."""
    prompt = EXTRACTION_PROMPT.format(raw_text=raw_text[:4000])

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            OLLAMA_URL,
            json={
                "model":  OLLAMA_MODEL,
                "prompt": prompt,
                "stream": True,
                "options": {"temperature": 0.0},
            }
        )
        response.raise_for_status()

        full_response = ""
        async for line in response.aiter_lines():
            if line.strip():
                chunk = json.loads(line)
                full_response += chunk.get("response", "")
                if chunk.get("done", False):
                    break

    clean = re.sub(r"```(?:json)?|```", "", full_response).strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Ollama returned invalid JSON: {e}\nResponse was: {clean[:300]}"
        )


class InvoiceExtractor:
    """Orchestrates PDF extraction and LLM parsing into an InvoiceContext."""

    async def extract_from_pdf(self, pdf_bytes: bytes, pipeline_id: str = "") -> InvoiceContext:
        raw_text = pdf_to_text(pdf_bytes)
        if not raw_text.strip():
            raise ValueError("No text extracted from PDF.")
        return await self._build_context(raw_text, source="pdf", pipeline_id=pipeline_id)

    async def extract_from_text(self, raw_text: str, pipeline_id: str = "") -> InvoiceContext:
        return await self._build_context(raw_text, source="email", pipeline_id=pipeline_id)

    async def _build_context(self, raw_text: str, source: str, pipeline_id: str = "") -> InvoiceContext:
        """Send text to Ollama and map the result into an InvoiceContext."""
        ctx = InvoiceContext(source=source, raw_text=raw_text)
        if pipeline_id:
            ctx.pipeline_id = pipeline_id

        try:
            extracted = await extract_with_ollama(raw_text)
        except Exception as e:
            raise RuntimeError(f"Ollama is unavailable or failed: {e}")

        ctx.invoice_id = extracted.get("invoice_id", "")
        ctx.vendor_name = extracted.get("vendor_name", "")
        ctx.vendor_id = extracted.get("vendor_id", "")
        ctx.invoice_date = extracted.get("invoice_date", "")
        ctx.due_date = extracted.get("due_date", "")
        ctx.currency = str(extracted.get("currency", "")).upper()
        ctx.line_items = extracted.get("line_items", [])
        ctx.subtotal = float(extracted.get("subtotal", 0))
        ctx.vat_rate = float(extracted.get("vat_rate", 0))
        ctx.vat_amount = float(extracted.get("vat_amount", 0))
        ctx.invoice_total = float(extracted.get("invoice_total", 0))

        ctx.status = InvoiceStatus.EXTRACTED
        ctx.add_audit(
            agent="IngestionAgent",
            action="extraction_complete",
            detail=f"method=ollama/{OLLAMA_MODEL}, items={len(ctx.line_items)}, source={source}",
        )
        return ctx


class ReceiveAndExtractBehaviour(CyclicBehaviour):
    """Listens for incoming invoice messages and forwards extracted data to Validation Agent."""

    async def run(self):
        msg = await self.receive(timeout=10)
        if msg is None:
            return

        self.agent.log(f"[Ingestion] Received from {msg.sender}")

        try:
            body = msg.body
            if body.strip().startswith("{"):
                payload = json.loads(body)
                if payload.get("type") == "pdf":
                    pdf_bytes = base64.b64decode(payload["data"])
                    pipeline_id = payload.get("pipeline_id", "")
                    ctx = await self.agent.extractor.extract_from_pdf(pdf_bytes, pipeline_id)
                else:
                    ctx = await self.agent.extractor.extract_from_text(payload.get("text", body))
            else:
                ctx = await self.agent.extractor.extract_from_text(body)

            await self._forward_to_validation(ctx)

        except Exception as e:
            self.agent.log(f"[Ingestion] ERROR: {e}")
            err = Message(to=str(msg.sender))
            err.set_metadata("performative", PERF_FAILURE)
            err.body = f"Extraction failed: {e}"
            await self.send(err)

    async def _forward_to_validation(self, ctx: InvoiceContext):
        out = Message(to=AGENT_JIDS["validation"])
        out.set_metadata("performative", PERF_INFORM)
        out.set_metadata("thread", THREAD_INVOICE_PIPELINE)
        out.set_metadata(META_STAGE, STAGE_VALIDATION)
        out.body = ctx.to_json()
        await self.send(out)
        self.agent.log(f"[Ingestion] → Validation: {ctx.invoice_id} ({ctx.source})")


class IngestionAgent(Agent):
    """Entry point of the invoice pipeline. Accepts PDFs and plain text."""

    def log(self, msg: str):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    async def setup(self):
        self.log("[Ingestion] Starting up...")
        self.extractor = InvoiceExtractor()
        template = Template()
        template.set_metadata("performative", PERF_REQUEST)
        self.add_behaviour(ReceiveAndExtractBehaviour(), template)
        self.log("[Ingestion] Ready.")