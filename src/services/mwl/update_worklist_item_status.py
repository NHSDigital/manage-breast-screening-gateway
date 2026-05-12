from services.storage import MWLStorage


class UpdateWorklistItemStatus:
    def __init__(self, storage: MWLStorage):
        self.storage = storage

    def call(self, payload: dict):
        """Update an existing worklist item."""
        try:
            item = payload["parameters"]["worklist_item"]
            accession_number = item["accession_number"]
            status = item["status"].upper()

            updated_item = self.storage.update_status(accession_number, status)

            if updated_item is None:
                return {"status": "error", "message": f"Worklist item '{accession_number}' not found"}

            return {"accession_number": accession_number, "status": "updated"}
        except KeyError as e:
            return {"status": "error", "message": f"Missing key: {e}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
