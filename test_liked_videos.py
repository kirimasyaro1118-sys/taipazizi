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

# 1. Check user channel relatedPlaylists.likes
ch_res = youtube.channels().list(part="contentDetails", mine=True).execute()
likes_playlist_id = None
if ch_res.get("items"):
    likes_playlist_id = ch_res["items"][0]["contentDetails"]["relatedPlaylists"].get("likes")
print(f"Likes Playlist ID: {likes_playlist_id}")

# 2. Try videos().list(myRating="like") or playlistItems().list(playlistId=likes_playlist_id)
liked_videos = []
if likes_playlist_id:
    try:
        pl_res = youtube.playlistItems().list(
            part="snippet",
            playlistId=likes_playlist_id,
            maxResults=50
        ).execute()
        for item in pl_res.get("items", []):
            liked_videos.append({
                "id": item["snippet"]["resourceId"]["videoId"],
                "title": item["snippet"]["title"]
            })
        print(f"Found {len(liked_videos)} liked videos via playlistItems.list")
    except Exception as e:
        print(f"playlistItems for likes error: {e}")

if not liked_videos:
    try:
        v_res = youtube.videos().list(
            part="snippet",
            myRating="like",
            maxResults=50
        ).execute()
        for item in v_res.get("items", []):
            liked_videos.append({
                "id": item["id"],
                "title": item["snippet"]["title"]
            })
        print(f"Found {len(liked_videos)} liked videos via videos.list(myRating='like')")
    except Exception as e:
        print(f"videos.list(myRating='like') error: {e}")

for idx, v in enumerate(liked_videos[:10], 1):
    print(f"{idx}. {v['title']} ({v['id']})")
