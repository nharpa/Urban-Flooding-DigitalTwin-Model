"""Issue reporting endpoint.

Exposes a POST /report route to capture community/user submitted flood related
issues (e.g. flooded road, blocked drain). Persists data to Mongo via
`FloodingDatabase.create_issue_report`.

Request JSON structure (example):
{
	"issue_type": "Flooded road",
	"description": "here",
	"location": {"latitude": -31.94, "longitude": 115.80},
	"user": {"uid": "abc", "display_name": "Name", "email": "user@example.com"}
}

The response echoes the submitted data and adds a generated `issue_id` and
`created_at` timestamp.
"""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, validator
from src.urban_flooding.persistence.database import FloodingDatabase
from src.urban_flooding.auth.auth import verify_token

router = APIRouter()


class ReportLocation(BaseModel):
	latitude: float = Field(..., ge=-90, le=90)
	longitude: float = Field(..., ge=-180, le=180)


class ReportUser(BaseModel):
	uid: str = Field(..., description="Unique user id (e.g. Firebase UID)")
	display_name: str | None = None
	email: str | None = None


class IssueReportRequest(BaseModel):
	issue_type: str = Field(..., min_length=3, max_length=120)
	description: str = Field(..., min_length=1, max_length=2000)
	location: ReportLocation
	user: ReportUser

	@field_validator("issue_type")
	def _trim_issue_type(cls, v: str) -> str:  # noqa: D401
		return v.strip()

	@field_validator("description")
	def _trim_description(cls, v: str) -> str:  # noqa: D401
		return v.strip()


class IssueReportResponse(BaseModel):
	issue_id: str
	issue_type: str
	description: str
	location: dict
	user: dict
	created_at: datetime


@router.post("/report", response_model=IssueReportResponse, status_code=201, tags=["report"])
def create_issue_report(req: IssueReportRequest, token: str = Depends(verify_token)):
	"""Create a new issue report.

	Authentication: requires a valid bearer token (see `verify_token`).
	"""
	db = FloodingDatabase()
	issue_id = db.create_issue_report(
		issue_type=req.issue_type,
		description=req.description,
		latitude=req.location.latitude,
		longitude=req.location.longitude,
		user_uid=req.user.uid,
		display_name=req.user.display_name,
		email=req.user.email,
	)
	# Fetch persisted document to ensure consistent shape (includes created_at)
	doc = db.get_issue_report(issue_id)
	# Defensive: if retrieval failed, synthesize response (unlikely)
	if not doc:
		doc = {
			"issue_id": issue_id,
			"issue_type": req.issue_type,
			"description": req.description,
			"location": {"type": "Point", "coordinates": [req.location.longitude, req.location.latitude]},
			"user": req.user.model_dump(),
			"created_at": datetime.now(),
		}
	return doc

