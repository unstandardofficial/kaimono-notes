"""ブログ（静的サイト）を docs/ に書き出す。GitHub Pages がそのまま公開する。"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
POSTS_JSON = ROOT / "data" / "posts.json"

E = html.escape

CSS = """
:root{--ink:#222;--sub:#666;--line:#e6e2dc;--bg:#faf8f5;--accent:#bf0000;--card:#fff}
*{box-sizing:border-box}body{margin:0;font-family:-apple-system,"Hiragino Sans","Noto Sans JP",sans-serif;color:var(--ink);background:var(--bg);line-height:1.85}
a{color:inherit}header,main,footer{max-width:760px;margin:0 auto;padding:0 18px}
header{padding-top:22px;padding-bottom:6px}header a{text-decoration:none}.logo{font-weight:700;font-size:1.25rem}
.tag{color:var(--sub);font-size:.85rem;margin:2px 0 0}
.pr{background:#fff4e5;border:1px solid #f3d3a5;border-radius:8px;padding:8px 12px;font-size:.85rem;margin:16px 0}
h1{font-size:1.5rem;line-height:1.5;margin:18px 0 6px}.date{color:var(--sub);font-size:.85rem}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px;margin:22px 0}
.card h2{font-size:1.1rem;margin:0 0 10px}.prod{display:flex;gap:16px;align-items:flex-start}
.prod img{width:140px;height:140px;object-fit:contain;border-radius:10px;background:#fff;flex:none}
.meta{font-size:.85rem;color:var(--sub)}.price{font-weight:700;font-size:1.1rem}
.btn{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;padding:10px 18px;border-radius:999px;font-weight:700;margin-top:10px}
.who{background:var(--bg);border-radius:8px;padding:6px 10px;font-size:.9rem;margin-top:8px}
.list a{display:block;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:12px 0;text-decoration:none}
.list small{color:var(--sub)}footer{color:var(--sub);font-size:.8rem;padding:30px 18px 50px;border-top:1px solid var(--line);margin-top:40px}
@media(max-width:520px){.prod{flex-direction:column}.prod img{width:100%;height:220px}}
"""

PR_NOTE = ("※この記事はアフィリエイト広告（楽天アフィリエイト）を利用しています。"
           "リンクから購入されると運営者に紹介料が入ることがあります。価格・送料・在庫は記事作成時点のもので、変わることがあります。")


def _page(title: str, body: str, site: dict, base: str, desc: str = "", canonical: str = "") -> str:
    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title><meta name="description" content="{E(desc or site['description'])}">
{f'<link rel="canonical" href="{E(canonical)}">' if canonical else ''}
<link rel="alternate" type="application/rss+xml" href="{base}feed.xml">
<style>{CSS}</style></head><body>
<header><a href="{base}"><div class="logo">{E(site['title'])}</div></a><p class="tag">{E(site['description'])}</p></header>
<main>{body}</main>
<footer><p>{E(PR_NOTE)}</p>
<p><a href="{base}about.html">運営者情報・広告について</a></p>
<p><!-- Rakuten Web Services Attribution Snippet FROM HERE --><a href="https://developers.rakuten.com/" target="_blank" rel="noopener">Supported by Rakuten Developers</a><!-- Rakuten Web Services Attribution Snippet TO HERE --></p>
<p>© {datetime.now().year} {E(site['author'])}</p></footer></body></html>"""


def render_post(post: dict, site: dict, site_url: str) -> str:
    cards = []
    for it, p in zip(post["article"]["items"], post["products"]):
        cards.append(f"""<section class="card"><h2>{E(it['heading'])}</h2><div class="prod">
<img src="{E(p['image'])}" alt="{E(p['short_name'])}" loading="lazy">
<div><div class="meta">{E(p['shop'])}・レビュー{p['review_count']:,}件（平均{p['review_average']:.1f}）</div>
<div class="price">{p['price']:,}円{'（送料無料）' if p['postage_free'] else ''}</div>
<p>{E(it['point'])}</p><div class="who">{E(it['who_for'])}</div>
<a class="btn" href="{E(p['url'])}" target="_blank" rel="nofollow sponsored noopener">楽天市場で見る</a></div></div></section>""")
    body = f"""<p class="pr">{E(PR_NOTE)}</p><article><h1>{E(post['article']['title'])}</h1>
<div class="date">{post['date'][:10]} 作成</div><p>{E(post['article']['intro'])}</p>{''.join(cards)}
<h2>まとめ</h2><p>{E(post['article']['summary'])}</p></article>"""
    url = f"{site_url}posts/{post['slug']}.html"
    return _page(post["article"]["title"], body, site, "../", post["article"]["intro"][:110], url)


def render_index(posts: list[dict], site: dict) -> str:
    links = "".join(
        f'<a href="posts/{p["slug"]}.html"><b>{E(p["article"]["title"])}</b><br><small>{p["date"][:10]}・{E(p["theme"])}</small></a>'
        for p in posts)
    return _page(site["title"], f'<p class="pr">{E(PR_NOTE)}</p><div class="list">{links or "<p>記事を準備中です。</p>"}</div>', site, "./")


def render_about(site: dict) -> str:
    body = f"""<h1>運営者情報・広告について</h1>
<p>{E(site['title'])}は、楽天市場のランキングとレビューをもとに、日用品・キッチン用品・収納グッズなどを選んで紹介しているブログです。</p>
<h2>広告について</h2><p>当サイトは楽天アフィリエイトを利用しています。記事内のリンクから商品を購入されると、運営者に紹介料が支払われることがあります。紹介料の有無で商品の評価を変えることはありません。</p>
<h2>記事の作り方</h2><p>記事は、楽天ウェブサービスのランキング・商品情報（価格、レビュー件数、評価）をもとに作成しています。運営者が実際に使用したレビューではありません。価格や在庫は変わることがあるため、購入前に必ずショップのページでご確認ください。</p>
<h2>運営者</h2><p>{E(site['author'])}</p>"""
    return _page("運営者情報・広告について", body, site, "./")


def render_feed(posts: list[dict], site: dict, site_url: str) -> str:
    items = "".join(
        f"<item><title>{E(p['article']['title'])}</title><link>{site_url}posts/{p['slug']}.html</link>"
        f"<pubDate>{datetime.fromisoformat(p['date']).strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>"
        f"<description>{E(p['article']['intro'])}</description></item>" for p in posts[:30])
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{E(site["title"])}</title>'
            f"<link>{site_url}</link><description>{E(site['description'])}</description>{items}</channel></rss>")


def render_sitemap(posts: list[dict], site_url: str) -> str:
    urls = [site_url, f"{site_url}about.html"] + [f"{site_url}posts/{p['slug']}.html" for p in posts]
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>")


def load_posts(path: Path = POSTS_JSON) -> list[dict]:
    return json.loads(path.read_text("utf-8")) if path.exists() else []


def save_posts(posts: list[dict], path: Path = POSTS_JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(posts, ensure_ascii=False, indent=1), "utf-8")


def build(posts: list[dict], site: dict, site_url: str, out: Path = DOCS) -> None:
    site_url = site_url.rstrip("/") + "/"
    posts = sorted(posts, key=lambda p: p["date"], reverse=True)
    (out / "posts").mkdir(parents=True, exist_ok=True)
    for p in posts:
        (out / "posts" / f"{p['slug']}.html").write_text(render_post(p, site, site_url), "utf-8")
    (out / "index.html").write_text(render_index(posts, site), "utf-8")
    (out / "about.html").write_text(render_about(site), "utf-8")
    (out / "feed.xml").write_text(render_feed(posts, site, site_url), "utf-8")
    (out / "sitemap.xml").write_text(render_sitemap(posts, site_url), "utf-8")


def build_root(accounts: list[dict], root_url: str, out: Path = DOCS) -> None:
    """GitHub Pages のトップ。運営者と各ブログへのリンク、広告の表記だけを置く。"""
    out.mkdir(parents=True, exist_ok=True)
    links = "".join(
        f'<a href="{E(a["slug"])}/"><b>{E(a["site"]["title"])}</b><br><small>{E(a["site"]["description"])}</small></a>'
        for a in accounts if a.get("enabled", True))
    site = {"title": "運営者情報", "description": "楽天アフィリエイトを利用した商品紹介ブログを運営しています。", "author": "運営者"}
    body = f'<h1>運営しているブログ</h1><p class="pr">{E(PR_NOTE)}</p><div class="list">{links}</div>'
    (out / "index.html").write_text(_page("運営しているブログ", body, site, "./"), "utf-8")
    (out / "about.html").write_text(render_about(site), "utf-8")
    (out / ".nojekyll").write_text("", "utf-8")
    sitemaps = "".join(f"<sitemap><loc>{root_url}{a['slug']}/sitemap.xml</loc></sitemap>" for a in accounts if a.get("enabled", True))
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + sitemaps + "</sitemapindex>", "utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {root_url}sitemap.xml\n", "utf-8")
