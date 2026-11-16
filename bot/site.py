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

THEMES = {  # ブランドごとの差し色（落ち着いた色だけを少し使う）
    "kurashi": {"accent": "#6f6253", "soft": "#ece6dd"},
    "kitchen": {"accent": "#3f4f3e", "soft": "#e7e8e0"},
    "kosodate": {"accent": "#8a6656", "soft": "#efe5de"},
    "otoriyose": {"accent": "#6e4a3c", "soft": "#ede3dc"},
    "gadget": {"accent": "#4a4f57", "soft": "#e6e6e4"},
}
DEFAULT_THEME = {"accent": "#5a554e", "soft": "#ebe7e0"}

FONTS = ('<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
         '<link href="https://fonts.googleapis.com/css2?family=Shippori+Mincho:wght@400;500&family=Noto+Sans+JP:wght@300;400;500&display=swap" rel="stylesheet">')

CSS = """
:root{--ink:#2f2b26;--sub:#8a847b;--line:#e4dfd7;--bg:#f8f6f2;--paper:#fdfcfa}
*{box-sizing:border-box}body{margin:0;font-family:"Noto Sans JP",-apple-system,"Hiragino Sans",sans-serif;font-weight:300;color:var(--ink);background:var(--bg);line-height:2;font-size:14px;letter-spacing:.03em}
a{color:inherit;text-decoration:none}img{max-width:100%;display:block}
.serif,h1,h2,h3,.logo,.no{font-family:"Shippori Mincho","Hiragino Mincho ProN","Yu Mincho",serif;font-weight:400}
.wrap{max-width:1080px;margin:0 auto;padding:0 28px}
header.top{border-bottom:1px solid var(--line);background:var(--paper)}header.top .wrap{display:flex;justify-content:space-between;align-items:center;height:64px}
.logo{font-size:1.05rem;letter-spacing:.12em}nav a{font-size:.72rem;letter-spacing:.18em;margin-left:28px;color:var(--sub)}nav a:hover{color:var(--ink)}
.hero{background:linear-gradient(100deg,var(--paper) 0%,var(--soft) 100%);border-bottom:1px solid var(--line)}
.hero .wrap{padding-top:110px;padding-bottom:110px}
.hero h1{font-size:2.6rem;line-height:1.45;letter-spacing:.12em;margin:0}.hero .rule{width:36px;height:1px;background:var(--ink);margin:26px 0}
.hero p{margin:0 0 34px;color:var(--sub);max-width:460px}
.outline{display:inline-block;border:1px solid var(--ink);border-radius:999px;padding:9px 30px;font-size:.72rem;letter-spacing:.18em}
.outline:hover{background:var(--ink);color:var(--paper)}
.lead{text-align:center;margin:90px 0 40px}.lead h2{font-size:1.15rem;letter-spacing:.2em;margin:0}.lead p{color:var(--sub);margin:6px 0 0;font-size:.8rem}
.rows{max-width:880px;margin:0 auto}
.row{display:grid;grid-template-columns:1fr 1fr;align-items:center;gap:0;margin:0 0 18px}
.row .pic{aspect-ratio:16/10;background:var(--soft);display:flex;align-items:center;justify-content:center;overflow:hidden}
.row .pic img{width:100%;height:100%;object-fit:cover}.row .txt{padding:0 48px}
.row.rev .pic{order:2}.no{font-size:2.4rem;line-height:1;color:var(--ink)}
.row h3{font-size:1rem;letter-spacing:.12em;margin:16px 0 10px;line-height:1.7}.row p{color:var(--sub);font-size:.82rem;margin:0}
.ph{font-family:"Shippori Mincho",serif;color:var(--sub);font-size:.9rem;padding:0 18%;text-align:center;line-height:1.8}
.strip{display:grid;grid-template-columns:repeat(5,1fr);border-top:1px solid var(--line);border-left:1px solid var(--line);background:var(--paper)}
.strip a{border-right:1px solid var(--line);border-bottom:1px solid var(--line);padding:26px 18px 22px;text-align:center}
.strip .sq{aspect-ratio:1/1;display:flex;align-items:center;justify-content:center;margin-bottom:16px;overflow:hidden}
.strip .sq img{width:100%;height:100%;object-fit:contain}.strip .sq .ph{padding:0 6%;font-size:.82rem}
.strip .nm{font-size:.74rem;letter-spacing:.08em;line-height:1.7;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.strip .pr2{font-size:.74rem;color:var(--sub);margin-top:4px}.strip a:hover .nm{text-decoration:underline}
.more{text-align:center;margin:34px 0 0}
.band{background:var(--accent);color:#f4f0ea;margin-top:100px}.band .wrap{padding-top:80px;padding-bottom:80px}
.band h2{font-size:1.6rem;letter-spacing:.14em;line-height:1.6;margin:0 0 12px}.band p{margin:0 0 28px;opacity:.8;font-size:.82rem}
.band .outline{border-color:#f4f0ea}.band .outline:hover{background:#f4f0ea;color:var(--accent)}
.pr{font-size:.7rem;color:var(--sub);text-align:center;margin:26px auto 0;max-width:720px}
article{max-width:760px;margin:0 auto}article h1{font-size:1.6rem;letter-spacing:.08em;line-height:1.7;margin:70px 0 4px;text-align:center}
.date{color:var(--sub);font-size:.75rem;text-align:center;letter-spacing:.15em}.intro{margin:34px 0 50px;color:var(--ink)}
article h2{font-size:1.05rem;letter-spacing:.12em;margin:50px 0 10px}
.item{display:grid;grid-template-columns:240px 1fr;gap:40px;align-items:start;padding:40px 0;border-top:1px solid var(--line)}
.item .sq{aspect-ratio:1/1;background:var(--soft);display:flex;align-items:center;justify-content:center;overflow:hidden}.item .sq img{width:100%;height:100%;object-fit:contain;background:#fff}
.item h3{font-size:1.05rem;letter-spacing:.06em;line-height:1.7;margin:6px 0 6px}.meta{font-size:.74rem;color:var(--sub)}
.cost{font-family:"Shippori Mincho",serif;font-size:1.1rem;margin:8px 0 14px}.who{font-size:.8rem;color:var(--sub);border-left:1px solid var(--ink);padding-left:12px;margin:14px 0 20px}
.howto{counter-reset:s;list-style:none;padding:0;margin:8px 0 18px}.howto li{counter-increment:s;padding-left:34px;position:relative;margin:6px 0;font-size:.86rem}
.howto li::before{content:counter(s,decimal-leading-zero);position:absolute;left:0;font-family:"Shippori Mincho",serif;color:var(--sub)}
.buy{display:inline-block;background:var(--ink);color:var(--paper);border-radius:999px;padding:10px 32px;font-size:.74rem;letter-spacing:.16em}
.list a{display:block;border-top:1px solid var(--line);padding:22px 4px}.list a:last-child{border-bottom:1px solid var(--line)}.list small{color:var(--sub)}
footer.bottom{border-top:1px solid var(--line);margin-top:100px;background:var(--paper)}footer.bottom .wrap{display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap;padding-top:26px;padding-bottom:26px}
footer.bottom a,footer.bottom span{font-size:.68rem;letter-spacing:.16em;color:var(--sub);margin-right:24px}
footer.bottom .note{font-size:.66rem;color:var(--sub);max-width:520px;margin:0;line-height:1.8}
@media(max-width:820px){.strip{grid-template-columns:repeat(2,1fr)}.row{grid-template-columns:1fr}.row.rev .pic{order:0}.row .txt{padding:26px 6px 40px}
.hero .wrap{padding-top:70px;padding-bottom:70px}.hero h1{font-size:1.8rem}nav a{margin-left:14px;letter-spacing:.08em}.item{grid-template-columns:1fr;gap:20px}.item .sq{max-width:260px}}
"""

