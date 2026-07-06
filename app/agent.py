import re
import json
import logging
from typing import Any, List, Optional
from pydantic import BaseModel, Field

from google.adk.workflow import Workflow, START, node, Edge
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool, McpToolset
from google.adk.tools.mcp_tool.mcp_toolset import StdioConnectionParams
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.genai import types

from app.config import config
from mcp import StdioServerParameters

# Setup audit logger
logger = logging.getLogger("pool-sense-audit")
logger.setLevel(logging.INFO)
# Standard output handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(ch)

# ---------------------------------------------------------
# Schemas and Models
# ---------------------------------------------------------

class PoolReadings(BaseModel):
    free_chlorine: float = Field(description="Free chlorine level in ppm. Safe range: 1.0 - 3.0 ppm. Unsafe for swimming if >10.0 ppm or <1.0 ppm.")
    ph: float = Field(description="pH level of the water. Safe range: 7.2 - 7.8. Irritating/corrosive if <7.0 or >7.8.")
    cyanuric_acid: float = Field(description="Cyanuric acid / stabilizer level in ppm. Ideal: 30 - 50 ppm. Max: 100 ppm.")
    water_clarity: str = Field(description="Clarity of water: 'clear', 'cloudy', or 'turbid'.")
    strong_chemical_smell: bool = Field(description="True if there is a strong chemical/chlorine smell.")
    indoor_outdoor: str = Field(description="Indoor or outdoor pool type: 'indoor' or 'outdoor'.")
    recent_rain_heavy_use: bool = Field(description="True if there was recent heavy rain or heavy swimmer load.")
    contamination_incident: bool = Field(description="True if there was a recent contamination incident (fecal, chemical spill, etc.).")

class SwimmerProfile(BaseModel):
    name: str = Field(description="Name or identifier of the swimmer.")
    age_group: str = Field(description="Age group: 'toddler', 'child', 'adult', 'senior'.")
    swimming_ability: str = Field(description="Swimming ability: 'weak', 'average', 'strong'.")
    allergies: Optional[str] = Field(None, description="Known allergies relevant to pool water (e.g. chlorine allergy, skin rashes).")
    asthma_breathing_sensitivity: bool = Field(description="True if swimmer has asthma or other respiratory sensitivities.")
    sensitive_skin_eczema: bool = Field(description="True if swimmer has eczema, psoriasis, or sensitive skin.")
    eye_sensitivity: bool = Field(description="True if swimmer's eyes are highly sensitive to pool water.")
    open_cuts_wounds: bool = Field(description="True if swimmer has open cuts, wounds, or stitches.")
    recent_illness: bool = Field(description="True if swimmer has had stomach illness or diarrhea in the past 2 weeks.")

class PoolAssessment(BaseModel):
    chemical_safety: str = Field(description="Assessment of chemical safety: 'safe', 'warning', 'danger'")
    chlorine_status: str = Field(description="Chlorine evaluation (e.g., too low, normal, too high, unsafe)")
    ph_status: str = Field(description="pH evaluation (e.g., acidic, normal, basic)")
    stabilizer_status: str = Field(description="Cyanuric acid evaluation")
    clarity_sanitation_status: str = Field(description="Water clarity and general sanitation assessment")
    key_warnings: List[str] = Field(description="List of specific chemical/water warnings")
    maintenance_recommendations: List[str] = Field(description="Actionable maintenance steps for pool balancing")

class SwimmerSafetyVerdict(BaseModel):
    swimmer_name: str = Field(description="Name of the swimmer")
    verdict: str = Field(description="Safety verdict: 'safe', 'caution', 'not recommended'")
    risks: List[str] = Field(description="Identified risks for this swimmer based on their health profile and pool status")
    guidance: List[str] = Field(description="Personalized safety guidance/precautions (e.g., wear goggles, wash immediately, do not swim)")

class SwimmerSafetyReport(BaseModel):
    swimmer_verdicts: List[SwimmerSafetyVerdict] = Field(description="Individual safety verdicts for each swimmer")

class PoolSenseOutput(BaseModel):
    overall_verdict: str = Field(description="Overall group verdict: 'safe', 'caution', or 'not recommended'")
    pool_analysis: PoolAssessment = Field(description="Analysis of the pool conditions")
    swimmer_verdicts: List[SwimmerSafetyVerdict] = Field(description="Verdicts for all listed swimmers")
    manager_alert_required: bool = Field(description="True if conditions require immediate pool manager action")
    manager_alert_message: Optional[str] = Field(None, description="Draft alert message for the manager")

