"""複数アカウント（ブランド）を1つのリポジトリで回す。

GitHub Actions が毎時起動し、その時刻が run_hours に入っているアカウントだけを処理する:
1. 今日の記事数が上限に届いていなければ、楽天から商品を取って記事を1本作り、そのブランドのブログを作り直す
2. 投稿待ちのSNS文を、そのブランドのX・Threadsに1本ずつ投稿する（1日の上限まで）
3. 状態を data/ に保存する（ワークフローがコミットする）

同じ商品は、どのブランドでも二度と紹介しない（楽天の「複数アカウントで同じ内容」禁止への対策）。

試運転:  python -m bot.main --dry-run --all   （外部に接続せず preview/ に出力）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import site as sitegen
from . import curated
from .rakuten import Product, RakutenClient, RakutenError, parse_item, pick_products
from .social import SocialError, post_threads, post_x
from .writer import write_article, write_social

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "ranking_sample.json"


def load_json(path: Path, default):
    return json.loads(path.read_text("utf-8")) if path.exists() else default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")


class Secrets:
    """環境変数か、ワークフローが渡す SECRETS_JSON（全Secretsをまとめたもの）から鍵を読む。

    アカウント専用の鍵は「名前_スラッグ大文字」（例 THREADS_ACCESS_TOKEN_KITCHEN）。
    無ければ共通の名前（例 X_API_KEY）を使う。
    """

    def __init__(self):
        try:
            self.bundle = json.loads(os.environ.get("SECRETS_JSON") or "{}")
        except json.JSONDecodeError:
            self.bundle = {}

    def get(self, name: str, slug: str | None = None) -> str:
        names = ([f"{name}_{slug.upper()}"] if slug else []) + [name]
        for n in names:
            v = os.environ.get(n) or self.bundle.get(n)
            if v:
                return v
        return ""


def current_event(cfg: dict, now: datetime) -> str | None:
    for ev in cfg.get("events", []):
        start = datetime.fromisoformat(ev["start"]) - timedelta(days=ev.get("warmup_days", 0))
        if start <= now <= datetime.fromisoformat(ev["end"]):
            return ev["name"]
    return None


def load_accounts(root: Path) -> list[dict]:
    return [json.loads(p.read_text("utf-8")) for p in sorted((root / "accounts").glob("*.json"))]


def fetch_candidates(acct: dict, state: dict, event: str | None, client, today_count: int) -> tuple[str, list[Product]]:
    if isinstance(client, tuple):  # APIの代わりの売れ筋リスト（curated）
        return client
    if client is None:  # 試運転
        g = acct["genres"][0]
        raw = load_json(FIXTURE, {"Items": []})
        return g["name"], [parse_item(i, g["name"]) for i in raw.get("Items", [])]

    # セール中の2本目は「買いまわり向けの1,000円前後の送料無料品」
    if event and today_count >= 1 and acct.get("budget_keywords"):
        kws = acct["budget_keywords"]
        kw = kws[state.get("keyword_cursor", 0) % len(kws)]
        state["keyword_cursor"] = state.get("keyword_cursor", 0) + 1
        items = [p for p in client.search(kw) if 800 <= p.price <= 1600]
        return f"{event}の買いまわり向け 送料無料の{acct['genres'][0]['name']}", items

    genres = acct["genres"]
    for _ in range(len(genres)):
        g = genres[state.get("genre_cursor", 0) % len(genres)]
        state["genre_cursor"] = state.get("genre_cursor", 0) + 1
        try:
            products = client.ranking(g["id"], g["name"], 1) + client.ranking(g["id"], g["name"], 2)
        except RakutenError as e:
            print(f"[{acct['slug']}] ジャンル{g['id']}（{g['name']}）が取れませんでした。IDを確認してください: {e}")
            continue
        if products:
            return g["name"], products
    return "", []


def run_account(acct: dict, cfg: dict, now: datetime, secrets: Secrets, posted: dict,
                root: Path, dry_run: bool, site_root_url: str) -> bool:
    slug = acct["slug"]
    data_dir = root / ("preview_data" if dry_run else "data") / slug
    out_dir = root / ("preview" if dry_run else "docs") / slug
    state = load_json(data_dir / "state.json", {})
    posts = sitegen.load_posts(data_dir / "posts.json")
    site_url = f"{site_root_url}{slug}/"
    today = now.strftime("%Y-%m-%d")
    event = current_event(cfg, now)
    daily = state.setdefault("daily", {}).get(today, {"articles": 0, "x": 0, "threads": 0})
    keep_from = (now - timedelta(days=14)).strftime("%Y-%m-%d")
    state["daily"] = {k: v for k, v in state["daily"].items() if k >= keep_from}
    state["daily"][today] = daily
    queue = state.setdefault("queue", {"x": [], "threads": []})
    ok = True
    print(f"[{slug}] {now:%m/%d %H:%M} / セール: {event or 'なし'} / 今日の記事 {daily['articles']}本")

    # 1) 記事
    limit = cfg["event_mode"]["articles_per_day"] if event else cfg.get("articles_per_day", 1)
    if daily["articles"] < limit:
        client = None
        curated_list = None
        if not dry_run and not secrets.get("RAKUTEN_APP_ID"):
            curated_list = curated.load(root, slug, secrets.get("RAKUTEN_AFFILIATE_ID"), acct["genres"][0]["name"])
            if not curated_list:
                print(f"[{slug}] 楽天APIの鍵も売れ筋リストも無いので、記事は作りません")
                return True
            client = curated_list
        elif not dry_run:
            try:
                client = RakutenClient(secrets.get("RAKUTEN_APP_ID"), secrets.get("RAKUTEN_ACCESS_KEY"),
                                       secrets.get("RAKUTEN_AFFILIATE_ID"), site_root_url)
            except RakutenError as e:
                print(f"[{slug}] {e}")
                return False
        try:
            theme, candidates = fetch_candidates(acct, state, event, client, daily["articles"])
        except RakutenError as e:
            print(f"[{slug}] {e}")
            return False
        chosen = pick_products(candidates, set(posted), cfg["items_per_article"],
                               cfg["min_review_count"], 0 if curated_list else cfg["min_review_average"])
        if len(chosen) < 2:
            print(f"[{slug}] 「{theme}」で紹介できる新しい商品が足りないので、今回は記事を作りません")
        else:
            voice = acct["site"].get("voice", "")
            article = write_article(chosen, theme, event, voice)
            post_slug = now.strftime("%Y%m%d-%H%M")
            if any(p["slug"] == post_slug for p in posts):
                post_slug += f"-{len(posts)}"
            posts.append({"slug": post_slug, "date": now.isoformat(timespec="seconds"), "theme": theme, "event": event,
                          "article": article,
                          "products": [{**p.__dict__, "short_name": p.short_name} for p in chosen]})
            for p in chosen:
                posted[p.code] = slug
            daily["articles"] += 1
            url = f"{site_url}posts/{post_slug}.html"
            ch = acct["channels"]
            if ch["x"]["enabled"]:
                queue["x"] += write_social(article, chosen, url if ch["x"].get("include_link", True) else "",
                                           "x", 1, event, voice, acct["site"].get("angles", ""))
            if ch["threads"]["enabled"]:
                texts = write_social(article, chosen, url, "threads", 3, event, voice, acct["site"].get("angles", ""))
                queue["threads"] += [{"text": t, "image": chosen[i % len(chosen)].image} for i, t in enumerate(texts)]
            print(f"[{slug}] 記事: {article['title']} → {url}")
        sitegen.build(posts, acct["site"], site_url, out=out_dir)

    # 2) SNS（1回の実行で各1本まで）
    ch = acct["channels"]
    x_max = cfg["event_mode"]["x_max_posts_per_day"] if event else ch["x"]["max_posts_per_day"]
    th_max = cfg["event_mode"]["threads_max_posts_per_day"] if event else ch["threads"]["max_posts_per_day"]
    if queue["x"] and ch["x"]["enabled"] and daily["x"] < x_max:
        text = queue["x"].pop(0)
        try:
            creds = [secrets.get(k, slug) for k in ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")]
            print(f"[{slug}] X: {post_x(text, creds) if not dry_run else '(試運転)'}\n{text}")
            daily["x"] += 1
        except SocialError as e:
            print(f"[{slug}] {e}")
            queue["x"].insert(0, text)
            ok = False
    if queue["threads"] and ch["threads"]["enabled"] and daily["threads"] < th_max:
        item = queue["threads"].pop(0)
        try:
            token, user = secrets.get("THREADS_ACCESS_TOKEN", slug), secrets.get("THREADS_USER_ID", slug) or "me"
            print(f"[{slug}] Threads: {post_threads(item['text'], item.get('image'), token, user) if not dry_run else '(試運転)'}\n{item['text']}")
            daily["threads"] += 1
        except SocialError as e:
            print(f"[{slug}] {e}")
            queue["threads"].insert(0, item)
            ok = False
    queue["x"], queue["threads"] = queue["x"][-10:], queue["threads"][-20:]

    save_json(data_dir / "state.json", state)
    sitegen.save_posts(posts, data_dir / "posts.json")
    return ok


def run(dry_run: bool = False, run_all: bool = False, only: str | None = None) -> int:
    root = ROOT
    cfg = load_json(root / "config.json", {})
    accounts = [a for a in load_accounts(root) if a.get("enabled", True) and (not only or a["slug"] == only)]
    secrets = Secrets()
    site_root_url = (secrets.get("SITE_URL") or "https://unstandardofficial.github.io/kaimono-notes/").rstrip("/") + "/"
    now = datetime.now(JST)
    data_root = root / ("preview_data" if dry_run else "data")
    posted = load_json(data_root / "posted_codes.json", {})  # 商品コード → 紹介したブランド（全ブランド共通）

    if not dry_run and not secrets.get("RAKUTEN_APP_ID"):
        if not (secrets.get("RAKUTEN_AFFILIATE_ID") and (root / "data" / "curated").exists()):
            print("[main] 楽天の鍵がまだ入っていないので、今回は何もしません（設定待ち）")
            return 0
        print("[main] 楽天APIの代わりに、確認済みの売れ筋リストで動きます")
    due = [a for a in accounts if run_all or only or now.hour in a.get("run_hours", [])]
    if not due:
        print(f"[main] {now:%H}時に動くアカウントはありません")
    failures = 0
    for acct in due:
        try:
            if not run_account(acct, cfg, now, secrets, posted, root, dry_run, site_root_url):
                failures += 1
        except Exception as e:  # 1つのブランドの失敗で他を止めない
            print(f"[{acct['slug']}] 想定外のエラー: {e!r}")
            failures += 1
        save_json(data_root / "posted_codes.json", posted)

    sitegen.build_root(load_accounts(root), site_root_url, out=root / ("preview" if dry_run else "docs"))
    return 1 if failures and failures == len(due) else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="サンプルデータで preview/ に出力（外部には接続しない）")
    ap.add_argument("--all", action="store_true", help="時刻に関係なく全アカウントを処理する")
    ap.add_argument("--account", help="このスラッグのアカウントだけ処理する")
    a = ap.parse_args()
    sys.exit(run(a.dry_run, a.all, a.account))
