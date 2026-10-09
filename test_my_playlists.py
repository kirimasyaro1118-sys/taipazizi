import os
import sys
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

SCOPES = ["https://www.googleapis.com/auth/youtube"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")

creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
youtube = build("youtube", "v3", credentials=creds)

res = youtube.playlists().list(part="snippet,contentDetails", mine=True, maxResults=50).execute()
print(f"Total playlists found: {len(res.get('items', []))}")
for p in res.get("items", []):
    print(f"Title: '{p['snippet']['title']}', ID: {p['id']}, Count: {p['contentDetails']['itemCount']}")
