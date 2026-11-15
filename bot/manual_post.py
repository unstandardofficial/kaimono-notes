"""楽天の鍵が無くても動く、承認済み投稿の予約投稿。

data/manual_queue.json に {"slug", "text", "at"（日本時間ISO、省略可）} を並べておくと、
時刻を過ぎたものを1回の実行につき1ブランド1本ずつThreadsに投稿し、posted_id を書き戻す。
中身はすべて事前に人が承認した文面だけを入れる。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bot import social
from bot.main import Secrets

JST = timezone(timedelta(hours=9))
QUEUE = Path("data/manual_queue.json")


def run(now: datetime | None = None, path: Path = QUEUE, post=social.post_threads) -> int:
    now = now or datetime.now(JST)
    if not path.exists():
        print("予約投稿はありません")
        return 0
    items = json.loads(path.read_text(encoding="utf-8"))
    secrets, done_slugs, posted = Secrets(), set(), 0
    for it in items:
        if it.get("posted_id") or it.get("error") or it["slug"] in done_slugs:
            continue
        at = datetime.fromisoformat(it["at"]).replace(tzinfo=JST) if it.get("at") else now
        if at > now:
            continue
        done_slugs.add(it["slug"])
        try:
            it["posted_id"] = post(it["text"], None, secrets.get("THREADS_ACCESS_TOKEN", it["slug"]))
            it["posted_at"] = now.isoformat(timespec="minutes")
            posted += 1
            print(f"[{it['slug']}] 投稿しました")
        except social.SocialError as e:
            it["error"] = str(e)[:300]
            print(f"[{it['slug']}] 失敗: {e}")
    path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return posted


if __name__ == "__main__":
    run()
