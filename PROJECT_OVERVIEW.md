# SwimSafe AI: Project Overview

SwimSafe AI is an agentic advisor that checks pool chemistry against swimmer health profiles for personalized safety verdicts and guidance.

## The Problem
Maintaining pool safety goes beyond reading chemical values off a test strip. Standard guidelines do not account for individual health profiles. A pool that is perfectly safe for a healthy adult might trigger severe asthma in a sensitive toddler due to high chloramines, or irritate a swimmer with skin eczema. Additionally, pool managers need immediate alerts if chemistry becomes hazardous.

## Key Features
*   **Security Checkpoint**: Redacts PII (emails/phones) and blocks malicious prompt injections or physically impossible readings (e.g. negative pH).
*   **Orchestrator & Sub-agents**: The workflow coordinates a *Pool Analyzer Agent* (handling chemistry guidelines) and a *Swimmer Safety Analyst Agent* (assessing swimmer risk factors).
*   **Custom MCP Server**: Exposes three core stdio tools: retrieving chemical guidelines, diagnosing water issues, and mathematically calculating the Langelier Saturation Index (LSI).
*   **Human-In-The-Loop (HITL) Checkpoint**: Suspends graph execution if chemistry is critically unbalanced, prompting the user to override or cancel.
*   **Vanilla Web Dashboard**: Provides a sleek dark-mode interface for entry of pool readings and swimmer profiles.

## Technical Stack
*   **Orchestration**: Python + Google ADK 2.0 Workflow API
*   **Core Model**: Gemini 2.5 Flash
*   **Verification**: Pydantic schemas for data boundaries
*   **Backend Hosting**: FastAPI & Uvicorn
*   **Database/Storage**: InMemorySessionService for state tracking
*   **Frontend**: Vanilla HTML / CSS / JavaScript
*   **Dependency Management**: uv
