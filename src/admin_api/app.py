"""FastAPI app: list and get reservation requests, PATCH to approve/reject."""

from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from src.db.sqlite_db import get_db

app = FastAPI(title="Parking reservation admin API", version="0.1.0")


class UpdateStatusBody(BaseModel):
    """Body for PATCH /requests/{id}: set status to approved or rejected."""

    status: Literal["approved", "rejected"]


@app.get("/requests")
def list_requests(
    status: Optional[Literal["pending", "approved", "rejected"]] = Query(
        default=None, description="Filter by status"
    ),
):
    """List reservation requests, optionally filtered by status."""
    db = get_db()
    return db.list_reservation_requests(status=status)


@app.get("/requests/{request_id}")
def get_request(request_id: str):
    """Get one reservation request by id."""
    db = get_db()
    req = db.get_reservation_request(request_id)
    if req is None:
        raise HTTPException(status_code=404, detail="Request not found")
    return req


@app.patch("/requests/{request_id}")
def update_request_status(request_id: str, body: UpdateStatusBody):
    """Set request status to approved or rejected."""
    db = get_db()
    status = body.status
    if db.get_reservation_request(request_id) is None:
        raise HTTPException(status_code=404, detail="Request not found")
    updated = db.set_request_status(request_id, status)
    if not updated:
        raise HTTPException(
            status_code=409,
            detail="Request is not pending (already approved or rejected)",
        )
    return {"id": request_id, "status": status}