PR_NOTE = ("※このサイトはアフィリエイト広告（楽天アフィリエイト）を利用しています。"
           "リンクから購入されると運営者に紹介料が入ることがあります。価格・送料・在庫は記載した日付の時点のもので、変わることがあります。")


def _theme_css(theme: dict | None) -> str:
    t = theme or DEFAULT_THEME
    return f":root{{--accent:{t['accent']};--soft:{t['soft']}}}"


def _brand(site: dict) -> str:
    return site["title"].split("｜")[0]


def _page(title: str, body: str, site: dict, base: str, desc: str = "", canonical: str = "", theme: dict | None = None) -> str:
    threads = site.get("threads", "")
    return f"""<!DOCTYPE html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title><meta name="description" content="{E(desc or site['description'])}">
{f'<link rel="canonical" href="{E(canonical)}">' if canonical else ''}
<link rel="alternate" type="application/rss+xml" href="{base}feed.xml">{FONTS}
<style>{CSS}{_theme_css(theme)}</style></head><body>
<header class="top"><div class="wrap"><a class="logo" href="{base}">{E(_brand(site))}</a>
<nav><a href="{base}products.html">商品一覧</a><a href="{base}#journal">記事</a><a href="{base}about.html">運営者情報</a></nav></div></header>
<main>{body}</main>
<footer class="bottom"><div class="wrap"><div><a href="{base}products.html">商品一覧</a><a href="{base}about.html">運営者情報・広告について</a>
{f'<a href="https://www.threads.net/@{E(threads)}" target="_blank" rel="noopener">Threads</a>' if threads else ''}
<!-- Rakuten Web Services Attribution Snippet FROM HERE --><a href="https://developers.rakuten.com/" target="_blank" rel="noopener">Supported by Rakuten Developers</a><!-- Rakuten Web Services Attribution Snippet TO HERE -->
<span>© {datetime.now().year} {E(site['author'])}</span></div><p class="note">{E(PR_NOTE)}</p></div></footer></body></html>"""


