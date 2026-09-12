"""
Quick script to test the MongoDB Atlas connection.
Run: python test_connection.py
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

# Load MONGODB_URI from your local .env file (never commit this file)
load_dotenv()

uri = os.getenv("MONGODB_URI")

if not uri:
    raise ValueError(
        "MONGODB_URI not found. Make sure you have a .env file in this "
        "folder with a line like:\n"
        "MONGODB_URI=mongodb+srv://admin:<password>@jobless-simulator..."
    )

# Create a new client and connect to the server
client = MongoClient(uri, server_api=ServerApi("1"))

try:
    # The ping command is cheap and confirms the connection works
    client.admin.command("ping")
    print("✅ Connected successfully to MongoDB Atlas!")

    # Optional: list the databases you can see, as a sanity check
    print("\nDatabases visible to this user:")
    for db_name in client.list_database_names():
        print(f"  - {db_name}")

except Exception as e:
    print("❌ Connection failed.")
    print(e)

finally:
    client.close()