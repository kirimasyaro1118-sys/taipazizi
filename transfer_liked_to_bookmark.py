import os
import sys
import time
import datetime
import argparse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

SCOPES = ["https://www.googleapis.com/auth/youtube"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(SCRIPT_DIR, "credentials.json")
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")

TARGET_PLAYLIST_NAME = "ブックマーク"

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
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(f"[エラー] '{CREDENTIALS_FILE}' が見つかりません。")
            if os.path.exists(TOKEN_FILE):
                try:
                    os.remove(TOKEN_FILE)
                except Exception:
                    pass
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            print("🔑 ブラウザを開いて Google アカウント認証を行います...")
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)

def get_all_liked_videos(youtube):
    """高評価した動画(LL再生リスト)の全動画一覧を取得します。"""
    liked_items = []
    next_page_token = None

    print("\n[取得中] 高評価した動画の一覧を取得しています...")
    
    # ユーザーの「高く評価した動画」の再生リストID (LL) を取得
    ch_res = youtube.channels().list(part="contentDetails", mine=True).execute()
    likes_playlist_id = "LL"
    if ch_res.get("items"):
        likes_playlist_id = ch_res["items"][0]["contentDetails"]["relatedPlaylists"].get("likes", "LL")

    while True:
        try:
            req = youtube.playlistItems().list(
                part="snippet",
                playlistId=likes_playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            res = req.execute()

            for item in res.get("items", []):
                snippet = item["snippet"]
                vid = snippet["resourceId"]["videoId"]
                title = snippet["title"]
                liked_items.append({
                    "videoId": vid,
                    "title": title
                })

            next_page_token = res.get("nextPageToken")
            if not next_page_token:
                break
        except HttpError as e:
            print(f"⚠️ 高評価動画の取得中にエラーが発生しました: {e}")
            break

    print(f"✓ 高評価動画を合計 {len(liked_items)} 件取得しました。")
    return liked_items

def get_or_create_bookmark_playlist(youtube):
    """再生リスト『ブックマーク』を取得、存在しなければ新規作成します。"""
    next_page_token = None
    while True:
        req = youtube.playlists().list(
            part="snippet",
            mine=True,
            maxResults=50,
            pageToken=next_page_token
        )
        res = req.execute()

        for item in res.get("items", []):
            if item["snippet"]["title"].strip().lower() == TARGET_PLAYLIST_NAME.lower():
                pid = item["id"]
                print(f"✓ 既存の再生リスト 『{TARGET_PLAYLIST_NAME}』 を検出しました (ID: {pid})")
                return pid

        next_page_token = res.get("nextPageToken")
        if not next_page_token:
            break

    # 無い場合は新規作成
    print(f"ℹ️ 再生リスト 『{TARGET_PLAYLIST_NAME}』 を新規作成します...")
    created = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": TARGET_PLAYLIST_NAME,
                "description": "高評価から移行したブックマーク動画リスト"
            },
            "status": {
                "privacyStatus": "private"
            }
        }
    ).execute()
    print(f"✨ 再生リスト 『{TARGET_PLAYLIST_NAME}』 を作成しました！ (ID: {created['id']})")
    return created["id"]

def get_existing_video_ids(youtube, playlist_id):
    """ターゲット再生リスト内の既存動画IDを取得して二重追加を防止します。"""
    existing_ids = set()
    next_page_token = None
    while True:
        try:
            req = youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            res = req.execute()
            for item in res.get("items", []):
                existing_ids.add(item["snippet"]["resourceId"]["videoId"])
            next_page_token = res.get("nextPageToken")
            if not next_page_token:
                break
        except HttpError as e:
            if "playlistNotFound" in str(e) or e.resp.status == 404:
                return set()
            raise e
    return existing_ids

def main():
    parser = argparse.ArgumentParser(description="高評価動画を『ブックマーク』再生リストへ移行するツール")
    parser.add_argument("--dry-run", action="store_true", help="プレビュー表示のみ行い、追加を行いません")
    parser.add_argument("--limit", type=int, default=None, help="一度に移行する最大件数制限")
    args = parser.parse_args()

    print("=" * 65)
    print(" 高評価動画 -> 『ブックマーク』再生リスト 移行システム ")
    print("=" * 65)

    try:
        youtube = get_youtube_service()
        print("✓ OAuth 認証成功")
    except Exception as e:
        print(f"❌ 認証エラー: {e}")
        return

    # 1. ブックマーク再生リストを取得または作成
    playlist_id = get_or_create_bookmark_playlist(youtube)

    # 2. ブックマーク再生リスト内の既存動画ID一覧を取得
    existing_ids = get_existing_video_ids(youtube, playlist_id)
    print(f"現在の 『{TARGET_PLAYLIST_NAME}』 内の既存動画数: {len(existing_ids)}件")

    # 3. 高評価動画一覧を取得
    liked_videos = get_all_liked_videos(youtube)
    if not liked_videos:
        print("高評価された動画は見つかりませんでした。")
        return

    # 未追加の動画を抽出
    to_add = [v for v in liked_videos if v["videoId"] not in existing_ids]

    if not to_add:
        print("\n✨ すべての高評価動画がすでに 『ブックマーク』 再生リストに追加されています！")
        return

    if args.limit and len(to_add) > args.limit:
        print(f"ℹ️ 件数制限により、上位 {args.limit} 件のみ移行します。")
        to_add = to_add[:args.limit]

    print(f"\n追加対象: {len(to_add)} 件の高評価動画を 『{TARGET_PLAYLIST_NAME}』 に追加します。")

    if args.dry_run:
        print("\n--- 【ドライラン (プレビュー)】 追加対象動画一覧 ---")
        for idx, v in enumerate(to_add, 1):
            print(f"  {idx}. {v['title']} (ID: {v['videoId']})")
        print("\n※ ドライランのため、実際に再生リストへの追加は行われていません。")
        return

    # 本番移行の実行
    print("\n[実行中] 『ブックマーク』 再生リストへ動画を追加しています...")
    added_count = 0
    for idx, v in enumerate(to_add, 1):
        time.sleep(0.4)
        try:
            youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": v["videoId"]
                        }
                    }
                }
            ).execute()
            print(f"  ✓ [{idx}/{len(to_add)}] 追加完了: {v['title']}")
            added_count += 1
        except HttpError as e:
            if "quotaExceeded" in str(e):
                print("\n🛑 本日の YouTube API 利用上限 (10,000 units) に達しました。明日16時以降に残りを実行可能です。")
                break
            elif "videoNotFound" in str(e) or "404" in str(e):
                print(f"  ⚠️ スキップ (非公開または削除済み動画): {v['title']}")
            else:
                print(f"  ❌ 追加エラースキップ: {v['title']} ({e})")

    print(f"\n✨ 移行完了: {added_count} 件の高評価動画を 『{TARGET_PLAYLIST_NAME}』 再生リストに移行しました！")

if __name__ == "__main__":
    main()