# ---------------------------------------------------------
# MCP Toolset Setup
# ---------------------------------------------------------

mcp_params = StdioServerParameters(
    command="uv",
    args=["run", "python", "-m", "app.mcp_server"],
)
mcp_connection = StdioConnectionParams(server_params=mcp_params)
mcp_toolset = McpToolset(connection_params=mcp_connection)

# ---------------------------------------------------------
# Sub-Agents
# ---------------------------------------------------------

pool_analyzer = LlmAgent(
    name="pool_analyzer",
    model=config.model,
    instruction="""
    You are the Pool Analyzer Agent. Analyze the pool's chemical and water conditions.
    Use the available MCP tools like `get_chemical_guidelines` and `diagnose_water_issues` to cross-reference official standards.
    If the LSI needs to be checked, call the `calculate_lsi` tool.
    Output a structured PoolAssessment detailing the safety category ('safe', 'warning', 'danger'), chemical levels status, clarity, warnings, and maintenance recommendations.
    """,
    description="Analyzes pool metrics (chlorine, pH, stabilizer, clarity, smell, location) against health guidelines.",
    tools=[mcp_toolset],
    output_schema=PoolAssessment,
)

swimmer_safety_analyst = LlmAgent(
    name="swimmer_safety_analyst",
    model=config.model,
    instruction="""
    You are the Swimmer Safety Analyst Agent. Evaluate the safety of pool water conditions for a list of swimmers based on their individual health/profile details and the pool assessment.
    For each swimmer, provide:
    1. Verdict: 'safe' (ideal conditions), 'caution' (minor risks, requires precautions), or 'not recommended' (swimming is contraindicated).
    2. Risks: Specific risk factors (e.g. acidic water irritating open cuts/wounds, low chlorine spreading bacteria if swimmer has recent illness, chloramines triggering asthma).
    3. Guidance: Actionable precautions (e.g. wear nose clips/goggles, apply barrier cream, limit swim time to 15 mins, do not swim).
    Output a structured SwimmerSafetyReport.
    """,
    description="Evaluates health/profile risks for each swimmer based on the pool chemistry analysis.",
    output_schema=SwimmerSafetyReport,
)

# ---------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------

orchestrator = LlmAgent(
    name="orchestrator",
    model=config.model,
    instruction="""
    You are the SwimSafe AI Orchestrator. You help users determine if a pool is safe for them or their group.
    
    1. Delegate pool chemistry analysis to the pool_analyzer tool using the pool readings provided in the input.
    2. Delegate swimmer risk assessment to the swimmer_safety_analyst tool using the pool assessment results and swimmer profiles.
    3. Synthesize the reports:
       - The overall group verdict should be:
         * 'not recommended' if ANY swimmer is 'not recommended' or the pool chemistry is 'danger'.
         * 'caution' if any swimmer has a 'caution' verdict and none are 'not recommended'.
         * 'safe' if all swimmers are 'safe'.
       - Check if a pool manager alert is required (e.g., chlorine < 1.0, pH < 7.0 or > 7.8, contamination incident, or turbid water). If so, draft a concise alert message.
    
    Assemble and output the final structured PoolSenseOutput.
    """,
    description="Coordinates pool water and swimmer safety evaluations.",
    tools=[AgentTool(pool_analyzer), AgentTool(swimmer_safety_analyst)],
    output_schema=PoolSenseOutput,
    output_key="orchestrator_output",
    rerun_on_resume=False,
)

# ---------------------------------------------------------
# Workflow Nodes
# ---------------------------------------------------------

def audit_log(severity: str, action: str, details: dict):
    """Log structured JSON audit entries for security and compliance."""
    log_entry = {
        "severity": severity,
        "action": action,
        "details": details
    }
    logger.info(f"AUDIT_LOG: {json.dumps(log_entry)}")

