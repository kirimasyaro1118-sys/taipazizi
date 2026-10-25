import os
import re
import sys
import json
import time
import datetime
import subprocess
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# UTF-8出力の設定 (Windows用)
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

# 固定的要件定義
CHANNEL_HANDLE = "tvtokyobiz"
CHANNEL_QUERY = "テレ東BIZ ダイジェスト"
TARGET_PLAYLIST_NAME = "テレ東短動画リスト"
MAX_DURATION_SECONDS = 120          # 2分（120秒）以下
EXCLUDE_KEYWORDS = ["天気"]          # 「天気」を含む動画を除外
MIN_PUBLISH_DATE_STR = "2026-10-01T00:00:00Z"  # システム全体の最古基準日（10/01以降の動画を保持）
SEARCH_SINCE_DATE_STR = "2026-10-21T00:00:00Z" # 探索対象期間（時短用: 10/21以降の新着を走査）
MAX_PLAYLIST_CAPACITY = 500         # 再生リストの最大保持件数（500件）

def run_interactive_oauth(flow, port=0):
    """Google OAuth認証用のローカルサーバーを起動し、ブラウザを開いてトークンを取得します。"""
    import wsgiref.simple_server
    import webbrowser
    from google_auth_oauthlib.flow import _RedirectWSGIApp, _ExclusiveWSGIServer, _WSGIRequestHandler

    wsgi_app = _RedirectWSGIApp("認証が完了しました！ブラウザを閉じて元の画面にお戻りください。")
    local_server = wsgiref.simple_server.make_server(
        "localhost",
        port,
        wsgi_app,
        server_class=_ExclusiveWSGIServer,
        handler_class=_WSGIRequestHandler,
    )

    try:
        flow.redirect_uri = f"http://localhost:{local_server.server_port}/"
        auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')

        print(f"\n========================================================", flush=True)
        print(f"🔑 Google アカウント認証用URL:\n{auth_url}", flush=True)
        print(f"========================================================\n", flush=True)

        auth_file = os.path.join(SCRIPT_DIR, "last_auth_url.txt")
        try:
            with open(auth_file, "w", encoding="utf-8") as f:
                f.write(auth_url)
        except Exception:
            pass

        try:
            os.startfile(auth_url)
        except Exception:
            try:
                webbrowser.open(auth_url)
            except Exception:
                pass

        print("ブラウザで Google アカウントの認証を行ってください（待機中...）", flush=True)
        local_server.timeout = 180
        local_server.handle_request()

        authorization_response = wsgi_app.last_request_uri.replace("http", "https")
        flow.fetch_token(authorization_response=authorization_response)
        return flow.credentials
    finally:
        local_server.server_close()

def get_youtube_service(allow_interactive=True):
    """OAuth認証を行い、YouTube APIサービスオブジェクトを取得します。"""
    creds = None
    if os.path.exists(TOKEN_FILE):
        try:
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            print(f"[警告] トークン読み込みエラー: {e}", flush=True)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                print("🔄 既存トークンの自動更新を試行中...", flush=True)
                creds.refresh(Request())
            except Exception as e:
                print(f"[警告] トークン再更新エラー: {e}。再認証を行います。", flush=True)
                creds = None

        if not creds or not creds.valid:
            if not allow_interactive:
                raise RuntimeError("OAuth認証トークンが無効または存在しません。インタラクティブ認証をスキップします。")
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(f"[エラー] '{CREDENTIALS_FILE}' が見つかりません。")
            if os.path.exists(TOKEN_FILE):
                try:
                    os.remove(TOKEN_FILE)
                except Exception:
                    pass
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            print("🔑 ブラウザを開いて Google アカウント認証を行います...", flush=True)
            creds = run_interactive_oauth(flow)

        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
        print("✓ 認証トークンを保存しました (token.json)", flush=True)

    return build("youtube", "v3", credentials=creds)

def parse_iso8601_duration(duration_str):
    """ISO 8601形式の動画時間を秒数に変換します。"""
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

def get_channel_uploads_id(youtube):
    """「テレ東BIZ ダイジェスト」のアップロード動画再生リストID（UU...）を取得します。"""
    # 1. ハンドル @tvtokyobiz
    try:
        res = youtube.channels().list(
            forHandle=CHANNEL_HANDLE,
            part="snippet,contentDetails"
        ).execute()
        items = res.get("items", [])
        if items:
            ch_title = items[0]["snippet"]["title"]
            uploads_id = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
            print(f"✓ チャンネル検出 [@{CHANNEL_HANDLE}]: 『{ch_title}』")
            return uploads_id
    except Exception:
        pass

    # 2. 検索クエリ fallback
    try:
        res = youtube.search().list(
            q=CHANNEL_QUERY,
            type="channel",
            part="snippet",
            maxResults=1
        ).execute()
        items = res.get("items", [])
        if items:
            ch_id = items[0]["snippet"]["channelId"]
            ch_title = items[0]["snippet"]["title"]
            uploads_id = "UU" + ch_id[2:]
            print(f"✓ チャンネル検出 [{CHANNEL_QUERY}]: 『{ch_title}』")
            return uploads_id
    except Exception as e:
        print(f"❌ チャンネル検出失敗: {e}")

    return None

