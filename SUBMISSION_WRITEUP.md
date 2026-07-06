 # Submission Write-Up: SwimSafe AI Agent 🏊

## Problem Statement
Swimming is a fun and healthy activity, but chemical imbalances and sanitation issues in pool water can lead to serious health concerns. While general guidelines exist, average swimmers do not know how to interpret readings (chlorine, pH, CYA) or understand how those readings impact them personally. A pool safe for a healthy adult could cause respiratory flares in asthmatics, severe eczema breakouts, or eye irritation in sensitive individuals. SwimSafe AI solves this by bridging the gap between raw chemical metrics and individual health/profile considerations to provide smart, personalized safety verdicts.

## Solution Architecture
SwimSafe AI is built on ADK 2.0 utilizing a graph-based workflow. The user inputs pool chemistry readings and swimmer health profiles, which follow this path:
1. **Security Checkpoint**: Validates inputs, scrubs PII (emails/phone numbers), detects prompt injection, and flags physical anomalies (e.g. negative readings).
2. **Orchestrator Agent**: Delegates specialized checks via `AgentTool` to:
   - **Pool Analyzer Agent**: Connects to the local stdio MCP server to diagnose chlorine/pH levels, check guidelines, and calculate LSI (water stability).
   - **Swimmer Safety Analyst Agent**: Assesses risk levels and creates personalized guidance for each swimmer.
3. **HITL (Human-in-the-Loop) Checkpoint**: Pauses execution and requests confirmation via `RequestInput` if overall pool conditions are flagged as dangerously unsafe (e.g. chlorine > 10.0 ppm or a contamination incident is active).
4. **Final Response**: Formats all results into a structured, highly readable Markdown report for display in the playground UI.

## Concepts Used
- **ADK 2.0 Workflows**: Graph topology defining nodes and routed edges (`START` -> `security_checkpoint` -> `orchestrator` -> `hitl_checkpoint` -> `final_response`).
- **LlmAgent**: Used for specialized sub-agents with strict `output_schema` and distinct roles.
- **AgentTool**: Enables the Orchestrator to delegate task execution dynamically to sub-agents.
- **MCP Server (Model Context Protocol)**: Houses domain-specific logic such as LSI calculations and chemical guidelines in a decoupled Python server.
- **PII Scrubbing & Security Node**: Secures prompt boundaries and data inputs before reaching LLM layers.
- **RequestInput (HITL)**: Persists session contexts and resumes cleanly when dangerous pool conditions demand confirmation.

## Security Design
- **PII Redaction**: Email and phone number patterns are intercepted and redacted (`[EMAIL_REDACTED]`, `[PHONE_REDACTED]`) at the first node to protect user privacy.
- **Injection Detection**: Scans for standard system instructions bypass keywords, routing violators to a blocked `security_incident_handler` sink.
- **Validation Guard**: Restricts logically impossible negative inputs (e.g., pH < 0) before LLM queries.
- **Structured Audit Logging**: Generates JSON audit logs for tracking clearance, violations, and HITL overrides.

## MCP Server Design
The MCP server exposes 3 main tools:
1. `get_chemical_guidelines()`: Pulls official CDC/EPA guidelines.
2. `diagnose_water_issues(clarity, ph, chlorine)`: Uses hardcoded logic to diagnose problems and suggest chemical adjustments.
3. `calculate_lsi(...)`: Calculates the Langelier Saturation Index to identify scaling or corrosive water.

## HITL Flow
If a pool has dangerous chemical settings, SwimSafe AI halts the report generation and prompts:
> `⚠️ DANGER WARNING: The pool conditions are flagged as DANGEROUS! Do you wish to override this warning and show personal swimmer advice anyway? (Enter 'yes' to proceed, or 'no' to abort):`

If the user responds with 'no', the swim safety checks are canceled and a manager alert is generated.

## Impact / Value Statement
SwimSafe AI increases public health awareness, prevents waterborne illnesses/skin flares, and automates pool chemistry diagnostics. It helps home pool owners keep their water balanced and keeps shared-pool managers alert to safety concerns.