def _pic(p: dict) -> str:
    if p.get("image"):
        return f'<img src="{E(p["image"])}" alt="{E(p.get("short_name") or p["name"])}" loading="lazy">'
    return f'<span class="ph">{E((p.get("short_name") or p["name"])[:22])}</span>'


def _price(p: dict) -> str:
    as_of = (p.get("extra") or {}).get("as_of") or p.get("as_of", "")
    return f'{p["price"]:,}円' + (f'（{as_of[5:].replace("-", "/")}時点）' if as_of else "")


def product_slug(code: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in code)


def _strip(items: list[dict], base: str = "") -> str:
    return '<div class="strip">' + "".join(
        f'<a href="{base}products/{product_slug(p["code"])}.html"><div class="sq"{"" if p.get("image") else ' style="background:var(--soft)"'}>{_pic(p) if p.get("image") else ""}</div>'
        f'<div class="nm">{E(p["short_name"])}</div><div class="pr2">{_price(p)}</div></a>' for p in items) + "</div>"


def render_post(post: dict, site: dict, site_url: str, theme: dict | None = None) -> str:
    items = []
    for i, (it, p) in enumerate(zip(post["article"]["items"], post["products"]), 1):
        howto = "".join(f"<li>{E(h)}</li>" for h in it.get("howto", []))
        items.append(f"""<section class="item"><div class="sq">{_pic(p)}</div><div><div class="no">{i:02d}</div><h3>{E(it['heading'])}</h3>
<div class="meta">{E(p.get('shop', ''))}　レビュー{p['review_count']:,}件{('（平均' + format(p['review_average'], '.1f') + '）') if p.get('review_average') else ''}</div>
<div class="cost">{_price(p)}</div><p>{E(it['point'])}</p>{f'<ol class="howto">{howto}</ol>' if howto else ''}
<div class="who">{E(it['who_for'])}</div><a class="buy" href="{E(p['url'])}" target="_blank" rel="nofollow sponsored noopener">楽天市場で見る</a></div></section>""")
    body = f"""<div class="wrap"><article><h1>{E(post['article']['title'])}</h1><div class="date">{post['date'][:10].replace('-', '.')}</div>
<p class="pr">{E(PR_NOTE)}</p><p class="intro">{E(post['article']['intro'])}</p>{''.join(items)}
<h2>まとめ</h2><p>{E(post['article']['summary'])}</p><p class="more"><a class="outline" href="../products.html">ほかの商品を見る</a></p></article></div>"""
    url = f"{site_url}posts/{post['slug']}.html"
    return _page(post["article"]["title"], body, site, "../", post["article"]["intro"][:110], url, theme)


