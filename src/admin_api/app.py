"""FastAPI app: create, list, get reservation requests; PATCH to approve/reject."""

from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from src.db.sqlite_db import get_db

app = FastAPI(title="Parking reservation admin API", version="0.1.0")


class CreateRequestBody(BaseModel):
    """Body for POST /requests: create a pending reservation request (Agent 1 sends via REST)."""

    nickname: str
    dates: List[str]


class UpdateStatusBody(BaseModel):
    """Body for PATCH /requests/{id}: set status to approved or rejected."""

    status: Literal["approved", "rejected"]


@app.post("/requests")
def create_request(body: CreateRequestBody):
    """Create a pending reservation request. Returns request_id for polling (Variant 1: Agent 1 sends via REST)."""
    db = get_db()
    request_id = db.create_pending_request(body.nickname, body.dates)
    return {"request_id": request_id}


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
