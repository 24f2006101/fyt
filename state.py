import hashlib
import json
import secrets

from trace import build_otlp


def handle_receipt(store, run_id, receipt):
    run = store.runs[run_id]
    outcomes = receipt.get("outcomes", [])
    approvals = receipt.get("approvals", [])

    for outcome in outcomes:
        for dispatch in run["dispatches"]:
            if dispatch["actionId"] != outcome["actionId"]:
                continue

            # Do not process the same logical attempt twice.
            if "receipt" in dispatch:
                continue

            dispatch["receipt"] = outcome
            dispatch["receiptId"] = receipt["receiptId"]

            # Diagnostic succeeded -> propose exactly one effect.
            if (
                dispatch["phase"] == "diagnostic"
                and outcome.get("resultClass") == "diagnosis_confirmed"
                and outcome.get("status") == 200
            ):
                return propose_effect(run, receipt)

            # 503 diagnostic -> exactly one retry.
            if (
                dispatch["phase"] == "diagnostic"
                and outcome.get("status") == 503
                and dispatch["attempt"] == 1
            ):
                return retry_dispatch(run, dispatch)

            # Effect succeeded -> run is complete.
            if (
                dispatch["phase"] == "effect"
                and outcome.get("status") == 200
            ):
                return finish_run(run, receipt)

    for approval in approvals:
        if approval.get("decision") == "approved":
            return dispatch_approved_effect(run, approval, receipt)

    return run["last_response"]


def retry_dispatch(run, dispatch):
    parts = dispatch["traceparent"].split("-")
    trace_id = parts[1]
    new_client_span_id = secrets.token_hex(8)

    retry = dict(dispatch)
    retry["attempt"] = 2
    retry["traceparent"] = f"00-{trace_id}-{new_client_span_id}-01"
    retry.pop("receipt", None)

    run["dispatches"].append(retry)

    return {
        "runId": run["request"]["runId"],
        "status": "waiting",
        "diagnosis": run["last_response"]["diagnosis"],
        "dispatches": [retry],
        "approvals": []
    }


def propose_effect(run, receipt):
    policy = run["request"]["policy"]
    effect_tool = policy["effectTools"][0]
    diagnosis = run["last_response"]["diagnosis"]

    if effect_tool in policy.get("approvalRequiredFor", []):
        arguments = {"reason": "confirmed incident"}
        approval = {
            "approvalId": "approval_" + secrets.token_hex(8),
            "actionId": "effect_" + secrets.token_hex(8),
            "toolName": effect_tool,
            "argumentsDigest": sha256_json(arguments)
        }

        run["approvals"] = [approval]

        return {
            "runId": run["request"]["runId"],
            "status": "waiting",
            "diagnosis": diagnosis,
            "dispatches": [],
            "approvals": [approval]
        }

    effect = {
        "actionId": "effect_" + secrets.token_hex(8),
        "callId": "effect_call_" + secrets.token_hex(8),
        "phase": "effect",
        "toolName": effect_tool,
        "arguments": {"reason": "confirmed incident"},
        "evidence": diagnosis["evidence"][:1],
        "attempt": 1,
        "traceparent": make_traceparent()
    }

    run["dispatches"].append(effect)

    return {
        "runId": run["request"]["runId"],
        "status": "waiting",
        "diagnosis": diagnosis,
        "dispatches": [effect],
        "approvals": []
    }


def dispatch_approved_effect(run, approval, receipt):
    diagnosis = run["last_response"]["diagnosis"]

    effect = {
        "actionId": approval["actionId"],
        "callId": "effect_call_" + secrets.token_hex(8),
        "phase": "effect",
        "toolName": approval["toolName"],
        "arguments": {"reason": "approved incident response"},
        "evidence": diagnosis["evidence"][:1],
        "attempt": 1,
        "approvalId": approval["approvalId"],
        "approvalNonce": receipt.get("nonce", ""),
        "traceparent": make_traceparent()
    }

    run["dispatches"].append(effect)

    return {
        "runId": run["request"]["runId"],
        "status": "waiting",
        "diagnosis": diagnosis,
        "dispatches": [effect],
        "approvals": []
    }


def finish_run(run, receipt):
    action_log = []
    receipt_log = []

    for dispatch in run["dispatches"]:
        action_log.append(dispatch)

        if "receipt" in dispatch:
            outcome = dispatch["receipt"]

            receipt_log.append({
                "receiptId": dispatch["receiptId"],
                "actionId": dispatch["actionId"],
                "callId": dispatch["callId"],
                "attempt": dispatch["attempt"],
                "status": outcome["status"],
                "resultClass": outcome["resultClass"],
                "nonce": outcome["nonce"]
            })

    return {
        "runId": run["request"]["runId"],
        "status": "completed",
        "diagnosis": run["last_response"]["diagnosis"],
        "chosenEffect": "scale_service",
        "suppressed": [],
        "actionLog": action_log,
        "receiptLog": receipt_log,
        "otlp": build_otlp(run)
    }


def sha256_json(value):
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":")
    ).encode()

    return hashlib.sha256(encoded).hexdigest()


def make_traceparent():
    return (
        "00-"
        + secrets.token_hex(16)
        + "-"
        + secrets.token_hex(8)
        + "-01"
    )