def security_checkpoint(ctx: Context, node_input: types.Content):
    """
    Security check for PII scrubbing, injection detection, and input constraints.
    """
    # Check if we are resuming from a HITL pause. If so, bypass orchestrator and route directly to hitl_checkpoint
    if ctx.resume_inputs and "confirm_override" in ctx.resume_inputs:
        user_response = ctx.resume_inputs["confirm_override"]
        return Event(output=user_response, route="resume_route")

    # 1. Extract text from the content
    text = ""
    if node_input and node_input.parts:
        text = " ".join(part.text for part in node_input.parts if part.text)
    
    # 2. PII Scrubbing (Scrub phone numbers and emails)
    email_pattern = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    phone_pattern = r'\+?\d{1,4}?[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}'
    
    scrubbed_text = re.sub(email_pattern, "[EMAIL_REDACTED]", text)
    scrubbed_text = re.sub(phone_pattern, "[PHONE_REDACTED]", scrubbed_text)
    
    # 3. Prompt Injection Detection
    injection_keywords = [
        "ignore previous instructions", "bypass rules", "system instructions", 
        "system prompt", "jailbreak", "dan mode", "you must now act as"
    ]
    
    has_injection = any(kw in text.lower() for kw in injection_keywords)
    
    if has_injection:
        audit_log("CRITICAL", "PROMPT_INJECTION_DETECTED", {"input_preview": text[:100]})
        return Event(output="Security Checkpoint Block: Potential prompt injection attempt detected.", route="SECURITY_EVENT")
    
    # 4. Domain-specific validation (Invalid metrics guard)
    # Simple check for negative numbers representing ph or chlorine levels which are physically impossible.
    negative_val_pattern = r'(?:ph|chlorine|ppm|acid|clarity)\s*(?:is|=)\s*-\d+'
    if re.search(negative_val_pattern, text.lower()):
        audit_log("WARNING", "INVALID_INPUT_METRICS", {"input_preview": text[:100]})
        return Event(output="Validation Check: Invalid negative values provided for pool readings.", route="SECURITY_EVENT")

    audit_log("INFO", "INPUT_CLEARED", {"pii_scrubbed": scrubbed_text != text})
    return Event(output=scrubbed_text, route="clean")

def security_incident_handler(node_input: str) -> str:
    """Handle blocked/unsafe requests gracefully and audit log it."""
    audit_log("WARNING", "INCIDENT_HANDLED", {"message": node_input})
    return f"🚫 Request Blocked: {node_input}"

async def hitl_checkpoint(ctx: Context, node_input: Any):
    """
    Human-in-the-Loop node. Pauses if pool chemistry is critically dangerous to ask for confirmation.
    """
    # If resuming, node_input might be the string user_response, retrieve the actual analysis from state
    orchestrator_output = ctx.state.get("orchestrator_output")
    if not orchestrator_output and isinstance(node_input, dict):
        orchestrator_output = node_input

    if not orchestrator_output:
        # Fallback if no analysis exists
        yield Event(output="Error: No prior safety analysis found on resume.")
        return

    pool_analysis = orchestrator_output.get("pool_analysis", {})
    chemical_safety = pool_analysis.get("chemical_safety", "safe")
    warnings = pool_analysis.get("key_warnings", [])
    
    # Check if pool conditions are labeled as DANGER or have serious contamination warnings
    is_dangerous = (chemical_safety == "danger") or any("contamination" in w.lower() for w in warnings)
    
    if is_dangerous:
        if not ctx.resume_inputs or "confirm_override" not in ctx.resume_inputs:
            # Yield RequestInput to pause and ask for confirmation
            warning_list = ", ".join(warnings) if warnings else "extreme chemical imbalance"
            yield RequestInput(
                interrupt_id="confirm_override",
                message=f"⚠️ DANGER WARNING: The pool conditions are flagged as DANGEROUS! Warnings: {warning_list}. Do you wish to override this warning and show personal swimmer advice anyway? (Enter 'yes' to proceed, or 'no' to abort):"
            )
            return
        
        user_response = ctx.resume_inputs["confirm_override"].strip().lower()
        if user_response != "yes":
            # Override aborted. Update the verdicts to block swimming
            aborted_output = {
                "overall_verdict": "not recommended",
                "pool_analysis": pool_analysis,
                "swimmer_verdicts": [
                    {
                        "swimmer_name": sv.get("swimmer_name", "Swimmer"),
                        "verdict": "not recommended",
                        "risks": ["Pool safety check aborted by user due to extreme hazard."],
                        "guidance": ["Do not enter the pool. Extremely hazardous conditions."]
                    } for sv in orchestrator_output.get("swimmer_verdicts", [])
                ],
                "manager_alert_required": True,
                "manager_alert_message": "Swimming aborted. Extremely hazardous pool chemistry detected."
            }
            audit_log("INFO", "HITL_OVERRIDE_ABORTED", {"warnings": warnings})
            yield Event(output=aborted_output)
            return
            
        audit_log("WARNING", "HITL_OVERRIDE_APPROVED", {"warnings": warnings})

    yield Event(output=orchestrator_output)

