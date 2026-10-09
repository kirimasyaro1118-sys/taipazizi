import os
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
                raise FileNotFoundError(f"'{CREDENTIALS_FILE}' が見つかりません。同じフォルダに配置してください。")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return build("youtube", "v3", credentials=creds)

def list_my_playlists(youtube):
    """ログイン中のユーザーの再生リスト一覧を取得して表示します。"""
    playlists = []
    next_page_token = None
    
    print("\n--- 取得中: 自分の再生リスト一覧 ---")
    while True:
        try:
            request = youtube.playlists().list(
                part="snippet,contentDetails",
                mine=True,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request.execute()
        except HttpError as e:
            if "has not been used" in str(e) or "disabled" in str(e):
                print("\n[エラー] YouTube Data API v3 がまだ有効化されていません。")
                print("以下のURLにアクセスし、「有効にする」を押してください:")
                print("https://console.cloud.google.com/apis/library/youtube.googleapis.com\n")
            raise e

        for item in response.get("items", []):
            p_info = {
                "id": item["id"],
                "title": item["snippet"]["title"],
                "itemCount": item["contentDetails"]["itemCount"]
            }
            playlists.append(p_info)

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    for idx, p in enumerate(playlists, 1):
        print(f"[{idx}] {p['title']} (動画数: {p['itemCount']}件) - ID: {p['id']}")
    
    return playlists

def fetch_playlist_items(youtube, playlist_id):
    """指定された再生リストのすべての動画情報を取得します。"""
    items = []
    next_page_token = None

    while True:
        request = youtube.playlistItems().list(
            part="snippet,contentDetails",
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
                "channelTitle": item["snippet"].get("videoOwnerChannelTitle", item["snippet"].get("channelTitle", "")),
                "position": item["snippet"]["position"]
            })

        next_page_token = response.get("nextPageToken")
        if not next_page_token:
            break

    return items

def backup_playlist(playlist_id, playlist_title, items):
    """作業前に元の再生リストのバックアップを保存します。"""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{playlist_id}_{timestamp}.json"
    data = {
        "playlistId": playlist_id,
        "playlistTitle": playlist_title,
        "backupTime": timestamp,
        "items": items
    }
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[安全機能] バックアップを保存しました: {filename}")
    return filename

def process_videos(youtube, source_id, target_id, keyword="", dry_run=True, delete_from_source=False, limit=None):
    """条件に合う動画を検索し、移動またはコピーを行います。"""
    print(f"\n--- 動画の抽出・処理中 (ドライラン: {'ON (プレビューのみ)' if dry_run else 'OFF (実際に実行)'}) ---")
    
    items = fetch_playlist_items(youtube, source_id)
    print(f"移動元リスト内の全動画数: {len(items)}件")

    if not dry_run:
        backup_playlist(source_id, "Source Playlist", items)

    matched = []
    for item in items:
        title = item["title"]
        channel = item["channelTitle"]
        
        # キーワード条件のチェック (大文字小文字を区別しない)
        if keyword.lower() in title.lower() or keyword.lower() in channel.lower():
            matched.append(item)

    print(f"条件 『{keyword}』 に一致した動画: {len(matched)}件")
    if limit and len(matched) > limit:
        print(f"[制限] 安全のため一度に最大 {limit} 件まで処理します。")
        matched = matched[:limit]

    for idx, item in enumerate(matched, 1):
        print(f"  {idx}. [{item['channelTitle']}] {item['title']} (Video ID: {item['videoId']})")

    if not matched:
        print("該当する動画が見つかりませんでした。")
        return

    if dry_run:
        print("\n[確認] ドライラン（プレビュー）のため、再生リストは変更されていません。")
        print("実際に実行する場合は dry_run=False で実行してください。")
        return

    # 本番実行
    print("\n[実行中] ターゲット再生リストへ追加しています...")
    for item in matched:
        time.sleep(0.5)  # 連打制限対策（0.5秒ウェイト）
        
        # 最大3回リトライ
        max_retries = 3
        success = False
        
        for attempt in range(1, max_retries + 1):
            try:
                # 移動先に追加
                youtube.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": target_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": item["videoId"]
                            }
                        }
                    }
                ).execute()
                print(f"  ✓ 追加完了: {item['title']}")
                success = True

                # 移動元から削除（オプション）
                if delete_from_source:
                    youtube.playlistItems().delete(id=item["playlistItemId"]).execute()
                    print(f"  - 元リストから削除完了: {item['title']}")
                break  # 成功したらリトライループを抜ける

            except HttpError as e:
                err_str = str(e)
                # 一時的な通信・サーバー混雑エラー（409 SERVICE_UNAVAILABLE / 503 等）の場合はリトライ
                if ("SERVICE_UNAVAILABLE" in err_str or "409" in err_str or "503" in err_str) and attempt < max_retries:
                    print(f"  🔄 サーバー混雑のため再試行中 ({attempt}/{max_retries}): {item['title']}")
                    time.sleep(1.5)
                    continue

                # クォータ上限エラーの判定
                if "quotaExceeded" in err_str:
                    print("\n" + "!" * 60)
                    print("🛑 本日の YouTube API 利用制限上限 (10,000 units/日) に達しました。")
                    print("   APIの仕様上、本日分の上限を超えたためこれ以上の操作は行えません。")
                    print("   【リセット日時】毎日 日本時間 16:00 (午後4時) に自動リセットされます。")
                    print("   16:00 以降に再度スクリプトを実行していただければ続きを行えます。")
                    print("!" * 60 + "\n")
                    return

                # リトライ不可のエラー判定
                if "videoNotFound" in err_str or "404" in err_str:
                    print(f"  ⚠️ スキップ (削除済み動画のため追加不可): {item['title']}")
                    if delete_from_source:
                        try:
                            youtube.playlistItems().delete(id=item["playlistItemId"]).execute()
                            print(f"  - 元リストから削除完了 (削除済み動画): {item['title']}")
                        except Exception:
                            pass
                elif "failedPrecondition" in err_str or "Private video" in item["title"] or "private" in err_str.lower():
                    print(f"  ⚠️ スキップ (非公開動画のため追加不可): {item['title']}")
                    if delete_from_source:
                        try:
                            youtube.playlistItems().delete(id=item["playlistItemId"]).execute()
                            print(f"  - 元リストから削除完了 (非公開動画): {item['title']}")
                        except Exception:
                            pass
                else:
                    print(f"  ❌ エラーのためスキップ: {item['title']} ({e})")
                break

    print("\n✨ 処理が正常に完了しました！")

