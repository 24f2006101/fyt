class MemoryStore:
    def __init__(self):
        self.runs = {}
        self.receipts = {}

    def save_run(self, run_id, request, response):
        self.runs[run_id] = {
            "request": request,
            "last_response": response,
            "state": "waiting",
            "dispatches": response.get("dispatches", []),
            "receipts": [],
            "approvals": [],
        }

    def save_receipt(self, receipt_id, receipt):
        self.receipts[receipt_id] = receipt

    def save_response(self, run_id, response):
        self.runs[run_id]["last_response"] = response