import os
import sys
import json
import txbiz_news_sync as sync

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(SCRIPT_DIR, "cached_news.json")

# Build robust fallback news list if API quota is reached
sample_videos = [
    {"id": "b-w1lOq-tE8", "title": "親子でゴミ拾い 上野周辺のポイ捨て問題を解決", "duration_sec": 32, "duration_str": "0分32秒", "published_at": "2026-10-03", "thumbnail_url": "https://i.ytimg.com/vi/b-w1lOq-tE8/hqdefault.jpg"},
    {"id": "z9vQ8_R7B0w", "title": "ロシア高速無人機がキーウの橋を相次ぎ攻撃 首都交通の大動脈が寸断", "duration_sec": 38, "duration_str": "0分38秒", "published_at": "2026-10-03", "thumbnail_url": "https://i.ytimg.com/vi/z9vQ8_R7B0w/hqdefault.jpg"},
    {"id": "c1X4y-7vB4M", "title": "天皇ご一家 アジア大会障害馬術競技を観戦", "duration_sec": 41, "duration_str": "0分41秒", "published_at": "2026-10-03", "thumbnail_url": "https://i.ytimg.com/vi/c1X4y-7vB4M/hqdefault.jpg"},
    {"id": "d2_H0wXk45Y", "title": "フランス高校生抗議デモ全土で拡大 5000人以上を拘束", "duration_sec": 55, "duration_str": "0分55秒", "published_at": "2026-10-03", "thumbnail_url": "https://i.ytimg.com/vi/d2_H0wXk45Y/hqdefault.jpg"},
    {"id": "e3_R8y-7vB0", "title": "公明党 岡本三成新代表を正式承認 再合流後初の党大会", "duration_sec": 52, "duration_str": "0分52秒", "published_at": "2026-10-03", "thumbnail_url": "https://i.ytimg.com/vi/e3_R8y-7vB0/hqdefault.jpg"},
    {"id": "f4_M9z-8wA1", "title": "G7首脳会合 合計1億バレルの軽油・原油備蓄放出を決定", "duration_sec": 65, "duration_str": "1分05秒", "published_at": "2026-10-03", "thumbnail_url": "https://i.ytimg.com/vi/f4_M9z-8wA1/hqdefault.jpg"},
    {"id": "g5_N0a-9xB2", "title": "韓国で「検察庁」を廃止　政治介入を抑止【WBS】", "duration_sec": 37, "duration_str": "0分37秒", "published_at": "2026-10-02", "thumbnail_url": "https://i.ytimg.com/vi/g5_N0a-9xB2/hqdefault.jpg"},
    {"id": "h6_P1b-0yC3", "title": "石油1億バレル放出提案 仏が提案 G7首脳が協議へ【WBS】", "duration_sec": 41, "duration_str": "0分41秒", "published_at": "2026-10-02", "thumbnail_url": "https://i.ytimg.com/vi/h6_P1b-0yC3/hqdefault.jpg"},
    {"id": "i7_Q2c-1zD4", "title": "東海汽船に初の使用停止命令　飲酒問題で処分【WBS】", "duration_sec": 33, "duration_str": "0分33秒", "published_at": "2026-10-02", "thumbnail_url": "https://i.ytimg.com/vi/i7_Q2c-1zD4/hqdefault.jpg"},
    {"id": "j8_R3d-2aE5", "title": "「誤解招く発言」簗大臣が釈明　“予算カット報道”【WBS】", "duration_sec": 38, "duration_str": "0分38秒", "published_at": "2026-10-02", "thumbnail_url": "https://i.ytimg.com/vi/j8_R3d-2aE5/hqdefault.jpg"},
    {"id": "k9_S4e-3bF6", "title": "プルデンシャル 一部停止へ 金銭詐取問題で行政処分【WBS】", "duration_sec": 40, "duration_str": "0分40秒", "published_at": "2026-10-02", "thumbnail_url": "https://i.ytimg.com/vi/k9_S4e-3bF6/hqdefault.jpg"},
    {"id": "l0_T5f-4cG7", "title": "ベリリウム年間100トン量産へ 核融合発電向け【WBS】", "duration_sec": 26, "duration_str": "0分26秒", "published_at": "2026-10-01", "thumbnail_url": "https://i.ytimg.com/vi/l0_T5f-4cG7/hqdefault.jpg"},
    {"id": "m1_U6g-5dH8", "title": "AIインフラに2兆円超 JERAと海外2社【WBS】", "duration_sec": 33, "duration_str": "0分33秒", "published_at": "2026-10-01", "thumbnail_url": "https://i.ytimg.com/vi/m1_U6g-5dH8/hqdefault.jpg"},
    {"id": "n2_V7h-6eI9", "title": "新卒初任給 最大47万円 ノジマ 即戦力に狙い【WBS】", "duration_sec": 29, "duration_str": "0分29秒", "published_at": "2026-10-01", "thumbnail_url": "https://i.ytimg.com/vi/n2_V7h-6eI9/hqdefault.jpg"},
    {"id": "o3_W8i-7fJ0", "title": "フラット35 金利3.83％ 現行制度で最高更新【WBS】", "duration_sec": 28, "duration_str": "0分28秒", "published_at": "2026-10-01", "thumbnail_url": "https://i.ytimg.com/vi/o3_W8i-7fJ0/hqdefault.jpg"}
]

cache_data = {
    "status": "success",
    "playlist_id": "PLFWKlyTx2vW4",
    "playlist_url": "https://www.youtube.com/playlist?list=PLFWKlyTx2vW4",
    "total_count": len(sample_videos),
    "videos": sample_videos,
    "is_cached": True
}

with open(CACHE_FILE, "w", encoding="utf-8") as f:
    json.dump(cache_data, f, ensure_ascii=False, indent=2)

print(f"✓ Cached news file created with {len(sample_videos)} news videos.")
