import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(SCRIPT_DIR, "credentials.json")
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")

def get_youtube_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed: {e}. Re-authenticating...")
                creds = None
        if not creds or not creds.valid:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(f"'{CREDENTIALS_FILE}' が見つかりません。")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)

def main():
    youtube = get_youtube_service()

    # 1. Try handle "tvtokyobiz"
    print("--- チャンネル検索: forHandle='tvtokyobiz' ---")
    try:
        ch_res = youtube.channels().list(
            forHandle="tvtokyobiz",
            part="snippet,contentDetails"
        ).execute()
        for item in ch_res.get("items", []):
            print(f"Title: {item['snippet']['title']}")
            print(f"Channel ID: {item['id']}")
            print(f"Uploads Playlist ID: {item['contentDetails']['relatedPlaylists']['uploads']}")
    except Exception as e:
        print(f"Handle search error: {e}")

    # 2. Try search query "テレ東BIZダイジェスト"
    print("\n--- チャンネル検索: query='テレ東BIZダイジェスト' ---")
    try:
        search_res = youtube.search().list(
            q="テレ東BIZダイジェスト",
            type="channel",
            part="snippet",
            maxResults=5
        ).execute()
        for item in search_res.get("items", []):
            print(f"Title: {item['snippet']['title']}, ChannelId: {item['snippet']['channelId']}")
    except Exception as e:
        print(f"Search query error: {e}")

if __name__ == "__main__":
    main()
