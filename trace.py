def build_otlp(run):
    run_id = run["request"]["runId"]
    marker = run["request"]["publicMarker"]

    spans = [
        {
            "traceId": "00000000000000000000000000000001",
            "spanId": "0000000000000001",
            "name": "POST /v2/incidents",
            "kind": 2,
            "attributes": [
                {
                    "key": "ga5.run.id",
                    "value": {"stringValue": run_id}
                },
                {
                    "key": "ga5.public.marker",
                    "value": {"stringValue": marker}
                }
            ]
        }
    ]

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