def main():
    print("=" * 60)
    print(" YouTube 再生リスト動画移動・安全整理ツール ")
    print("=" * 60)

    try:
        youtube = get_youtube_service()
        print("✓ OAuth 認証に成功しました。")
    except Exception as e:
        print(f"認証エラーが発生しました: {e}")
        return

    while True:
        print("\n--- メニュー ---")
        print("1. 自分の再生リスト一覧を表示")
        print("2. 条件に合う動画を検索・シミュレーション (ドライラン)")
        print("3. 条件に合う動画を実際に移動/コピーする (本番実行)")
        print("0. 終了")
        
        choice = input("番号を選択してください: ").strip()

        if choice == "1":
            try:
                list_my_playlists(youtube)
            except HttpError as e:
                if "quotaExceeded" in str(e):
                    print("\n🛑 本日の YouTube API 利用制限上限 (10,000 units/日) に達しました。")
                    print("   【リセット日時】毎日 日本時間 16:00 (午後4時) に自動リセットされます。\n")
        elif choice in ["2", "3"]:
            dry_run = (choice == "2")
            try:
                playlists = list_my_playlists(youtube)
            except HttpError as e:
                if "quotaExceeded" in str(e):
                    print("\n🛑 本日の YouTube API 利用制限上限 (10,000 units/日) に達しました。")
                    print("   【リセット日時】毎日 日本時間 16:00 (午後4時) に自動リセットされます。\n")
                    continue
                raise e
            if not playlists:
                continue

            try:
                src_num = int(input("\n移動『元』の再生リスト番号を入力してください: ")) - 1
                tgt_num = int(input("移動『先』の再生リスト番号を入力してください: ")) - 1

                source_id = playlists[src_num]["id"]
                target_id = playlists[tgt_num]["id"]

                keyword = input("検索キーワード (タイトルやチャンネル名の一部、空エンターで全動画対象): ").strip()
                
                delete_source = False
                if not dry_run:
                    ans = input("移動元リストから動画を削除しますか？ (y/N): ").strip().lower()
                    delete_source = (ans == "y")

                process_videos(
                    youtube,
                    source_id=source_id,
                    target_id=target_id,
                    keyword=keyword,
                    dry_run=dry_run,
                    delete_from_source=delete_source,
                    limit=None  # 制限なし（該当する全動画を処理）
                )
            except (ValueError, IndexError):
                print("無効な番号が入力されました。")
        elif choice == "0":
            print("終了します。")
            break
        else:
            print("正しい番号を入力してください。")

if __name__ == "__main__":
    main()
