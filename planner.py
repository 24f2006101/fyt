import re
import secrets


def extract_evidence_ids(transcript):
    return re.findall(r"\[(ev_[A-Za-z0-9_\-]+)\]", transcript)


def plan_incident(body):
    incident = body["incident"]
    catalog = body["toolCatalog"]

    root_cause = incident["allowedRootCauses"][0]

    evidence_ids = extract_evidence_ids(incident["transcript"])
    diagnosis_evidence = evidence_ids[:2]

    diagnostic_tool = next(
        tool for tool in catalog
        if tool["name"] == "query_metrics"
    )

    trace_id = secrets.token_hex(16)
    client_span_id = secrets.token_hex(8)

    dispatch = {
        "actionId": "diag_" + secrets.token_hex(8),
        "callId": "call_" + secrets.token_hex(8),
        "phase": "diagnostic",
        "toolName": diagnostic_tool["name"],
        "arguments": {
            "service": incident["service"]
        },
        "evidence": [diagnosis_evidence[0]],
        "attempt": 1,
        "traceparent": f"00-{trace_id}-{client_span_id}-01"
    }

    return {
        "runId": body["runId"],
        "status": "waiting",
        "diagnosis": {
            "rootCause": root_cause,
            "evidence": diagnosis_evidence
        },
        "dispatches": [dispatch],
        "approvals": []
    }