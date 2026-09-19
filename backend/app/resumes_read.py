"""
Read/delete endpoints for resume_documents - the missing "read" half of
resume access (upload was already covered in resumes.py).
"""

from typing import List

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .auth import CurrentUser
from .dependencies import AdminDatabase, AuthenticatedDatabase
from .document_access import section_items
from .schemas import ExtractedData, ResumeUploadResponse

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


class DeleteResumeResponse(BaseModel):
    resume_id: str
    deleted: bool


class TopSkill(BaseModel):
    skill: str
    count: int


class ResumeStatsResponse(BaseModel):
    total_resumes: int
    top_skills: List[TopSkill]


def _doc_to_response(doc: dict) -> ResumeUploadResponse:
    return ResumeUploadResponse(
        resume_id=str(doc["_id"]),
        user_id=doc["user_id"],
        file_name=doc["file_name"],
        uploaded_at=doc["uploaded_at"],
        extracted_data=ExtractedData(
            skills=doc["extracted_data"].get("skills", []),
            education=section_items(doc["extracted_data"].get("education", [])),
            experience=section_items(doc["extracted_data"].get("experience", [])),
            projects=section_items(doc["extracted_data"].get("projects", [])),
        ),
    )


@router.get("/stats", response_model=ResumeStatsResponse)
def get_resume_stats(
    user: CurrentUser,
    db: AdminDatabase,
    top_n: int = Query(10, ge=1, le=50, description="How many top skills to return"),
) -> ResumeStatsResponse:
    """
    Summary stats across all stored resumes: total count, and the most
    frequently occurring skills across every resume's extracted_data.
    """
    total_resumes = db["resume_documents"].count_documents({})

    pipeline = [
        {"$unwind": "$extracted_data.skills"},
        {"$group": {"_id": "$extracted_data.skills", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": top_n},
    ]
    results = db["resume_documents"].aggregate(pipeline)
    top_skills = [TopSkill(skill=doc["_id"], count=doc["count"]) for doc in results]

    return ResumeStatsResponse(total_resumes=total_resumes, top_skills=top_skills)


@router.get("/user/{user_id}", response_model=list[ResumeUploadResponse])
def list_resumes_for_user(
    user: CurrentUser, user_id: str, db: AuthenticatedDatabase
) -> list[ResumeUploadResponse]:
    """List only the authenticated user's current resume documents."""
    if user_id != str(user.user_id):
        raise HTTPException(status_code=404, detail="No resumes found for this user.")
    docs = db["resume_documents"].find({"user_id": str(user.user_id)}).sort("uploaded_at", -1)
    return [_doc_to_response(doc) for doc in docs]


@router.get("/{resume_id}", response_model=ResumeUploadResponse)
def get_resume(
    user: CurrentUser, resume_id: str, db: AuthenticatedDatabase
) -> ResumeUploadResponse:
    """Fetch a single resume by its MongoDB _id."""
    try:
        object_id = ObjectId(resume_id)
    except InvalidId:
        raise HTTPException(status_code=422, detail=f"'{resume_id}' is not a valid resume_id.")

    doc = db["resume_documents"].find_one({"_id": object_id, "user_id": str(user.user_id)})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"No resume found for resume_id={resume_id}")

    return _doc_to_response(doc)


@router.delete("/{resume_id}", response_model=DeleteResumeResponse)
def delete_resume(
    user: CurrentUser, resume_id: str, db: AuthenticatedDatabase
) -> DeleteResumeResponse:
    """Deletes a resume by its MongoDB _id."""
    try:
        object_id = ObjectId(resume_id)
    except InvalidId:
        raise HTTPException(status_code=422, detail=f"'{resume_id}' is not a valid resume_id.")

    result = db["resume_documents"].delete_one({"_id": object_id, "user_id": str(user.user_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"No resume found for resume_id={resume_id}")

    return DeleteResumeResponse(resume_id=resume_id, deleted=True)