def final_response(node_input: dict):
    """
    Formulate the final, highly styled output report for display in the Web UI.
    """
    if isinstance(node_input, str):
        # Handles security blocks or direct string inputs
        yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=node_input)]))
        yield Event(output=node_input)
        return

    output_text = "## 🏊 SwimSafe AI Safety Report\n\n"
    
    if "overall_verdict" in node_input:
        verdict = node_input["overall_verdict"].upper()
        emoji = "✅" if verdict == "SAFE" else "⚠️" if verdict == "CAUTION" else "🚨"
        output_text += f"### Overall Verdict: {emoji} **{verdict}**\n\n"
        
        # Pool chemistry assessment
        pool_analysis = node_input.get("pool_analysis", {})
        output_text += "#### 📊 Pool Water Chemistry Assessment\n"
        output_text += f"- **Chemical Safety Status**: **{pool_analysis.get('chemical_safety', 'N/A').upper()}**\n"
        output_text += f"- **Chlorine Level**: {pool_analysis.get('chlorine_status', 'N/A')}\n"
        output_text += f"- **pH Level**: {pool_analysis.get('ph_status', 'N/A')}\n"
        output_text += f"- **Stabilizer (CYA)**: {pool_analysis.get('stabilizer_status', 'N/A')}\n"
        output_text += f"- **Water Clarity**: {pool_analysis.get('clarity_status', 'N/A')}\n"
        
        # LSI
        lsi_info = pool_analysis.get("lsi_index_info", {})
        lsi_val = lsi_info.get("lsi_value")
        if lsi_val is not None:
            output_text += f"- **Langelier Saturation Index (LSI)**: `{lsi_val}` ({lsi_info.get('water_status', 'balanced')})\n"
            
        warnings = pool_analysis.get("key_warnings", [])
        if warnings:
            output_text += "\n⚠️ **Warnings:**\n"
            for w in warnings:
                output_text += f"- {w}\n"
                
        recs = pool_analysis.get("maintenance_recommendations", [])
        if recs:
            output_text += "\n🛠️ **Maintenance Recommendations:**\n"
            for r in recs:
                output_text += f"- {r}\n"
                
        # Swimmer verdicts
        output_text += "\n#### 👥 Swimmer Safety Reports\n"
        for sv in node_input.get("swimmer_verdicts", []):
            s_verdict = sv.get("verdict", "N/A").upper()
            s_emoji = "✅" if s_verdict == "SAFE" else "⚠️" if s_verdict == "CAUTION" else "🚨"
            output_text += f"##### {sv.get('swimmer_name', 'Swimmer')}: {s_emoji} {s_verdict}\n"
            
            risks = sv.get("risks", [])
            if risks:
                output_text += "  - *Risks*: " + ", ".join(risks) + "\n"
            guidance = sv.get("guidance", [])
            if guidance:
                output_text += "  - *Guidance*:\n"
                for g in guidance:
                    output_text += f"    - {g}\n"
                    
        # Manager Alert
        if node_input.get("manager_alert_required"):
            output_text += f"\n🚨 **Manager Alert Flagged:** {node_input.get('manager_alert_message', 'Alert')}\n"
    else:
        output_text += f"Unexpected response format: {node_input}"
        
    yield Event(
        content=types.Content(
            role='model',
            parts=[types.Part.from_text(text=output_text)]
        )
    )
    yield Event(output=node_input)

# ---------------------------------------------------------
# Workflow Definitions
# ---------------------------------------------------------

from google.adk.apps import App

root_agent = Workflow(
    name="pool_sense",
    edges=[
        ('START', security_checkpoint),
        (security_checkpoint, {"clean": orchestrator, "SECURITY_EVENT": security_incident_handler, "resume_route": hitl_checkpoint}),
        (orchestrator, hitl_checkpoint),
        (hitl_checkpoint, final_response),
        (security_incident_handler, final_response),
    ],
    description="A multi-agent personalized swim safety advisor.",
)

app = App(
    root_agent=root_agent,
    name="app",
)


