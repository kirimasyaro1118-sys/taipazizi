import os
import sys
import time
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
    """「高く評価した動画」(LL) の全動画を取得します。"""
    liked_items = []
    next_page_token = None

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
            print(f"⚠️ 高評価動画の取得エラー: {e}")
            break

    return liked_items

def main():
    parser = argparse.ArgumentParser(description="高く評価した動画の評価を取り消してリストを空にするツール")
    parser.add_argument("--dry-run", action="store_true", help="プレビュー表示のみ行います")
    parser.add_argument("--auto", action="store_true", help="確認プロンプトをスキップして実行します")
    args = parser.parse_args()

    print("=" * 65)
    print(" 高く評価した動画 リストクリア（高評価解除）システム ")
    print("=" * 65)

    try:
        youtube = get_youtube_service()
        print("✓ OAuth 認証成功")
    except Exception as e:
        print(f"❌ 認証エラー: {e}")
        return

    liked_videos = get_all_liked_videos(youtube)
    print(f"現在 「高く評価した動画」 に登録されている動画数: {len(liked_videos)}件")

    if not liked_videos:
        print("✨ 「高く評価した動画」 リストはすでに空です！")
        return

    if args.dry_run:
        print("\n--- 【ドライラン (プレビュー)】 高評価解除対象 ---")
        for idx, v in enumerate(liked_videos, 1):
            print(f"  {idx}. {v['title']} (ID: {v['videoId']})")
        print("\n※ ドライランのため高評価の解除は行われていません。")
        return

    if not args.auto:
        ans = input(f"\n⚠️ {len(liked_videos)} 件の動画の高評価(Like)を取り消してリストを空にしますか？ (Y/n): ").strip().lower()
        if ans == "n":
            print("キャンセルしました。")
            return

    print("\n[実行中] 高評価の取り消し処理を行っています...")
    removed_count = 0
    for idx, v in enumerate(liked_videos, 1):
        time.sleep(0.4)
        try:
            # rating='none' で高評価を取り消す
            youtube.videos().rate(id=v["videoId"], rating="none").execute()
            print(f"  ✓ [{idx}/{len(liked_videos)}] 高評価解除完了: {v['title']}")
            removed_count += 1
        except HttpError as e:
            if "quotaExceeded" in str(e):
                print("\n🛑 本日の YouTube API 利用上限 (10,000 units) に達しました。明日16時以降に残りを実行可能です。")
                break
            else:
                print(f"  ❌ スキップ: {v['title']} ({e})")

    print(f"\n✨ 完了: {removed_count} 件の動画の高評価を取り消しました！")

if __name__ == "__main__":
    main()