def get_or_create_target_playlist(youtube):
    """再生リスト 『ニュース』 を取得または作成し、限定公開(unlisted)に設定します。"""
    next_page_token = None
    while True:
        request = youtube.playlists().list(
            part="snippet,status",
            mine=True,
            maxResults=50,
            pageToken=next_page_token
        )
        response = request.execute()
        for item in response.get("items", []):
            if item["snippet"]["title"].strip().lower() == TARGET_PLAYLIST_NAME.strip().lower():
                pid = item["id"]
                # 公開設定を限定公開 (unlisted) に確保
                if item.get("status", {}).get("privacyStatus") != "unlisted":
                    try:
                        youtube.playlists().update(
                            part="snippet,status",
                            body={
                                "id": pid,
                                "snippet": {
                                    "title": TARGET_PLAYLIST_NAME,
                                    "description": "テレ東BIZダイジェストの2分以下短尺ニュース（限定公開・共有用）"
                                },
                                "status": {
                                    "privacyStatus": "unlisted"
                                }
                            }
                        ).execute()
                        print(f"✓ 再生リスト 『{TARGET_PLAYLIST_NAME}』 の公開設定を『限定公開 (unlisted)』に変更しました。")
                    except Exception as e:
                        print(f"⚠️ 公開設定の更新スキップ: {e}")
                print(f"✓ 再生リスト 『{TARGET_PLAYLIST_NAME}』 を検出しました (ID: {pid})")
                return pid
        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    # 無い場合は作成
    print(f"ℹ️ 再生リスト 『{TARGET_PLAYLIST_NAME}』 を新規作成（限定公開）します...")
    created = youtube.playlists().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": TARGET_PLAYLIST_NAME,
                "description": "テレ東BIZダイジェストの2分以下短尺ニュース（限定公開・共有用）"
            },
            "status": {
                "privacyStatus": "unlisted"
            }
        }
    ).execute()
    print(f"✨ 再生リスト 『{TARGET_PLAYLIST_NAME}』 を作成しました！ (ID: {created['id']})")
    return created["id"]

