import os
import sys
import json
import urllib.parse
from http.server import HTTPServer, SimpleHTTPRequestHandler
import txbiz_news_sync as sync

PORT = 8000
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(SCRIPT_DIR, "cached_news.json")
STATS_FILE = os.path.join(SCRIPT_DIR, "visit_stats.json")

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

def get_and_increment_visit_count():
    count = 0
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                count = data.get("visit_count", 0)
        except Exception:
            pass
    count += 1
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump({"visit_count": count}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Stats save error: {e}")
    return count

def load_cached_videos():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def save_cached_videos(data):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Cache save error: {e}")

class NewsWebHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        parsed = urllib.parse.urlparse(path)
        rel_path = parsed.path.lstrip('/')
        if not rel_path:
            rel_path = 'index.html'
        return os.path.join(SCRIPT_DIR, rel_path)

    def do_GET(self):
        if self.path.startswith('/api/news'):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            visit_count = get_and_increment_visit_count()
            cached_data = load_cached_videos()

            try:
                youtube = sync.get_youtube_service(allow_interactive=False)
                playlist_id = sync.get_or_create_target_playlist(youtube)
                items = sync.fetch_playlist_items(youtube, playlist_id)

                if items:
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
                            dur_sec = sync.parse_iso8601_duration(dur_iso)
                            dur_str = sync.format_seconds(dur_sec)
                            thumbs = item["snippet"].get("thumbnails", {})
                            thumb_url = thumbs.get("medium", {}).get("url", thumbs.get("default", {}).get("url", ""))
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
                            "thumbnail_url": det.get("thumbnail_url", ""),
                            "url": f"https://www.youtube.com/watch?v={vid}"
                        })

                    res_data = {
                        "status": "success",
                        "playlist_id": playlist_id,
                        "playlist_url": f"https://www.youtube.com/playlist?list={playlist_id}",
                        "total_count": len(videos),
                        "videos": videos,
                        "visit_count": visit_count,
                        "is_cached": False
                    }
                    save_cached_videos(res_data)
                    self.wfile.write(json.dumps(res_data, ensure_ascii=False).encode('utf-8'))
                    return
            except Exception as e:
                print(f"Notice: Serving cached news due to API state ({e})")

            # Fallback to cached data if API failed or hit quota
            if cached_data and "videos" in cached_data and cached_data["videos"]:
                cached_data["status"] = "success"
                cached_data["is_cached"] = True
                cached_data["visit_count"] = visit_count
                if "quotaExceeded" in str(e):
                    cached_data["notice"] = "YouTube APIの本日の利用上限に達したため、キャッシュされた最新ニュースデータを表示しています。"
                else:
                    cached_data.pop("notice", None)
                self.wfile.write(json.dumps(cached_data, ensure_ascii=False).encode('utf-8'))
            else:
                err_res = {
                    "status": "error",
                    "message": "ニュースデータの取得に失敗しました。最新のキャッシュを作成するには「2_対話実行_手動同期.bat」を実行してください。",
                    "videos": [],
                    "visit_count": visit_count
                }
                self.wfile.write(json.dumps(err_res, ensure_ascii=False).encode('utf-8'))
            return

        super().do_GET()

def run_server():
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, NewsWebHandler)
    print(f"🚀 テレ東BIZ 2分ニュース 専用Webページサーバー起動中: http://localhost:{PORT}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nサーバーを停止します。")

if __name__ == "__main__":
    run_server()
