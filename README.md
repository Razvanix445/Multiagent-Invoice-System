# Invoxa - Multiagent Invoice System
### SPADE + XMPP + Ollama

An automated invoice processing system built with autonomous agents. Upload a PDF invoice and watch it flow through ingestion, validation, decision-making, notification, and audit, all handled by independent agents communicating over XMPP.

---

[Invoxa Demo](https://github.com/Razvanix445/Multiagent-Invoice-System/blob/main/invoxa-demo.mp4)

## Architecture
 
The system is built as a **sequential multi-agent pipeline** where each agent owns exactly one responsibility. Agents communicate exclusively via XMPP messages using FIPA ACL performatives. They never call each other directly, which means any agent can be replaced, scaled, or restarted independently.
 
```
PDF Upload → Ingestion Agent → Validation Agent → Decision Agent → Communication Agent → Audit Agent
               (Ollama LLM)     (6 checks)         (rule engine)    (email + Slack)       (JSONL log)
                                                         │
                                                    ┌────┴────┐
                                               Communication  Audit
                                               Agent          Agent
                                               (notifies)     (always logs)
```
 
The Decision Agent fans out to both the Communication Agent and Audit Agent in parallel. Audit logging is never dependent on notification succeeding.
 
---
 
## Agent design — PEAS framework
 
Each agent is formally described using the **PEAS framework** (Performance, Environment, Actuators, Sensors) from Russell & Norvig's *Artificial Intelligence: A Modern Approach*. This is the standard way to specify rational agents in academic and enterprise AI systems.
 
| Agent | Performance | Environment | Actuators | Sensors |
|---|---|---|---|---|
| **Ingestion** | Extraction accuracy, field coverage | PDF files, email text, XMPP bus | Sends structured InvoiceContext to Validation Agent | Receives REQUEST messages with file payloads |
| **Validation** | Zero false positives, zero false negatives | InvoiceContext, vendor registry, invoice ID store | Forwards ValidationReport to Decision Agent | Receives INFORM messages, reads invoice fields |
| **Decision** | Correct classification rate, auditability | InvoiceContext + ValidationReport, business rules | Sets decision field, routes to Communication + Audit | Reads validation result, invoice total, vendor |
| **Communication** | Notification delivery rate, message relevance | Decided InvoiceContext, email server, Slack API | Sends email and Slack notifications | Receives INFORM messages, reads decision field |
| **Audit** | 100% capture rate, log integrity | All InvoiceContext messages, file system | Writes JSONL records, notifies web dashboard | Receives INFORM from Decision + Communication agents |
 
---
 
## Agent communication — FIPA ACL
 
Agents communicate using **FIPA ACL** (Foundation for Intelligent Physical Agents — Agent Communication Language), the industry standard for multi-agent systems. Each message carries a **performative** that declares the intent of the message:
 
| Performative | Meaning | Used when |
|---|---|---|
| `REQUEST` | "Please do this task" | API Gateway → Ingestion Agent |
| `INFORM` | "Here is information" | Between all pipeline agents |
| `FAILURE` | "Something went wrong" | Any agent reporting an error |
 
Messages are routed by **stage metadata** — each message is tagged with the pipeline stage it belongs to (e.g. `stage=validation`), so agents only process messages intended for them even though all messages travel over the same XMPP bus.

---

## Requirements

- Python 3.10
- SPADE 3.3.2
- Docker Desktop (for ejabberd XMPP server)
- Ollama (https://ollama.com)

Run these commands into the terminal if working with conda:

`conda create -n spade-env python=3.10` \
`conda activate spade-env` \
`pip install spade==3.3.2`

Note: Conda must be downloaded from anaconda.com/download

---

## First-time setup

### 1. Clone the project and create a virtual environment

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Mac/Linux
pip install -r requirements.txt
```

### 2. Pull the Ollama model

```bash
ollama pull llama3.2:1b
```

### 3. Start ejabberd

```bash
docker compose up -d
```

### 4. Register all agent accounts

```bash
docker exec -it multiagent-invoice-system-ejabberd-1 ejabberdctl register ingestion_agent localhost invoice123
docker exec -it multiagent-invoice-system-ejabberd-1 ejabberdctl register validation_agent localhost invoice123
docker exec -it multiagent-invoice-system-ejabberd-1 ejabberdctl register decision_agent localhost invoice123
docker exec -it multiagent-invoice-system-ejabberd-1 ejabberdctl register communication_agent localhost invoice123
docker exec -it multiagent-invoice-system-ejabberd-1 ejabberdctl register audit_agent localhost invoice123
docker exec -it multiagent-invoice-system-ejabberd-1 ejabberdctl register orchestrator localhost invoice123
docker exec -it multiagent-invoice-system-ejabberd-1 ejabberdctl register api_gateway localhost invoice123
```

> You only need to do this once. Accounts persist across restarts thanks to the Docker volume in `docker-compose.yml`.

---

## Running the system

### Option A — one double-click (Windows)

```
start.bat
```

This starts everything automatically and opens the dashboard in your browser.

### Option B — manually (3 terminals)

**Terminal 1** — start the agents:
```bash
.venv\Scripts\python.exe main.py
```

**Terminal 2** — start the web dashboard:
```bash
.venv\Scripts\uvicorn.exe api.main:app --port 8000
```

**Terminal 3** — Ollama runs automatically in the background. If not:
```bash
ollama serve
```

Then open **http://127.0.0.1:8000** in your browser.

---

## Using the dashboard

1. Drop a PDF invoice into the upload zone
2. Click **Process Invoice**
3. Watch the pipeline stages update in real time
4. Click any row in the audit history to see full invoice details

---

## Troubleshooting

**Accounts already exist error**

If agents fail to connect, unregister and re-register them:

```bash
docker exec multiagent-invoice-system-ejabberd-1 ejabberdctl unregister ingestion_agent localhost
docker exec multiagent-invoice-system-ejabberd-1 ejabberdctl unregister validation_agent localhost
docker exec multiagent-invoice-system-ejabberd-1 ejabberdctl unregister decision_agent localhost
docker exec multiagent-invoice-system-ejabberd-1 ejabberdctl unregister communication_agent localhost
docker exec multiagent-invoice-system-ejabberd-1 ejabberdctl unregister audit_agent localhost
docker exec multiagent-invoice-system-ejabberd-1 ejabberdctl unregister orchestrator localhost
docker exec multiagent-invoice-system-ejabberd-1 ejabberdctl unregister api_gateway localhost
```

---

## Decision logic

| Condition | Outcome |
|---|---|
| Validation failed | Rejected |
| Total > €10,000 | Escalated → manager |
| Total > €1,000 | Escalated → finance team |
| Validation warnings | Escalated → finance team |
| All clear | Auto-approved |

Thresholds are configurable in `config.py`.
