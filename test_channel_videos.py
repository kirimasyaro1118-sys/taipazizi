import os
import sys
import datetime
import re
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

def parse_iso8601_duration(duration_str):
    pattern = re.compile(r'PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?')
    match = pattern.match(duration_str)
    if not match:
        return 0
    parts = match.groupdict()
    hours = int(parts['hours'] or 0)
    minutes = int(parts['minutes'] or 0)
    seconds = int(parts['seconds'] or 0)
    return hours * 3600 + minutes * 60 + seconds

creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
youtube = build("youtube", "v3", credentials=creds)

# Get channel upload playlist ID
res = youtube.channels().list(forHandle="tvtokyobiz", part="snippet,contentDetails").execute()
ch_item = res["items"][0]
uploads_id = ch_item["contentDetails"]["relatedPlaylists"]["uploads"]
print(f"Channel: {ch_item['snippet']['title']}, Uploads ID: {uploads_id}")

# Get recent 50 videos
pl_res = youtube.playlistItems().list(part="snippet", playlistId=uploads_id, maxResults=50).execute()
items = pl_res.get("items", [])
v_ids = [it["snippet"]["resourceId"]["videoId"] for it in items]

vid_res = youtube.videos().list(part="snippet,contentDetails", id=",".join(v_ids)).execute()

print(f"\nAnalyzing {len(vid_res.get('items', []))} recent uploads:")
for v in vid_res.get("items", []):
    title = v["snippet"]["title"]
    pub = v["snippet"]["publishedAt"]
    dur_iso = v["contentDetails"]["duration"]
    dur_sec = parse_iso8601_duration(dur_iso)
    print(f"- Pub: {pub[:10]} | Dur: {dur_sec}s | Title: {title}")
