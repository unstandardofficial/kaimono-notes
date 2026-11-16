import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from bot import main, site
from bot.rakuten import parse_item, pick_products
from bot.writer import write_article, write_social

HERE = Path(__file__).parent
REPO = HERE.parent
FIX = json.loads((HERE / "fixtures" / "ranking_sample.json").read_text("utf-8"))


@pytest.fixture(autouse=True)
def no_ai(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def products():
    return [parse_item(i, "日用品雑貨") for i in FIX["Items"]]


def test_parse_uses_affiliate_url_and_bigger_image():
    p = products()[0]
    assert p.url.startswith("https://hb.afl.rakuten.co.jp/")
    assert p.image.endswith("?_ex=400x400")
    assert p.postage_free is True
    assert "【" not in p.short_name


def test_pick_skips_posted_low_reviews_and_same_shop():
    ps = products()
    chosen = pick_products(ps, {ps[0].code}, 3, 30, 4.0)
    codes = [c.code for c in chosen]
    assert ps[0].code not in codes and ps[5].code not in codes
    assert len({c.shop for c in chosen}) == len(chosen) == 3


def test_event_window_includes_warmup():
    cfg = {"events": [{"name": "BF", "start": "2026-11-19T20:00:00+09:00",
                       "end": "2026-11-25T01:59:00+09:00", "warmup_days": 3}]}
    assert main.current_event(cfg, datetime.fromisoformat("2026-11-17T09:00:00+09:00")) == "BF"
    assert main.current_event(cfg, datetime.fromisoformat("2026-11-15T09:00:00+09:00")) is None
    assert main.current_event(cfg, datetime.fromisoformat("2026-11-25T03:00:00+09:00")) is None


def test_template_article_and_social_have_pr_and_fit():
    ps = products()[:3]
    art = write_article(ps, "日用品雑貨", None)
    assert len(art["items"]) == 3 and art["title"]
    url = "https://example.github.io/x/kurashi/posts/1.html"
    for t in write_social(art, ps, url, "x", 1, None):
        assert t.startswith("【PR】") and t.endswith(url) and len(t) <= 130
    th = write_social(art, ps, url, "threads", 3, "楽天ブラックフライデー")
    assert len(th) == 3 and all(t.startswith("【PR】") and len(t) <= 500 for t in th)


def test_post_page_has_disclosure_credit_and_sponsored_links(tmp_path):
    ps = products()[:3]
    art = write_article(ps, "日用品雑貨", None)
    post = {"slug": "s1", "date": "2026-11-14T07:30:00+09:00", "theme": "日用品雑貨", "event": None,
            "article": art, "products": [{**p.__dict__, "short_name": p.short_name} for p in ps]}
    site.build([post], {"title": "T", "description": "D", "author": "A"}, "https://e.com/b/kurashi", out=tmp_path)
    page = (tmp_path / "posts" / "s1.html").read_text("utf-8")
    assert "アフィリエイト広告" in page and "Supported by Rakuten Developers" in page
    assert 'rel="nofollow sponsored noopener"' in page
    assert "https://e.com/b/kurashi/posts/s1.html" in (tmp_path / "sitemap.xml").read_text("utf-8")


def test_accounts_are_distinct():
    accts = main.load_accounts(REPO)
    assert len(accts) == 5
    titles = [a["site"]["title"] for a in accts]
    genres = [g["id"] for a in accts for g in a["genres"]]
    hours = [h for a in accts for h in a["run_hours"]]
    assert len(set(titles)) == len(titles)
    assert len(set(genres)) == len(genres), "ジャンルが重複している"
    assert len(set(hours)) == len(hours), "投稿時刻が重なっている"


def test_secret_lookup_prefers_account_specific(monkeypatch):
    monkeypatch.setenv("SECRETS_JSON", json.dumps({"THREADS_ACCESS_TOKEN_KITCHEN": "k", "THREADS_ACCESS_TOKEN": "common"}))
    s = main.Secrets()
    assert s.get("THREADS_ACCESS_TOKEN", "kitchen") == "k"
    assert s.get("THREADS_ACCESS_TOKEN", "kurashi") == "common"


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    shutil.copy(REPO / "config.json", tmp_path / "config.json")
    shutil.copytree(REPO / "accounts", tmp_path / "accounts")
    for p in (tmp_path / "accounts").glob("*.json"):
        a = json.loads(p.read_text("utf-8"))
        a["channels"]["threads"]["enabled"] = True
        a["channels"]["x"]["enabled"] = True
        p.write_text(json.dumps(a, ensure_ascii=False), "utf-8")
    monkeypatch.setattr(main, "ROOT", tmp_path)
    return tmp_path


def test_all_accounts_never_share_a_product(sandbox):
    assert main.run(dry_run=True, run_all=True) == 0
    posted = json.loads((sandbox / "preview_data" / "posted_codes.json").read_text("utf-8"))
    # サンプルは条件を満たす商品が5つだけ: 1ブランド目が3つ、2ブランド目が2つ使い、残りは記事を作らない
    by_brand = {}
    for code, slug in posted.items():
        by_brand.setdefault(slug, []).append(code)
    assert sum(len(v) for v in by_brand.values()) == len(posted) == 5
    all_codes = []
    for slug in by_brand:
        posts = json.loads((sandbox / "preview_data" / slug / "posts.json").read_text("utf-8"))
        all_codes += [pr["code"] for p in posts for pr in p["products"]]
    assert len(all_codes) == len(set(all_codes))
    assert (sandbox / "preview" / "index.html").exists()
    for slug in by_brand:
        assert (sandbox / "preview" / slug / "index.html").exists()
        st = json.loads((sandbox / "preview_data" / slug / "state.json").read_text("utf-8"))
        day = next(iter(st["daily"].values()))
        assert day["threads"] == 1 and day["x"] == 1


def test_only_due_accounts_run(sandbox, monkeypatch):
    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 14, 8, 5, tzinfo=tz)
    monkeypatch.setattr(main, "datetime", Fixed)
    main.run(dry_run=True)
    dirs = [p.name for p in (sandbox / "preview_data").iterdir() if p.is_dir()]
    assert dirs == ["kitchen"]  # 8時は kitchen だけ


def test_curated_products(tmp_path):
    import json
    from bot import curated
    (tmp_path / "data" / "curated").mkdir(parents=True)
    (tmp_path / "data" / "curated" / "x.json").write_text(json.dumps({"as_of": "2026-11-16", "items": [
        {"rank": 4, "name": "テスト洗剤", "item_url": "https://item.rakuten.co.jp/shop/123/", "price": 990, "review_count": 50, "shop": "店"}]}), encoding="utf-8")
    theme, items = curated.load(tmp_path, "x", "aaa.bbb")
    assert items[0].code == "shop:123" and items[0].url.startswith("https://hb.afl.rakuten.co.jp/hgc/aaa.bbb/?pc=https%3A%2F%2Fitem")
    assert items[0].review_average == 0
