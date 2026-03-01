"""
Announcement endpoints for the High School Management System API

Provides CRUD operations for school announcements.
Only authenticated teachers/admins can create, update, or delete announcements.
Active announcements are publicly visible.
"""

from datetime import datetime, timezone
import logging

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from ..database import announcements_collection, teachers_collection

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementCreate(BaseModel):
    """Schema for creating or updating an announcement."""
    message: str = Field(..., min_length=1, max_length=500)
    start_date: Optional[str] = None
    expiration_date: str


def _serialize_announcement(doc: dict) -> dict:
    """Convert a MongoDB announcement document to a JSON-serializable dict."""
    doc["id"] = str(doc.pop("_id"))
    return doc


def _validate_teacher(username: str) -> None:
    """Raise 401 if the username does not belong to a valid teacher/admin."""
    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _validate_dates(start_date: Optional[str], expiration_date: str) -> None:
    """Validate that dates are well-formed ISO strings and logically ordered."""
    try:
        exp = datetime.fromisoformat(expiration_date)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=400, detail="Invalid expiration date format"
        )

    if start_date:
        try:
            start = datetime.fromisoformat(start_date)
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400, detail="Invalid start date format"
            )
        if start >= exp:
            raise HTTPException(
                status_code=400,
                detail="Start date must be before expiration date",
            )


# --- Public endpoints ---


@router.get("/")
def list_announcements():
    """Return all announcements, sorted newest first."""
    docs = announcements_collection.find().sort("created_at", -1)
    return [_serialize_announcement(doc) for doc in docs]


@router.get("/active")
def list_active_announcements():
    """Return only currently active announcements (not expired, past start date)."""
    now = datetime.now(timezone.utc).isoformat()
    query = {"expiration_date": {"$gt": now}}
    docs = announcements_collection.find(query).sort("created_at", -1)

    active = []
    for doc in docs:
        start = doc.get("start_date")
        if start and start > now:
            continue
        active.append(_serialize_announcement(doc))
    return active


# --- Authenticated endpoints ---


@router.post("/")
def create_announcement(
    body: AnnouncementCreate,
    teacher_username: str = Query(...),
):
    """Create a new announcement. Requires a valid teacher username."""
    _validate_teacher(teacher_username)
    _validate_dates(body.start_date, body.expiration_date)

    doc = {
        "message": body.message,
        "start_date": body.start_date,
        "expiration_date": body.expiration_date,
        "created_by": teacher_username,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = announcements_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    doc.pop("_id", None)
    logger.info("Announcement created by %s", teacher_username)
    return doc


@router.put("/{announcement_id}")
def update_announcement(
    announcement_id: str,
    body: AnnouncementCreate,
    teacher_username: str = Query(...),
):
    """Update an existing announcement. Requires a valid teacher username."""
    _validate_teacher(teacher_username)
    _validate_dates(body.start_date, body.expiration_date)

    try:
        obj_id = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement ID")

    existing = announcements_collection.find_one({"_id": obj_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    update_data = {
        "message": body.message,
        "start_date": body.start_date,
        "expiration_date": body.expiration_date,
    }
    announcements_collection.update_one({"_id": obj_id}, {"$set": update_data})
    logger.info("Announcement %s updated by %s", announcement_id, teacher_username)
    return {"message": "Announcement updated successfully"}


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: str = Query(...),
):
    """Delete an announcement. Requires a valid teacher username."""
    _validate_teacher(teacher_username)

    try:
        obj_id = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement ID")

    result = announcements_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    logger.info("Announcement %s deleted by %s", announcement_id, teacher_username)
    return {"message": "Announcement deleted successfully"}
