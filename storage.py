import json
import os

from upstash_redis import Redis

redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")

if not redis_url or not redis_token:
    raise RuntimeError(
        "UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN are required"
    )

r = Redis(url=redis_url, token=redis_token)


class UpstashStore:
    def save_run(self, run_id, request, response):
        run = {
            "request": request,
            "last_response": response,
            "dispatches": response.get("dispatches", []),
            "approvals": response.get("approvals", []),
        }

        r.set(f"run:{run_id}", json.dumps(run))

    def get_run(self, run_id):
        raw = r.get(f"run:{run_id}")

        if raw is None:
            return None

        if isinstance(raw, dict):
            return raw

        return json.loads(raw)

    def save_response(self, run_id, response):
        run = self.get_run(run_id)

        if run is None:
            return

        run["last_response"] = response
        run["dispatches"] = response.get("dispatches", run["dispatches"])
        run["approvals"] = response.get("approvals", run["approvals"])

        r.set(f"run:{run_id}", json.dumps(run))

    def save_receipt(self, receipt_id, receipt):
        r.set(f"receipt:{receipt_id}", json.dumps(receipt))

    def get_receipt(self, receipt_id):
        raw = r.get(f"receipt:{receipt_id}")

        if raw is None:
            return None

        if isinstance(raw, dict):
            return raw

        return json.loads(raw)
