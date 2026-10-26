"""Current-resume replacement against a real MongoDB (disposable container).

Skipped unless TEST_MONGODB_URI is set; it must point at a throwaway database
(backend/scripts/run_disposable_db_tests.sh makes one). The test deletes every
document in that database's resume_documents. Never point it at the team's
MongoDB project.
"""

import os
from datetime import UTC, datetime

import pytest
from pymongo import MongoClient

from app.document_access import replace_current_resume

TEST_MONGODB_URI = os.environ.get("TEST_MONGODB_URI", "").strip()
MONGO_TEST_DATABASE = "jobless_simulator_test"

pytestmark = pytest.mark.skipif(
    not TEST_MONGODB_URI,
    reason="Set TEST_MONGODB_URI to a throwaway database to run these.",
)

USER_ID = "22222222-2222-4222-8222-222222222222"


def _document(file_name: str) -> dict:
    return {
        "user_id": USER_ID,
        "file_name": file_name,
        "raw_text": "Python SQL",
        "extracted_data": {"skills": ["Python"], "education": [], "experience": [], "projects": []},
        "uploaded_at": datetime.now(UTC),
    }


def test_replacement_returns_the_document_this_call_wrote() -> None:
    client = MongoClient(TEST_MONGODB_URI)
    try:
        db = client[MONGO_TEST_DATABASE]
        db["resume_documents"].delete_many({})

        first = replace_current_resume(db, _document("first.pdf"))
        second = replace_current_resume(db, _document("second.pdf"))

        assert first["file_name"] == "first.pdf"
        assert second["file_name"] == "second.pdf"
        # One current resume per user: the replacement keeps the same document id.
        assert second["_id"] == first["_id"]
        assert db["resume_documents"].count_documents({"user_id": USER_ID}) == 1
    finally:
        client[MONGO_TEST_DATABASE]["resume_documents"].delete_many({})
        client.close()
