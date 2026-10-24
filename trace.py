import secrets


def build_otlp(run):
    run_id = run["request"]["runId"]
    marker = run["request"]["publicMarker"]

    trace_id = secrets.token_hex(16)
    server_span_id = secrets.token_hex(8)
    agent_span_id = secrets.token_hex(8)
    model_span_id = secrets.token_hex(8)
    join_span_id = secrets.token_hex(8)

    def text(key, value):
        return {
            "key": key,
            "value": {"stringValue": str(value)}
        }

    def number(key, value):
        return {
            "key": key,
            "value": {"intValue": str(value)}
        }

    spans = [
        {
            "traceId": trace_id,
            "spanId": server_span_id,
            "name": "POST /v2/incidents",
            "kind": 2,
            "attributes": [
                text("ga5.run.id", run_id),
                text("ga5.public.marker", marker)
            ]
        },
        {
            "traceId": trace_id,
            "spanId": agent_span_id,
            "parentSpanId": server_span_id,
            "name": "invoke_agent incident-response",
            "kind": 1,
            "attributes": [
                text("ga5.run.id", run_id),
                text("ga5.public.marker", marker)
            ]
        },
        {
            "traceId": trace_id,
            "spanId": model_span_id,
            "parentSpanId": agent_span_id,
            "name": "chat incident-plan",
            "kind": 3,
            "attributes": [
                text("ga5.run.id", run_id),
                text("ga5.public.marker", marker),
                text("gen_ai.operation.name", "chat"),
                text("gen_ai.request.model", "gpt-4o-mini")
            ]
        },
        {
            "traceId": trace_id,
            "spanId": join_span_id,
            "parentSpanId": agent_span_id,
            "name": "incident.join",
            "kind": 1,
            "attributes": [
                text("ga5.run.id", run_id),
                text("ga5.public.marker", marker)
            ]
        }
    ]

    diagnostic_span_ids = []

    for dispatch in run["dispatches"]:
        logical_span_id = secrets.token_hex(8)
        client_span_id = dispatch["traceparent"].split("-")[2]
        receipt = dispatch.get("receipt", {})

        attributes = [
            text("ga5.run.id", run_id),
            text("ga5.public.marker", marker),
            text("ga5.action.id", dispatch["actionId"]),
            text("gen_ai.tool.name", dispatch["toolName"]),
            text("gen_ai.tool.call.id", dispatch["callId"]),
            text("gen_ai.operation.name", "execute_tool")
        ]

        if dispatch["phase"] == "effect" and dispatch.get("approvalId"):
            attributes.append(
                text("ga5.approval.id", dispatch["approvalId"])
            )

        spans.append({
            "traceId": trace_id,
            "spanId": logical_span_id,
            "parentSpanId": agent_span_id,
            "name": f"execute_tool {dispatch['toolName']}",
            "kind": 1,
            "attributes": attributes
        })

        client_attributes = [
            text("ga5.run.id", run_id),
            text("ga5.public.marker", marker),
            text("ga5.action.id", dispatch["actionId"]),
            number("ga5.attempt", dispatch["attempt"]),
            text("ga5.receipt.id", dispatch.get("receiptId", "")),
            text("ga5.receipt.nonce", receipt.get("nonce", "")),
            text("http.request.method", "POST"),
            number("http.request.resend_count", dispatch["attempt"] - 1),
            number("http.response.status_code", receipt.get("status", 0))
        ]

        if dispatch["phase"] == "effect" and dispatch.get("approvalNonce"):
            client_attributes.append(
                text("ga5.approval.nonce", dispatch["approvalNonce"])
            )

        spans.append({
            "traceId": trace_id,
            "spanId": client_span_id,
            "parentSpanId": logical_span_id,
            "name": f"POST tool/{dispatch['toolName']}",
            "kind": 3,
            "attributes": client_attributes
        })

        if dispatch["phase"] == "diagnostic":
            diagnostic_span_ids.append(logical_span_id)

    # Add approval_gate only if an approval was actually used.
    has_approval = any(
        dispatch.get("approvalId")
        for dispatch in run["dispatches"]
    )

    if has_approval:
        approval_dispatch = next(
            d for d in run["dispatches"]
            if d.get("approvalId")
        )

        approval_span_id = secrets.token_hex(8)

        spans.append({
            "traceId": trace_id,
            "spanId": approval_span_id,
            "parentSpanId": agent_span_id,
            "name": "approval_gate",
            "kind": 1,
            "attributes": [
                text("ga5.run.id", run_id),
                text("ga5.public.marker", marker),
                text("ga5.approval.id", approval_dispatch["approvalId"]),
                text(
                    "ga5.approval.receipt.nonce",
                    approval_dispatch.get("approvalNonce", "")
                )
            ]
        })

    return {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": spans
                    }
                ]
            }
        ]
    }
