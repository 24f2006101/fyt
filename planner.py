import json
import os
import re
import secrets

from dotenv import load_dotenv

from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1"
)

MODEL_NAME = "llama-3.3-70b-versatile"


def extract_evidence_ids(transcript):
    """
    Accept any bracketed evidence ID, for example:
    [ev_001], [E12], [log_abc], [metric_1]
    """
    return re.findall(r"\[([A-Za-z0-9_\-]+)\]", transcript)


def coerce_value(value, schema):
    expected = schema.get("type")

    if expected == "string":
        return str(value)

    if expected == "integer":
        return int(value)

    if expected == "number":
        return float(value)

    if expected == "boolean":
        if isinstance(value, str):
            return value.lower() == "true"
        return bool(value)

    if expected == "array":
        return value if isinstance(value, list) else [value]

    return value


def build_required_arguments(tool, transcript):
    schema = tool.get("inputSchema", {})
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    prompt = f"""
Fill the required arguments for this diagnostic tool using only facts
supported by the incident transcript.

Tool name:
{tool["name"]}

Tool description:
{tool.get("description", "")}

Input schema:
{json.dumps(schema, indent=2)}

Required argument names:
{json.dumps(required)}

Incident transcript:
{transcript}

Return only JSON in this exact shape:
{{
  "arguments": {{}}
}}
"""

    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "Return only valid JSON. Use exact values supported by the transcript."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        response_format={"type": "json_object"}
    )

    parsed = json.loads(completion.choices[0].message.content)
    arguments = parsed.get("arguments", {})

    cleaned = {}

    for key, value in arguments.items():
        if key not in properties:
            continue

        cleaned[key] = coerce_value(value, properties[key])

    for key in required:
        if key not in cleaned:
            raise ValueError(f"Missing required argument: {key}")

    return cleaned


def plan_incident(body):
    incident = body["incident"]
    catalog = body["toolCatalog"]
    policy = body["policy"]

    evidence_ids = extract_evidence_ids(incident["transcript"])

    planning_prompt = f"""
You are an incident triage planner.

Choose exactly one root cause from allowedRootCauses.
Cite 2 to 4 evidence IDs that support it.
Choose 1 to 3 diagnostic tools from the tool catalog.
For each chosen diagnostic tool, cite at least one evidence ID.

Return only JSON in this exact shape:
{{
  "rootCause": "one value from allowedRootCauses",
  "evidence": ["id1", "id2"],
  "diagnostics": [
    {{
      "toolName": "exact tool name from catalog",
      "evidence": ["id1"]
    }}
  ]
}}

allowedRootCauses:
{json.dumps(incident["allowedRootCauses"])}

Evidence IDs:
{json.dumps(evidence_ids)}

Tool catalog:
{json.dumps(catalog)}

Policy:
{json.dumps(policy)}

Incident:
{json.dumps(incident)}
"""

    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "system",
                "content": "You are a careful incident diagnosis planner. Return only valid JSON."
            },
            {
                "role": "user",
                "content": planning_prompt
            }
        ],
        response_format={"type": "json_object"}
    )

    plan = json.loads(completion.choices[0].message.content)

    root_cause = plan["rootCause"]
    diagnosis_evidence = plan["evidence"][:4]

    if root_cause not in incident["allowedRootCauses"]:
        raise ValueError("Model chose an unsupported root cause")

    if not (2 <= len(diagnosis_evidence) <= 4):
        raise ValueError("Diagnosis must cite 2 to 4 evidence IDs")

    for evidence_id in diagnosis_evidence:
        if evidence_id not in evidence_ids:
            raise ValueError(f"Unknown evidence ID: {evidence_id}")

    dispatches = []

    for item in plan.get("diagnostics", [])[:3]:
        tool_name = item["toolName"]

        tool = next(
            (t for t in catalog if t["name"] == tool_name),
            None
        )

        if tool is None:
            continue

        cited = [
            evidence for evidence in item.get("evidence", [])
            if evidence in diagnosis_evidence
        ]

        if not cited:
            cited = [diagnosis_evidence[0]]

        arguments = build_required_arguments(
            tool,
            incident["transcript"]
        )

        trace_id = secrets.token_hex(16)
        client_span_id = secrets.token_hex(8)

        dispatches.append({
            "actionId": "diag_" + secrets.token_hex(8),
            "callId": "call_" + secrets.token_hex(8),
            "phase": "diagnostic",
            "toolName": tool_name,
            "arguments": arguments,
            "evidence": cited[:1],
            "attempt": 1,
            "traceparent": f"00-{trace_id}-{client_span_id}-01"
        })

    if not dispatches:
        raise ValueError("No valid diagnostic dispatch was produced")

    return {
        "runId": body["runId"],
        "status": "waiting",
        "diagnosis": {
            "rootCause": root_cause,
            "evidence": diagnosis_evidence
        },
        "dispatches": dispatches,
        "approvals": []
    }
