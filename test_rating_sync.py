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

# Fetch target playlist items
p_res = youtube.playlists().list(mine=True, part="snippet", maxResults=50).execute()
pid = None
for p in p_res.get("items", []):
    if p["snippet"]["title"] == "テレ東短動画リスト":
        pid = p["id"]
        break

if pid:
    items_res = youtube.playlistItems().list(playlistId=pid, part="snippet", maxResults=20).execute()
    vids = [item["snippet"]["resourceId"]["videoId"] for item in items_res.get("items", [])]
    if vids:
        ratings_res = youtube.videos().getRating(id=",".join(vids)).execute()
        print("Ratings fetched from YouTube:")
        for r in ratings_res.get("items", []):
            print(f"- Video ID: {r['videoId']} -> Rating: {r['rating']}")
    else:
        print("No videos found in playlist 'テレ東短動画リスト'")
else:
    print("Playlist 'テレ東短動画リスト' not found.")
