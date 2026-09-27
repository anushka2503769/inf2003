"""
Quick script to test the MongoDB Atlas connection.
Run: python test_connection.py
"""

import os


def main() -> None:
    """Ping MongoDB only when this diagnostic script is run explicitly."""
    from dotenv import load_dotenv
    from pymongo import MongoClient
    from pymongo.server_api import ServerApi

    load_dotenv()
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise ValueError(
            "MONGODB_URI not found. Configure it in the environment before running this check."
        )

    client = MongoClient(uri, server_api=ServerApi("1"))
    try:
        client.admin.command("ping")
        print("Connected successfully to MongoDB Atlas.")
        print("\nDatabases visible to this user:")
        for db_name in client.list_database_names():
            print(f"  - {db_name}")
    except Exception as exc:
        print("Connection failed.")
        print(exc)
    finally:
        client.close()


if __name__ == "__main__":
    main()