def fetch_playlist_items(youtube, playlist_id):
    """再生リスト内の全アイテム（playlistItemId, videoId, position）を取得します。"""
    items = []
    next_page_token = None
    while True:
        try:
            request = youtube.playlistItems().list(
                part="snippet",
                playlistId=playlist_id,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
            for item in response.get("items", []):
                items.append({
                    "playlistItemId": item["id"],
                    "videoId": item["snippet"]["resourceId"]["videoId"],
                    "title": item["snippet"]["title"],
                    "position": item["snippet"]["position"]
                })
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break
        except HttpError as e:
            # 新規作成直後や動画数0の再生リストで404エラーが発生した場合は空リストを返す
            if "playlistNotFound" in str(e) or e.resp.status == 404:
                return []
            raise e
    return items

def cleanup_playlist_capacity(youtube, playlist_id):
    """再生リストの件数が500件を超えている場合、古い動画から順番に自動削除します。"""
    items = fetch_playlist_items(youtube, playlist_id)
    if not items:
        return

    if len(items) > MAX_PLAYLIST_CAPACITY:
        excess = len(items) - MAX_PLAYLIST_CAPACITY
        print(f"\n⚠️ 再生リストの件数 ({len(items)}件) が最大容量 ({MAX_PLAYLIST_CAPACITY}件) を超えています。")
        print(f"古い動画から {excess} 件を自動削除します...")

        old_items_to_delete = items[:excess]
        for item in old_items_to_delete:
            try:
                youtube.playlistItems().delete(id=item["playlistItemId"]).execute()
                print(f"  - 削除（500件容量上限超過）: {item['title']}")
                time.sleep(0.3)
            except Exception as e:
                print(f"  ❌ 削除失敗: {item['title']} ({e})")

def main():
    print("=" * 65)
    print(" テレ東BIZ ダイジェスト ニュース再生リスト自動同期 ")
    print(f" 実行日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 65)

    try:
        youtube = get_youtube_service()
        print("✓ OAuth 認証成功")
    except Exception as e:
        print(f"❌ 認証エラー: {e}")
        return

    # 1. ターゲット再生リスト「ニュース」の準備
    try:
        playlist_id = get_or_create_target_playlist(youtube)
    except HttpError as e:
        if "quotaExceeded" in str(e):
            print("🛑 API本日の上限(10,000 units)に達しました。明日16時以降に再開されます。")
            return
        raise e

    # 2. 40件上限超過分の古い動画整理
    try:
        cleanup_playlist_capacity(youtube, playlist_id)
    except HttpError as e:
        if "quotaExceeded" in str(e):
            print("🛑 本日の API 利用上限 (10,000 units) に達しました。本日16時以降に再開されます。")
            print(f"🔗 共有用URL (限定公開): https://www.youtube.com/playlist?list={playlist_id}")
            return
        raise e

    # 3. 既存の登録動画IDリストを取得（重複防止用）
    existing_items = fetch_playlist_items(youtube, playlist_id)
    existing_video_ids = {item["videoId"] for item in existing_items}

    # 4. 「テレ東BIZ ダイジェスト」の新着動画を取得
    uploads_id = get_channel_uploads_id(youtube)
    if not uploads_id:
        print("❌ アップロード再生リストが取得できませんでした。")
        return

    search_min_dt = datetime.datetime.fromisoformat(SEARCH_SINCE_DATE_STR.replace("Z", "+00:00"))
    min_publish_dt = datetime.datetime.fromisoformat(MIN_PUBLISH_DATE_STR.replace("Z", "+00:00"))
    recent_items = []
    next_page_token = None
    page_count = 0

    print(f"\n📡 チャンネル新着動画を探索中（探索範囲: {SEARCH_SINCE_DATE_STR[:10]} 以降）...")
    while True:
        page_count += 1
        res = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_id,
            maxResults=50,
            pageToken=next_page_token
        ).execute()

        items = res.get("items", [])
        if not items:
            break

        stop_paging = False
        for item in items:
            published_at_str = item["snippet"].get("publishedAt", "")
            if published_at_str:
                pub_dt = datetime.datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
                if pub_dt < search_min_dt:
                    stop_paging = True
                    break
            recent_items.append(item)

        print(f"  - ページ {page_count}: {len(items)} 件チェック（対象候補: {len(recent_items)} 件）")

        if stop_paging:
            break

        next_page_token = res.get("nextPageToken")
        if not next_page_token:
            break

    video_ids = [item["snippet"]["resourceId"]["videoId"] for item in recent_items]
    if not video_ids:
        print("対象の新着動画はありませんでした。")
        return

    # 動画の詳細情報（再生時間、公開日時）を50件ずつバッチ取得
    details_map = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        vid_response = youtube.videos().list(
            part="snippet,contentDetails",
            id=",".join(batch)
        ).execute()
        for item in vid_response.get("items", []):
            v_id = item["id"]
            title = item["snippet"]["title"]
            published_at_str = item["snippet"]["publishedAt"]
            duration_iso = item.get("contentDetails", {}).get("duration", "PT0S")
            duration_sec = parse_iso8601_duration(duration_iso)
            duration_str = format_seconds(duration_sec)
            details_map[v_id] = {
                "title": title,
                "published_at": published_at_str,
                "duration_sec": duration_sec,
                "duration_str": duration_str
            }

    matched_videos = []
    print("\n--- 新着動画チェック判定 ---")
    for v_id in video_ids:
        info = details_map.get(v_id)
        if not info:
            continue

        title = info["title"]
        published_at_str = info["published_at"]
        published_dt = datetime.datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
        duration_sec = info["duration_sec"]
        duration_str = info["duration_str"]

        # 条件1: 探索対象日（10/21）以降の動画か
        if published_dt < search_min_dt:
            print(f"  ⏭️ スキップ (探索対象日以前: {published_at_str[:10]}): {title}")
            continue

        # 条件2: すでに「ニュース」再生リストに存在するか
        if v_id in existing_video_ids:
            print(f"  ⏭️ スキップ (追加済み): [{duration_str}] {title}")
            continue

        # 条件3: 長さが 2分 (120秒) 以下か (1秒〜120秒)
        if duration_sec <= 0 or duration_sec > MAX_DURATION_SECONDS:
            print(f"  ⏭️ スキップ (2分超過または配信予定: {duration_str}): {title}")
            continue

        # 条件4: 除外キーワード「天気」が含まれていないか
        if any(kw in title for kw in EXCLUDE_KEYWORDS):
            print(f"  ⏭️ スキップ (NGワード「天気」検出): {title}")
            continue

        matched_videos.append({
            "id": v_id,
            "title": title,
            "duration_str": duration_str,
            "published_at": published_at_str
        })
        print(f"  🎯 追加対象ヒット! [{duration_str}] ({published_at_str[:10]}) {title}")

    # 古い順に追加して再生リストの時系列順序を維持
    matched_videos.reverse()

    if not matched_videos:
        print("\n追加対象の新しいニュース動画はありませんでした。")
    else:
        print(f"\n[実行中] {len(matched_videos)} 件の動画を再生リスト 『{TARGET_PLAYLIST_NAME}』 に追加します...")
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
                    print("\n🛑 API本日の上限に達したため、残りの追加を中断します。")
                    break
                else:
                    print(f"  ❌ 追加失敗: {v['title']} ({e})")

        print(f"\n✨ 完了: {added_count} 件の短尺ニュースを 『{TARGET_PLAYLIST_NAME}』 に追加しました！")

    print(f"🔗 共有用URL (限定公開): https://www.youtube.com/playlist?list={playlist_id}")

    # 5. 最新キャッシュ (cached_news.json) の更新
    print("\n--- Webサイト用最新ニュースキャッシュの生成 ---")
    update_cached_news(youtube, playlist_id)

    # 6. GitHub Pages への自動プッシュ
    print("\n--- GitHub Pages への最新化同期 ---")
    sync_git_repo()

def update_cached_news(youtube, playlist_id):
    """最新の再生リスト内容を取得して cached_news.json を更新します。"""
    try:
        items = fetch_playlist_items(youtube, playlist_id)
        if not items:
            return False

        v_ids = [it["videoId"] for it in items]
        details_map = {}
        for i in range(0, len(v_ids), 50):
            batch = v_ids[i:i+50]
            v_res = youtube.videos().list(
                part="snippet,contentDetails",
                id=",".join(batch)
            ).execute()
            for item in v_res.get("items", []):
                vid = item["id"]
                dur_iso = item.get("contentDetails", {}).get("duration", "PT0S")
                dur_sec = parse_iso8601_duration(dur_iso)
                dur_str = format_seconds(dur_sec)
                thumbs = item["snippet"].get("thumbnails", {})
                thumb_url = thumbs.get("medium", {}).get("url", thumbs.get("default", {}).get("url", f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"))
                details_map[vid] = {
                    "duration_sec": dur_sec,
                    "duration_str": dur_str,
                    "published_at": item["snippet"].get("publishedAt", "")[:10],
                    "thumbnail_url": thumb_url
                }

        videos = []
        for it in items:
            vid = it["videoId"]
            det = details_map.get(vid, {})
            videos.append({
                "id": vid,
                "title": it["title"],
                "duration_sec": det.get("duration_sec", 0),
                "duration_str": det.get("duration_str", "0分00秒"),
                "published_at": det.get("published_at", ""),
                "thumbnail_url": det.get("thumbnail_url", f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"),
                "url": f"https://www.youtube.com/watch?v={vid}"
            })

        visit_count = 0
        cache_file = os.path.join(SCRIPT_DIR, "cached_news.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                    visit_count = old_data.get("visit_count", 0)
            except Exception:
                pass

        stats_file = os.path.join(SCRIPT_DIR, "visit_stats.json")
        if os.path.exists(stats_file):
            try:
                with open(stats_file, "r", encoding="utf-8") as f:
                    visit_count = max(visit_count, json.load(f).get("visit_count", 0))
            except Exception:
                pass

        cache_data = {
            "status": "success",
            "playlist_id": playlist_id,
            "playlist_url": f"https://www.youtube.com/playlist?list={playlist_id}",
            "total_count": len(videos),
            "videos": videos,
            "visit_count": visit_count,
            "is_cached": False,
            "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        print(f"✓ キャッシュファイル（cached_news.json）を {len(videos)} 件の動画で更新しました。", flush=True)
        return True
    except Exception as e:
        print(f"⚠️ キャッシュ更新エラー: {e}", flush=True)
        return False

def sync_git_repo():
    """GitHubリポジトリへの最新キャッシュのコミット＆プッシュを行います。"""
    git_cmd = r"C:\Users\katad\AppData\Local\GitHubDesktop\app-3.6.7\resources\app\git\cmd\git.exe"
    if not os.path.exists(git_cmd):
        git_cmd = "git"
    try:
        status = subprocess.run([git_cmd, "status", "--porcelain"], cwd=SCRIPT_DIR, capture_output=True, text=True, check=True)
        if "cached_news.json" in status.stdout:
            print("📦 変更されたキャッシュデータを GitHub にプッシュします...", flush=True)
            subprocess.run([git_cmd, "add", "cached_news.json"], cwd=SCRIPT_DIR, check=True)
            commit_msg = f"Update news cache: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
            subprocess.run([git_cmd, "commit", "-m", commit_msg], cwd=SCRIPT_DIR, check=True)
            subprocess.run([git_cmd, "push", "origin", "main"], cwd=SCRIPT_DIR, check=True)
            print("🚀 GitHub Pages への最新キャッシュ同期が完了しました！", flush=True)
        else:
            print("✓ GitHub リポジトリのキャッシュデータは最新です（変更なし）。", flush=True)
    except Exception as e:
        print(f"⚠️ Git同期スキップ: {e}", flush=True)

if __name__ == "__main__":
    main()
