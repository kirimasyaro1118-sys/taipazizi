import os
import re
import sys
import json
import time
import datetime
import argparse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/youtube"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_FILE = os.path.join(SCRIPT_DIR, "credentials.json")
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")

# デフォルト設定
DEFAULT_CONFIG = {
    "channel_handle": "tvtokyobiz",
    "channel_query": "テレ東BIZダイジェスト",
    "target_playlist_name": "テレ東BIZダイジェスト（2分以下）",
    "max_duration_seconds": 120,  # 2分（120秒）以下
    "exclude_keywords": [],       # 除外キーワード（例: ["天気"] など必要に応じて指定）
    "max_fetch_count": 50,         # チェックする新着動画件数
    "privacy_status": "private"    # 新規作成時の公開設定: private, unlisted, public
}

def load_config():
    """設定ファイルを読み込みます。無ければデフォルト値を保存して返します。"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                # デフォルト値の補完
                for k, v in DEFAULT_CONFIG.items():
                    if k not in config:
                        config[k] = v
                return config
        except Exception as e:
            print(f"⚠️ 設定ファイルの読み込みエラー: {e}。デフォルト設定を使用します。")
    save_config(DEFAULT_CONFIG)
    return DEFAULT_CONFIG

def save_config(config):
    """設定ファイルを保存します。"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def get_youtube_service():
    """OAuth認証を行い、YouTube APIサービスオブジェクトを取得します。"""
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            print(f"[警告] 保存済みトークンの読み込みエラー: {e}")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"[警告] トークンの更新に失敗したため、再認証を行います: {e}")
                creds = None

        if not creds or not creds.valid:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"[エラー] '{CREDENTIALS_FILE}' が見つかりません。\n"
                    "Google Cloud Console からダウンロードした credentials.json を同じフォルダに配置してください。"
                )
            # 古いtoken.jsonがあれば削除
            if os.path.exists(TOKEN_FILE):
                try:
                    os.remove(TOKEN_FILE)
                except Exception:
                    pass
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            print("🔑 ブラウザを開いて Google アカウントの認証を行います...")
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

def get_channel_uploads_id(youtube, handle="tvtokyobiz", query="テレ東BIZダイジェスト"):
    """「テレ東BIZダイジェスト」チャンネルのアップロード動画再生リストID（UU...）を取得します。"""
    # 1. ハンドル指定で試行 (@tvtokyobiz)
    if handle:
        try:
            res = youtube.channels().list(
                forHandle=handle,
                part="snippet,contentDetails"
            ).execute()
            items = res.get("items", [])
            if items:
                ch_title = items[0]["snippet"]["title"]
                uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
                print(f"✓ チャンネル発見 [ハンドル: @{handle}]: 『{ch_title}』 (Uploads ID: {uploads_id})")
                return uploads_id, ch_title
        except Exception as e:
            print(f"⚠️ ハンドル検索スキップ (@{handle}): {e}")

    # 2. 検索クエリで試行 (テレ東BIZダイジェスト)
    try:
        res = youtube.search().list(
            q=query,
            type="channel",
            part="snippet",
            maxResults=1
        ).execute()
        items = res.get("items", [])
        if items:
            ch_id = items[0]["snippet"]["channelId"]
            ch_title = items[0]["snippet"]["title"]
            uploads_id = "UU" + ch_id[2:]
            print(f"✓ チャンネル発見 [検索: {query}]: 『{ch_title}』 (Uploads ID: {uploads_id})")
            return uploads_id, ch_title
    except Exception as e:
        print(f"❌ チャンネル検索エラー ({query}): {e}")

    return None, None

def get_or_create_target_playlist(youtube, playlist_name, privacy_status="private"):
    """指定された名前の再生リストを取得します。存在しない場合は自動作成します。"""
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
                p_id = item["id"]
                print(f"✓ ターゲット再生リストを発見しました: 『{playlist_name}』 (ID: {p_id})")
                return p_id
        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    # 無い場合は自動作成
    print(f"ℹ️ 再生リスト 『{playlist_name}』 が存在しないため、自動作成します...")
    body = {
        "snippet": {
            "title": playlist_name,
            "description": "テレ東BIZダイジェストの2分以下の短尺動画を自動集約した再生リスト"
        },
        "status": {
            "privacyStatus": privacy_status
        }
    }
    created = youtube.playlists().insert(part="snippet,status", body=body).execute()
    created_id = created["id"]
    print(f"✨ 再生リスト 『{playlist_name}』 を新規作成しました！ (ID: {created_id})")
    return created_id

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