def render_index(posts: list[dict], site: dict, catalog: list[dict] | None = None, theme: dict | None = None) -> str:
    catalog = catalog or []
    rows = "".join(
        f'<a class="row{" rev" if i % 2 else ""}" href="posts/{p["slug"]}.html"><div class="pic">{_pic(p["products"][0]) if p.get("products") else ""}</div>'
        f'<div class="txt"><div class="no">{i + 1:02d}</div><h3>{E(p["article"]["title"])}</h3><p>{E(p["article"]["intro"][:70])}…</p></div></a>'
        for i, p in enumerate(posts[:3]))
    threads = site.get("threads", "")
    body = f"""<section class="hero"><div class="wrap"><h1>{E(_brand(site))}</h1><div class="rule"></div><p>{E(site['description'])}</p>
<a class="outline" href="products.html">商品一覧を見る</a></div></section>
<div class="wrap"><div class="lead" id="journal"><h2>記事</h2><p>楽天の売れ筋を、比べるポイントと一緒に</p></div>
<div class="rows">{rows or '<p class="pr">記事を準備中です。</p>'}</div>
<div class="lead"><h2>いま売れているもの</h2><p>価格は確認した日付の時点です</p></div>{_strip(catalog[:5]) if catalog else '<p class="pr">商品を準備中です。</p>'}
<p class="more"><a class="outline" href="products.html">すべての商品を見る</a></p><p class="pr">{E(PR_NOTE)}</p></div>
{f'<section class="band"><div class="wrap"><h2>新しい紹介は<br>Threadsで</h2><p>セールの始まりや、売れ筋の入れ替わりをお知らせしています。</p><a class="outline" href="https://www.threads.net/@{E(threads)}" target="_blank" rel="noopener">@{E(threads)}</a></div></section>' if threads else ''}"""
    return _page(site["title"], body, site, "./", theme=theme)


def render_products(catalog: list[dict], site: dict, theme: dict | None = None) -> str:
    body = f"""<div class="wrap"><div class="lead"><h2>商品一覧</h2><p>楽天市場の売れ筋から、このブログで紹介している商品です</p></div>
{_strip(catalog) if catalog else '<p class="pr">商品を準備中です。</p>'}<p class="pr">{E(PR_NOTE)}</p></div>"""
    return _page(f"商品一覧｜{_brand(site)}", body, site, "./", theme=theme)


def render_product(p: dict, site: dict, site_url: str, theme: dict | None = None) -> str:
    howto = "".join(f"<li>{E(h)}</li>" for h in p.get("howto", []))
    body = f"""<div class="wrap"><article><section class="item" style="border:0;margin-top:50px"><div class="sq">{_pic(p)}</div><div>
<h3 style="font-size:1.25rem">{E(p['short_name'])}</h3>
<div class="meta">{E(p.get('shop', ''))}　レビュー{p['review_count']:,}件{('　ランキング' + str(p['rank']) + '位') if p.get('rank') else ''}</div>
<div class="cost">{_price(p)}</div>{f'<p>{E(p["note"])}</p>' if p.get('note') else ''}{f'<p>{E(p["point"])}</p>' if p.get('point') else ''}
{f'<h2>使い方</h2><ol class="howto">{howto}</ol>' if howto else ''}{f'<div class="who">{E(p["who_for"])}</div>' if p.get('who_for') else ''}
<a class="buy" href="{E(p['url'])}" target="_blank" rel="nofollow sponsored noopener">楽天市場で見る</a></div></section>
<p class="meta">商品名：{E(p['name'])}</p><p class="more"><a class="outline" href="../products.html">商品一覧にもどる</a></p><p class="pr">{E(PR_NOTE)}</p></article></div>"""
    return _page(f"{p['short_name']}｜{_brand(site)}", body, site, "../",
                 (p.get("note") or p["name"])[:110], f"{site_url}products/{product_slug(p['code'])}.html", theme)


def render_about(site: dict, theme: dict | None = None) -> str:
    body = f"""<div class="wrap"><article><h1>運営者情報・広告について</h1>
<p>{E(site['title'])}は、楽天市場のランキングとレビューをもとに商品を選んで紹介しているブログです。</p>
<h2>広告について</h2><p>当サイトは楽天アフィリエイトを利用しています。記事内のリンクから商品を購入されると、運営者に紹介料が支払われることがあります。紹介料の有無で商品の評価を変えることはありません。</p>
<h2>記事の作り方</h2><p>記事は、楽天市場のランキング・商品ページの情報（価格、レビュー件数など）をもとに作成しています。運営者が実際に使った商品は、そのことを明記しています。それ以外は使用レビューではありません。価格や在庫は変わることがあるため、購入前に必ずショップのページでご確認ください。</p>
<h2>運営者</h2><p>{E(site['author'])}</p></article></div>"""
    return _page("運営者情報・広告について", body, site, "./", theme=theme)


