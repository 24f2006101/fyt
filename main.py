from fastapi import FastAPI, HTTPException, Body
from typing import Any, Dict
from storage import UpstashStore

from planner import plan_incident
from state import handle_receipt

app = FastAPI()

store = UpstashStore()
import logging
import traceback

from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger("incident-agent")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.error(
        "Unhandled error on %s: %s\n%s",
        request.url.path,
        repr(exc),
        traceback.format_exc()
    )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

@app.post("/v2/incidents")
async def create_incident(
    body: Dict[str, Any] = Body(...)
):
    if body.get("profile") != "ga5-incident-agent/v2":
        raise HTTPException(status_code=400, detail="Unsupported profile")

    run_id = body.get("runId")

    if not run_id:
        raise HTTPException(status_code=400, detail="runId is required")

    existing_run = store.get_run(run_id)

    if existing_run:
        if existing_run["request"] != body:
            raise HTTPException(status_code=409, detail="runId content conflict")

        return existing_run["last_response"]

    response = plan_incident(body)
    store.save_run(run_id, body, response)

    return response


@app.post("/v2/incidents/{run_id}/receipts")
async def receive_receipt(
    run_id: str,
    body: Dict[str, Any] = Body(...)
):
    run = store.get_run(run_id)

    if run is None:
        raise HTTPException(status_code=404, detail="Unknown run")

    receipt_id = body.get("receiptId")

    if not receipt_id:
        raise HTTPException(status_code=400, detail="receiptId is required")

    existing_receipt = store.get_receipt(receipt_id)

    if existing_receipt:
        if existing_receipt != body:
            raise HTTPException(status_code=409, detail="receiptId content conflict")

        return run["last_response"]

    response = handle_receipt(store, run_id, body)

    store.save_receipt(receipt_id, body)
    store.save_response(run_id, response)

    return response


@app.get("/v2/incidents/{run_id}")
async def get_incident(run_id: str):
    run = store.get_run(run_id)

    if run is None:
        raise HTTPException(status_code=404, detail="Unknown run")

    return run["last_response"]