def run_sync(auto_mode=False, dry_run=False, max_limit=None):
    """テレ東BIZダイジェストの2分以下動画を収集して再生リストに追加します。"""
    config = load_config()

    print("=" * 65)
    print(" テレ東BIZダイジェスト 2分以下動画 自動再生リスト集約システム ")
    print(f"  モード: {'ドライラン (プレビュー)' if dry_run else ('全自動実行' if auto_mode else '対話実行')}")
    print("=" * 65)

    try:
        youtube = get_youtube_service()
        print("✓ YouTube API 認証に成功しました。")
    except Exception as e:
        print(f"❌ 認証エラー: {e}")
        return {"status": "error", "message": f"認証エラー: {e}"}

    # 1. ターゲット再生リストの準備（無ければ自動作成）
    playlist_name = config["target_playlist_name"]
    try:
        playlist_id = get_or_create_target_playlist(
            youtube,
            playlist_name,
            config.get("privacy_status", "private")
        )
    except HttpError as e:
        if "quotaExceeded" in str(e):
            msg = "🛑 YouTube API の本日分利用上限 (10,000 units) に達しました。明日16時以降にお試しください。"
            print(msg)
            return {"status": "quota_exceeded", "message": msg}
        raise e

    # 2. 既存動画の取得 (重複防止)
    existing_video_ids = get_existing_video_ids(youtube, playlist_id)
    print(f"現在の再生リスト 『{playlist_name}』 内の登録動画数: {len(existing_video_ids)}件")

    # 3. チャンネルの最新アップロード動画を取得
    uploads_id, ch_title = get_channel_uploads_id(
        youtube,
        handle=config.get("channel_handle", "tvtokyobiz"),
        query=config.get("channel_query", "テレ東BIZダイジェスト")
    )
    if not uploads_id:
        msg = "❌ 対象チャンネルが見つかりませんでした。"
        print(msg)
        return {"status": "error", "message": msg}

    fetch_count = min(config.get("max_fetch_count", 50), 50)
    req = youtube.playlistItems().list(
        part="snippet",
        playlistId=uploads_id,
        maxResults=fetch_count
    )
    res = req.execute()
    recent_items = res.get("items", [])

    video_ids = [item["snippet"]["resourceId"]["videoId"] for item in recent_items]
    if not video_ids:
        print("新着動画が見つかりませんでした。")
        return {"status": "success", "added_count": 0, "message": "新着動画なし"}

    # 動画の詳細（長さ・サムネイル・公開日時）を取得
    vid_response = youtube.videos().list(
        part="snippet,contentDetails",
        id=",".join(video_ids)
    ).execute()

    matched_videos = []
    max_sec = config.get("max_duration_seconds", 120)
    exclude_kws = config.get("exclude_keywords", [])

    print("\n--- 動画チェック・判定結果 ---")
    for item in vid_response.get("items", []):
        v_id = item["id"]
        title = item["snippet"]["title"]
        published_at = item["snippet"].get("publishedAt", "")
        thumbnails = item["snippet"].get("thumbnails", {})
        thumb_url = thumbnails.get("medium", {}).get("url", thumbnails.get("default", {}).get("url", ""))

        duration_iso = item["contentDetails"]["duration"]
        duration_sec = parse_iso8601_duration(duration_iso)
        duration_str = format_seconds(duration_sec)

        # 判定1: 既に登録済みか
        if v_id in existing_video_ids:
            print(f"  ⏭️ スキップ (追加済み): [{duration_str}] {title}")
            continue

        # 判定2: 長さが指定秒数以下か (デフォルト: 120秒 = 2分以下)
        if duration_sec > max_sec:
            print(f"  ⏭️ スキップ ({max_sec // 60}分超過: {duration_str}): {title}")
            continue

        # 判定3: 除外キーワードチェック
        if exclude_kws and any(kw in title for kw in exclude_kws):
            print(f"  ⏭️ スキップ (除外キーワード検出): {title}")
            continue

        # 対象マッチ！
        video_data = {
            "id": v_id,
            "title": title,
            "duration_sec": duration_sec,
            "duration_str": duration_str,
            "published_at": published_at,
            "thumbnail_url": thumb_url,
            "url": f"https://www.youtube.com/watch?v={v_id}"
        }
        matched_videos.append(video_data)
        print(f"  🎯 対象ヒッ卜! [{duration_str}] {title}")

    if max_limit and len(matched_videos) > max_limit:
        print(f"ℹ️ 最大件数制限により {max_limit} 件に制限します。")
        matched_videos = matched_videos[:max_limit]

    print(f"\n判定結果: 2分以下の新着動画 {len(matched_videos)} 件がヒットしました。")

    if not matched_videos:
        print("追加対象の新しい動画はありません。")
        return {
            "status": "success",
            "added_count": 0,
            "message": "追加対象の動画はありませんでした。"
        }

    if dry_run:
        print("\n[ドライラン終了] 実際に再生リストへ変更は行われていません。")
        return {
            "status": "dry_run_success",
            "matched_videos": matched_videos
        }

    if not auto_mode:
        ans = input(f"\n再生リスト 『{playlist_name}』 に {len(matched_videos)} 件の動画を追加しますか？ (Y/n): ").strip().lower()
        if ans == "n":
            print("操作をキャンセルしました。")
            return {"status": "cancelled", "message": "ユーザーによりキャンセルされました"}

    # 追加処理の実行
    print("\n[処理中] 再生リストへ動画を追加しています...")
    added_count = 0
    for v in matched_videos:
        time.sleep(0.5)  # API連打防止
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
                return {
                    "status": "quota_exceeded",
                    "added_count": added_count,
                    "message": "API利用制限上限に達しました。"
                }
            else:
                print(f"  ❌ 追加失敗: {v['title']} ({e})")

    print(f"\n✨ 完了: {added_count} 件の動画を 『{playlist_name}』 に追加しました！")
    return {
        "status": "success",
        "added_count": added_count,
        "playlist_name": playlist_name,
        "playlist_id": playlist_id
    }

def main():
    parser = argparse.ArgumentParser(description="テレ東BIZダイジェスト 2分以下動画 自動再生リスト集約ツール")
    parser.add_argument("--auto", action="store_true", help="確認プロンプトを出さずに自動追加します")
    parser.add_argument("--dry-run", action="store_true", help="プレビュー表示のみを行い、追加を行いません")
    parser.add_argument("--limit", type=int, default=None, help="一回に追加する最大動画数")
    args = parser.parse_args()

    run_sync(auto_mode=args.auto, dry_run=args.dry_run, max_limit=args.limit)

if __name__ == "__main__":
    main()
