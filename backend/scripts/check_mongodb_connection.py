"""Check the MongoDB Atlas connection when run explicitly."""

import os

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi


def main() -> None:
    """Load the local URI and report whether MongoDB responds to a ping."""
    load_dotenv()
    uri = os.getenv("MONGODB_URI")

    if not uri:
        raise ValueError(
            "MONGODB_URI not found. Make sure you have a .env file in this "
            "folder with a line like:\n"
            "MONGODB_URI=mongodb+srv://admin:<password>@jobless-simulator..."
        )

    client = MongoClient(
        uri,
        server_api=ServerApi("1"),
        serverSelectionTimeoutMS=10_000,
    )

    try:
        client.admin.command("ping")
        print("✅ Connected successfully to MongoDB Atlas!")
    except Exception as error:
        print(f"❌ Connection failed: {error}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
