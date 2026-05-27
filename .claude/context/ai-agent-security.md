# AI Agent Security — Reviewer Cheat Sheet

Condensed from the [OWASP AI Agent Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/AI_Agent_Security_Cheat_Sheet.html). Loaded only when the diff touches agent / tool / prompt / LLM-SDK code.

## 1. Tool least-privilege
- Each tool gets minimum permissions; read-only by default.
- Separate tool sets per trust tier. No "god tool" with shell + network + filesystem.
- Allowlists for permitted paths/operations. Block `*.env`, `*.key`, `*.pem`, `*secret*`.
- Sensitive operations (delete, payment, send-email) require explicit authorization.
- Sanitize tool params before logging/displaying — never log raw user input verbatim.

## 2. Prompt-injection defense
- Treat **all** external data as hostile: user input, retrieved docs, API responses, scraped web content, emails.
- Use clear delimiters between system instructions and untrusted data (e.g. `<user_data>...</user_data>`).
- Filter known injection patterns before insertion.
- For high-risk content, use a separate sanitization LLM call to summarize/validate.
- Never let untrusted content set tool-use decisions directly — gate through the planner.

## 3. Memory & context hygiene
- Validate/sanitize before write. Don't trust your own past output.
- Per-user/session isolation; no shared memory across tenants.
- Expiration (24h default) and size caps (~100 items, ~5000 chars/item).
- Redact PII (SSN, CC, passwords, API keys) before persistence.
- Checksum memory blobs for integrity verification.

## 4. Human-in-the-loop
- Classify actions: `LOW` / `MEDIUM` / `HIGH` / `CRITICAL`.
- Auto-approve only `LOW` (read-only, idempotent queries).
- `MEDIUM+` queues for human approval with a preview of the exact action and parameters.
- Audit trail records what the agent decided and what the human chose.
- Provide an interrupt + rollback path.

## 5. Output validation
- Schema-validate every agent output (Pydantic / JSON Schema).
- PII filter on responses.
- Detect exfiltration patterns: large outbound payloads, suspicious URL encoding, base64 of internal data.
- Rate-limit (~100 calls / 60s baseline).
- Validate tool-call names and args against allowlists before execution.

## 6. Observability
- Log every decision, tool call, and outcome — to an immutable store.
- Redact secrets from logs (passwords, API keys, tokens, full PII).
- Alert on: tool-call rate >30/min, ≥5 failed tool calls, any injection detection, ≥3 sensitive-data accesses, session cost >$10.
- Track token usage and cost per session — denial-of-wallet is a real attack class.

## 7. Multi-agent
- Trust levels: `UNTRUSTED` / `INTERNAL` / `PRIVILEGED` / `SYSTEM`.
- Allowlist message recipients per agent.
- Sign + verify inter-agent messages.
- Message TTL (~5 min) prevents replay.
- Circuit breakers (5 failures → open) prevent cascading failures.
- Strip system fields from messages originating from low-trust agents.

## 8. Data protection
- Classify: `PUBLIC` / `INTERNAL` / `CONFIDENTIAL` / `RESTRICTED`.
- `RESTRICTED` fully redacted; `CONFIDENTIAL` partially masked.
- Minimize sensitive data in context — pass IDs, fetch on demand.
- Encryption at rest and in transit.
- GDPR/CCPA retention + deletion enforced.

## Red flags (instant findings)

```python
# CRITICAL — shell exec with interpolated user input
os.system(f"grep {user_query} log.txt")

# CRITICAL — unvalidated tool dispatch
tool_name = llm_response["tool"]
TOOLS[tool_name](**llm_response["args"])

# HIGH — secret logged
log.info(f"calling API with key={api_key}")

# HIGH — no allowlist
def read_file(path: str) -> str:
    return open(path).read()  # path-traversal trivial

# HIGH — untrusted content concatenated into system prompt
prompt = f"You are helpful.\n\nUser doc: {scraped_html}"

# MEDIUM — unbounded loop, denial-of-wallet
while not done:
    response = llm.complete(prompt)

# MEDIUM — no schema validation on agent output
result = json.loads(llm_response)  # trust whatever shape it returned
```

## Threat classes to keep in mind
Direct/indirect prompt injection · tool abuse / privilege escalation · data exfiltration · memory poisoning · goal hijacking · excessive autonomy · cascading multi-agent failure · LLM config tampering · denial-of-wallet · sensitive-data exposure · supply-chain compromise of tools/APIs.