def render_feed(posts: list[dict], site: dict, site_url: str) -> str:
    items = "".join(
        f"<item><title>{E(p['article']['title'])}</title><link>{site_url}posts/{p['slug']}.html</link>"
        f"<pubDate>{datetime.fromisoformat(p['date']).strftime('%a, %d %b %Y %H:%M:%S %z')}</pubDate>"
        f"<description>{E(p['article']['intro'])}</description></item>" for p in posts[:30])
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{E(site["title"])}</title>'
            f"<link>{site_url}</link><description>{E(site['description'])}</description>{items}</channel></rss>")


def render_sitemap(posts: list[dict], site_url: str, catalog: list[dict] | None = None) -> str:
    urls = ([site_url, f"{site_url}about.html", f"{site_url}products.html"] + [f"{site_url}posts/{p['slug']}.html" for p in posts]
            + [f"{site_url}products/{product_slug(c['code'])}.html" for c in (catalog or [])])
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>")


def load_posts(path: Path = POSTS_JSON) -> list[dict]:
    return json.loads(path.read_text("utf-8")) if path.exists() else []


def save_posts(posts: list[dict], path: Path = POSTS_JSON) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(posts, ensure_ascii=False, indent=1), "utf-8")


def make_catalog(items: list[dict], posts: list[dict]) -> list[dict]:
    """売れ筋リストの商品に、記事で書いた紹介文（おすすめポイント・こんな人に・使い方）を足す。除外した商品は載せない。"""
    written = {}
    for post in posts:
        for it, p in zip(post["article"]["items"], post["products"]):
            written.setdefault(p["code"], {"point": it.get("point", ""), "who_for": it.get("who_for", ""), "howto": it.get("howto", [])})
    out = []
    for c in items:
        if c.get("status") == "除外":
            continue
        w = written.get(c["code"], {})
        out.append({**c, "point": c.get("point") or w.get("point", ""), "who_for": c.get("who_for") or w.get("who_for", ""),
                    "howto": c.get("howto") or w.get("howto", [])})
    return out


def build(posts: list[dict], site: dict, site_url: str, out: Path = DOCS, catalog: list[dict] | None = None,
          theme: dict | None = None) -> None:
    site_url = site_url.rstrip("/") + "/"
    posts = sorted(posts, key=lambda p: p["date"], reverse=True)
    catalog = make_catalog(catalog or [], posts)
    (out / "posts").mkdir(parents=True, exist_ok=True)
    (out / "products").mkdir(parents=True, exist_ok=True)
    for p in posts:
        (out / "posts" / f"{p['slug']}.html").write_text(render_post(p, site, site_url, theme), "utf-8")
    for c in catalog:
        (out / "products" / f"{product_slug(c['code'])}.html").write_text(render_product(c, site, site_url, theme), "utf-8")
    (out / "index.html").write_text(render_index(posts, site, catalog, theme), "utf-8")
    (out / "products.html").write_text(render_products(catalog, site, theme), "utf-8")
    (out / "about.html").write_text(render_about(site, theme), "utf-8")
    (out / "feed.xml").write_text(render_feed(posts, site, site_url), "utf-8")
    (out / "sitemap.xml").write_text(render_sitemap(posts, site_url, catalog), "utf-8")


def build_root(accounts: list[dict], root_url: str, out: Path = DOCS) -> None:
    """GitHub Pages のトップ。運営者と各ブログへのリンク、広告の表記だけを置く。"""
    out.mkdir(parents=True, exist_ok=True)
    links = "".join(
        f'<a href="{E(a["slug"])}/"><b>{E(a["site"]["title"])}</b><br><small>{E(a["site"]["description"])}</small></a>'
        for a in accounts if a.get("enabled", True))
    site = {"title": "運営者情報", "description": "楽天アフィリエイトを利用した商品紹介ブログを運営しています。", "author": "運営者"}
    body = f'<div class="wrap"><article><h1>運営しているブログ</h1><p class="pr">{E(PR_NOTE)}</p><div class="list">{links}</div></article></div>'
    (out / "index.html").write_text(_page("運営しているブログ", body, site, "./"), "utf-8")
    (out / "about.html").write_text(render_about(site), "utf-8")
    (out / ".nojekyll").write_text("", "utf-8")
    sitemaps = "".join(f"<sitemap><loc>{root_url}{a['slug']}/sitemap.xml</loc></sitemap>" for a in accounts if a.get("enabled", True))
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + sitemaps + "</sitemapindex>", "utf-8")
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {root_url}sitemap.xml\n", "utf-8")
