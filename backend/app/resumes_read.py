"""
Read/delete endpoints for resume_documents - the missing "read" half of
resume access (upload was already covered in resumes.py).
"""

from typing import List

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo.database import Database

from backend.app.db import get_db
from backend.app.schemas import ExtractedData, ResumeUploadResponse

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


class DeleteResumeResponse(BaseModel):
    resume_id: str
    deleted: bool


def _doc_to_response(doc: dict) -> ResumeUploadResponse:
    return ResumeUploadResponse(
        resume_id=str(doc["_id"]),
        user_id=doc["user_id"],
        file_name=doc["file_name"],
        uploaded_at=doc["uploaded_at"],
        extracted_data=ExtractedData(**doc["extracted_data"]),
    )


@router.get("/{resume_id}", response_model=ResumeUploadResponse)
def get_resume(resume_id: str, db: Database = Depends(get_db)) -> ResumeUploadResponse:
    """Fetch a single resume by its MongoDB _id."""
    try:
        object_id = ObjectId(resume_id)
    except InvalidId:
        raise HTTPException(status_code=422, detail=f"'{resume_id}' is not a valid resume_id.")

    doc = db["resume_documents"].find_one({"_id": object_id})
    if doc is None:
        raise HTTPException(status_code=404, detail=f"No resume found for resume_id={resume_id}")

    return _doc_to_response(doc)


@router.get("/user/{user_id}", response_model=List[ResumeUploadResponse])
def list_resumes_for_user(user_id: str, db: Database = Depends(get_db)) -> List[ResumeUploadResponse]:
    """Lists all resumes uploaded by a given user, newest first."""
    docs = db["resume_documents"].find({"user_id": user_id}).sort("uploaded_at", -1)
    return [_doc_to_response(doc) for doc in docs]


@router.delete("/{resume_id}", response_model=DeleteResumeResponse)
def delete_resume(resume_id: str, db: Database = Depends(get_db)) -> DeleteResumeResponse:
    """Deletes a resume by its MongoDB _id."""
    try:
        object_id = ObjectId(resume_id)
    except InvalidId:
        raise HTTPException(status_code=422, detail=f"'{resume_id}' is not a valid resume_id.")

    result = db["resume_documents"].delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"No resume found for resume_id={resume_id}")

    return DeleteResumeResponse(resume_id=resume_id, deleted=True)