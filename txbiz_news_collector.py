import os
import re
import json
import time
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/youtube"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(SCRIPT_DIR, "credentials.json")
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")

# 設定
CHANNEL_QUERY = "テレ東BIZ"
MAX_DURATION_SECONDS = 120  # 2分（120秒）以下
TARGET_PLAYLIST_NAME = "テレ東短動画リスト"
EXCLUDE_KEYWORDS = ["天気"]

def get_youtube_service():
    """OAuth認証を行い、YouTube APIサービスオブジェクトを取得します。"""
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(f"'{CREDENTIALS_FILE}' が見つかりません。")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)

def parse_iso8601_duration(duration_str):
    """ISO 8601形式の動画時間 (PT1M45S など) を秒数に変換します。"""
    pattern = re.compile(r'PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?')
    match = pattern.match(duration_str)
    if not match:
        return 0
    parts = match.groupdict()
    hours = int(parts['hours'] or 0)
    minutes = int(parts['minutes'] or 0)
    seconds = int(parts['seconds'] or 0)
    return hours * 3600 + minutes * 60 + seconds

def format_seconds(seconds):
    """秒数を mm:ss 形式に整形します。"""
    m, s = divmod(seconds, 60)
    return f"{m}分{s:02d}秒"

def get_target_playlist_id(youtube, playlist_name):
    """指定された名前の自分の再生リストのIDを取得します。"""
    next_page_token = None
    while True:
        request = youtube.playlists().list(
            part="snippet",
            mine=True,
            maxResults=50,
            pageToken=next_page_token
        )
        response = request.execute()
        for item in response.get("items", []):
            if item["snippet"]["title"].strip().lower() == playlist_name.strip().lower():
                return item["id"]
        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break
    return None

def get_channel_uploads_playlist_id(youtube, channel_name):
    """チャンネル名からアップロード再生リストID（UU...）を取得します。"""
    request = youtube.search().list(
        q=channel_name,
        type="channel",
        part="snippet",
        maxResults=1
    )
    response = request.execute()
    items = response.get("items", [])
    if not items:
        return None
    channel_id = items[0]["snippet"]["channelId"]
    # チャンネルID (UC...) の2文字目を U に変えるとアップロード用リストID (UU...) になる
    uploads_playlist_id = "UU" + channel_id[2:]
    return uploads_playlist_id

def get_existing_video_ids(youtube, playlist_id):
    """再生リスト内にある既存動画のID一覧を取得して二重追加を防止します。"""
    existing_ids = set()
    next_page_token = None
    while True:
        request = youtube.playlistItems().list(
            part="snippet",
            playlistId=playlist_id,
            maxResults=50,
            pageToken=next_page_token
        )
        response = request.execute()
        for item in response.get("items", []):
            existing_ids.add(item["snippet"]["resourceId"]["videoId"])
        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break
    return existing_ids

def main():
    print("=" * 60)
    print(f" テレ東BIZ ニュース自動追加ツール (2分以下・天気除外) ")
    print("=" * 60)

    try:
        youtube = get_youtube_service()
        print("✓ OAuth 認証に成功しました。")
    except Exception as e:
        print(f"認証エラー: {e}")
        return

    # 1. ターゲット再生リスト「ニュース」の検索
    print(f"\n[検索中] 再生リスト 『{TARGET_PLAYLIST_NAME}』 を検索しています...")
    playlist_id = get_target_playlist_id(youtube, TARGET_PLAYLIST_NAME)
    if not playlist_id:
        print(f"❌ 再生リスト 『{TARGET_PLAYLIST_NAME}』 が見つかりませんでした。")
        print("YouTube上で 『ニュース』 という名前の再生リストが作成されているか確認してください。")
        return
    print(f"✓ ターゲット再生リストを発見しました (ID: {playlist_id})")

    # 2. 既存の再生リスト内動画を取得（重複防止）
    existing_video_ids = get_existing_video_ids(youtube, playlist_id)
    print(f"現在の 『{TARGET_PLAYLIST_NAME}』 再生リスト内の動画数: {len(existing_video_ids)}件")

    # 3. テレ東BIZの最新アップロード動画を取得
    print(f"\n[検索中] 『{CHANNEL_QUERY}』 の最新動画を取得中...")
    uploads_id = get_channel_uploads_playlist_id(youtube, CHANNEL_QUERY)
    if not uploads_id:
        print(f"❌ 『{CHANNEL_QUERY}』 チャンネルが見つかりませんでした。")
        return

    # 最新のアップロード動画を取得 (最新50件)
    request = youtube.playlistItems().list(
        part="snippet",
        playlistId=uploads_id,
        maxResults=50
    )
    response = request.execute()
    recent_items = response.get("items", [])
    
    video_ids = [item["snippet"]["resourceId"]["videoId"] for item in recent_items]
    if not video_ids:
        print("新着動画が見つかりませんでした。")
        return

    # 動画の詳細（長さ）を一括取得
    vid_response = youtube.videos().list(
        part="snippet,contentDetails",
        id=",".join(video_ids)
    ).execute()

    matched_videos = []
    print("\n--- 新着動画のチェック判定 ---")
    for item in vid_response.get("items", []):
        v_id = item["id"]
        title = item["snippet"]["title"]
        duration_iso = item["contentDetails"]["duration"]
        duration_sec = parse_iso8601_duration(duration_iso)
        duration_str = format_seconds(duration_sec)

        # 判定1: すでに再生リストに存在するか
        if v_id in existing_video_ids:
            print(f"  ⏭️ スキップ (追加済み): {title} ({duration_str})")
            continue

        # 判定2: 長さが 2分(120秒) 以下か
        if duration_sec > MAX_DURATION_SECONDS:
            print(f"  ⏭️ スキップ (2分超過: {duration_str}): {title}")
            continue

        # 判定3: 除外キーワード（天気など）が含まれていないか
        has_exclude_kw = any(kw in title for kw in EXCLUDE_KEYWORDS)
        if has_exclude_kw:
            print(f"  ⏭️ スキップ (NGワード「天気」検出): {title}")
            continue

        # 条件クリア
        matched_videos.append({
            "id": v_id,
            "title": title,
            "duration_str": duration_str
        })
        print(f"  🎯 対象ヒット! [{duration_str}] {title}")

    if not matched_videos:
        print("\n追加対象の新しいニュース動画はありませんでした。")
        return

    import sys
    auto_mode = "--auto" in sys.argv

    print(f"\n追加対象: {len(matched_videos)}件 のニュース動画を再生リスト 『{TARGET_PLAYLIST_NAME}』 に追加します。")
    if not auto_mode:
        ans = input("実行しますか？ (Y/n): ").strip().lower()
        if ans == "n":
            print("キャンセルしました。")
            return
    else:
        print("[全自動モード] 確認なしでそのまま追加を開始します。")

    # 4. 追加処理
    print("\n[実行中] 再生リストへ追加を開始します...")
    added_count = 0
    for v in matched_videos:
        time.sleep(0.5)
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": v["id"]
                        }
                    }
                }
            ).execute()
            print(f"  ✓ 追加完了 [{v['duration_str']}]: {v['title']}")
            added_count += 1
        except HttpError as e:
            if "quotaExceeded" in str(e):
                print("\n🛑 本日の YouTube API 利用制限上限に達しました。明日16時以降にお試しください。")
                break
            else:
                print(f"  ❌ エラーのためスキップ: {v['title']} ({e})")

    print(f"\n✨ 完了: {added_count}件 の短尺ニュースを 『{TARGET_PLAYLIST_NAME}』 に追加しました！")

if __name__ == "__main__":
    main()
