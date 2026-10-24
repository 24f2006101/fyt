from fastapi import FastAPI, HTTPException, Body
from typing import Any, Dict
from storage import MemoryStore
from planner import plan_incident
from state import handle_receipt

app = FastAPI()
store = MemoryStore()


@app.post("/v2/incidents")
async def create_incident(
    body: Dict[str, Any] = Body(...)
):
    if body.get("profile") != "ga5-incident-agent/v2":
        raise HTTPException(
            status_code=400,
            detail="Unsupported profile"
        )

    run_id = body.get("runId")
    if not run_id:
        raise HTTPException(
            status_code=400,
            detail="runId is required"
        )

    if run_id in store.runs:
        stored = store.runs[run_id]

        if stored["request"] != body:
            raise HTTPException(
                status_code=409,
                detail="runId content conflict"
            )

        return stored["last_response"]

    response = plan_incident(body)
    store.save_run(run_id, body, response)
    return response


@app.post("/v2/incidents/{run_id}/receipts")
async def receive_receipt(
    run_id: str,
    body: Dict[str, Any] = Body(...)
):
    if run_id not in store.runs:
        raise HTTPException(
            status_code=404,
            detail="Unknown run"
        )

    receipt_id = body.get("receiptId")
    if not receipt_id:
        raise HTTPException(
            status_code=400,
            detail="receiptId is required"
        )

    if receipt_id in store.receipts:
        stored = store.receipts[receipt_id]

        if stored != body:
            raise HTTPException(
                status_code=409,
                detail="receiptId content conflict"
            )

        return store.runs[run_id]["last_response"]

    response = handle_receipt(store, run_id, body)
    store.save_receipt(receipt_id, body)
    store.save_response(run_id, response)
    return response


@app.get("/v2/incidents/{run_id}")
async def get_incident(run_id: str):
    if run_id not in store.runs:
        raise HTTPException(
            status_code=404,
            detail="Unknown run"
        )

    return store.runs[run_id]["last_response"]