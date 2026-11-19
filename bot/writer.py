"""記事とSNS投稿の文章を作る。

ANTHROPIC_API_KEY があれば Claude で書き、なければテンプレートで書く。
どちらでも「使ってみた」などの嘘の体験談や、効果効能の断定（薬機法）は書かない。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import random
import re

import requests

from .rakuten import Product

MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-5-5")

RULES = """守ること:
- 自分で使った・試したという体験談は書かない（実際には使っていないため）。「レビューでは〜という声が多い」のように、レビュー件数・評価・商品説明から言えることだけを書く
- 健康・美容の商品で「治る」「痩せる」「効く」など効果効能を断定しない（薬機法・景品表示法）
- 「最安」「絶対」「必ず」などの断定、価格がずっと続くような表現は使わない
- 煽りすぎず、読んだ人の暮らしの困りごとから入る
- ハッシュタグは使わないか、使っても1つまで
- 複数の商品を比べるときは、どれも否定しない。「〇〇重視ならA、△△重視ならB」と、良い面どうしで比べる。勝ち負け・「イマイチ」などは書かない
- 実在しない人物や家族構成を名乗らない。中の人の体験は、商品データに「実際に使っている」とある場合だけ書いてよい"""


# 調べた「伸びている投稿の型」（スプレッドシート「SNS×ジャンル別 伸びている投稿の型と改善版」）
THREADS_STYLE = """Threads用。1本ごとに次の型を順番に1つずつ使い、同じ型を続けない:
 1) 読点切り: 短い行を改行で重ね、1行目で「あるある」の悩みを言い切る
 2) 対立: 「〇〇だけで選ぶと失敗しがち」と常識をひっくり返し、見るべき点を①②③で示す
 3) 保存されるメモ: 「〇〇な人へ」→買う前に確認したい点（□で3〜4個）→「保存しておくと次の買い物で迷いません」
 4) 質問: 「AとB、どっち派ですか？」のように答えやすい二択で締める
1行目で手を止めさせ、2段落目でレビュー件数・平均評価・価格・送料などの数字を出す。
1本は「1投稿目」と「自分への返信」の2つに分ける:
 - main（1投稿目）: リンクも商品名の連呼もしない。驚き・あるある・気持ちから入る2〜5行。最後は問いかけか、続きは返信へ、で終える
 - reply（返信）: 価格・レビュー件数などの数字を1〜2行、選び方のひとことで締める。URLとPRは自分で書かない（後から付ける）"""
X_STYLE = """X用。1文目に「〇〇は△△で選ぶと失敗しにくい」のような選び方の結論、2文目に「楽天の売れ筋3つを□□で比べました」。
数字（寸法・容量・枚数・価格のどれか）を1つ入れる。URLは自分で書かない（後から付ける）"""


def style_notes() -> str:
    """data/style_notes.md（伸びた投稿の研究から出た、守るとよい型）を読み込む。共有された良い投稿をここに反映する。"""
    f = Path(__file__).resolve().parent.parent / "data" / "style_notes.md"
    try:
        t = f.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return ("\n伸びた投稿の研究から（できるだけ取り入れる）:\n" + t) if t else ""


def _yen(n: int) -> str:
    return f"{n:,}円"


def _ai(prompt: str, max_tokens: int = 2500) -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": MODEL, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]},
            timeout=90,
        )
        r.raise_for_status()
        return "".join(b.get("text", "") for b in r.json().get("content", []))
    except Exception as e:  # AIが落ちてもテンプレートで続ける
        print(f"[writer] AIでの作成に失敗したのでテンプレートを使います: {e}")
        return None


def _extract_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _product_brief(i: int, p: Product) -> str:
    rating = (f"平均{p.review_average:.2f}・" if p.review_average else "") + f"{p.review_count:,}件"
    as_of = p.extra.get("as_of") if p.extra else None
    note = (f"    注意: 価格・レビュー数は{as_of}時点。価格に触れるときは「{as_of}時点」と添える。平均評価は不明なので書かない\n"
            if as_of else "")
    return (f"[{i}] 商品名: {p.name}\n    価格: {_yen(p.price)} / 送料無料: {'はい' if p.postage_free else 'いいえ'}"
            f" / ショップ: {p.shop}\n    レビュー: {rating}"
            f" / ランキング: {p.rank or '-'}位（{p.genre_name}）\n    キャッチコピー: {p.catchcopy}\n"
            + note + f"    商品説明（抜粋）: {p.caption[:300]}")


def write_article(products: list[Product], theme: str, event: str | None, voice: str = "") -> dict:
    """戻り値: {title, intro, items:[{heading, point, who_for}], summary}"""
    briefs = "\n".join(_product_brief(i + 1, p) for i, p in enumerate(products))
    event_line = f"今は「{event}」の時期なので、買いまわりやまとめ買いの視点も少し入れる。" if event else ""
    prompt = f"""あなたは商品紹介ブログの編集者です。楽天市場の売れ筋から選んだ{len(products)}つの商品を紹介する記事を書きます。
テーマ: {theme}
このブログの読者と口調: {voice or '日用品を探している人に向けて、丁寧で分かりやすい口調'}
{event_line}
{RULES}

商品:
{briefs}

次のJSONだけを出力してください。
{{"title": "32文字以内。具体的な悩みや場面が分かる記事タイトル",
 "intro": "120〜200文字の導入",
 "items": [{{"heading": "その商品の特徴が分かる20文字前後の見出し", "point": "150〜250文字。どんな点が支持されているか", "who_for": "こんな人に向いている（40文字以内）"}}],
 "summary": "80〜150文字のまとめ。選び方のヒントで締める"}}"""
    data = _extract_json(_ai(prompt) or "")
    if data and len(data.get("items", [])) == len(products):
        return data
    return _template_article(products, theme, event)


def _template_article(products: list[Product], theme: str, event: str | None) -> dict:
    lead = random.choice([
        "毎日使うものほど、ちょっとした使いやすさの差が気になりますよね。",
        "「なんとなく」で選びがちなものほど、評判のいいものに替えるだけで暮らしが楽になることがあります。",
        "どれを買えばいいか迷ったときは、たくさんの人に選ばれている商品から見るのが近道です。",
    ])
    ev = f"{event}の期間は、買いまわりでポイントが上がるのでまとめ買いにも向いています。" if event else ""
    items = []
    for p in products:
        stars = f"レビュー{p.review_count:,}件" + (f"・平均{p.review_average:.1f}" if p.review_average else "")
        free = "送料無料で、" if p.postage_free else ""
        items.append({
            "heading": p.short_name[:24],
            "point": (f"{p.genre_name}ランキングで{p.rank}位に入っている商品です。" if p.rank else "")
                     + (f"{stars}と評価が安定していて、" if p.review_average else f"{stars}が集まっていて、") + f"{free}{_yen(p.price)}で買えます" + (f"（{p.extra.get('as_of')}時点の価格）" if p.extra.get("as_of") else "") + "。"
                     + (f"ショップの説明では「{p.catchcopy[:60]}」とされています。" if p.catchcopy and not p.extra.get("as_of") else ""),
            "who_for": "評判を見てから選びたい人に",
        })
    return {
        "title": f"楽天で売れている{theme} {len(products)}選｜レビューが多い定番から",
        "intro": lead + f"この記事では、楽天市場の{theme}の売れ筋から、レビュー件数と評価が高いものを{len(products)}つ選びました。" + ev,
        "items": items,
        "summary": "迷ったら、レビュー件数が多くて評価も高いものから選ぶと失敗しにくいです。価格は変わることがあるので、購入前にショップのページで確認してください。",
    }


def write_social(article: dict, products: list[Product], url: str, platform: str,
                 n: int, event: str | None, voice: str = "", angles: str = "") -> list:
    """SNS投稿文を n 本作る。
    X: 文字列のリスト（先頭に【PR】、末尾にURL）。
    Threads: {"text": 1投稿目（末尾に【PR】・リンクなし）, "reply": 返信（数字＋URL＋PR）} のリスト。"""
    threads = platform != "x"
    limit = 130 if not threads else 450
    briefs = "\n".join(_product_brief(i + 1, p) for i, p in enumerate(products))
    style = (THREADS_STYLE + style_notes() if threads else X_STYLE) + (f"\nこのブランドで効く切り口: {angles}" if angles else "")
    shape = ('{"posts": [{"main": "...", "reply": "..."}, ...]}' if threads else '{"posts": ["...", "..."]}')
    prompt = f"""ブログ記事「{article['title']}」を紹介するSNS投稿を{n}本、それぞれ別の切り口で書いてください。
{style}
アカウントの読者と口調: {voice or '日用品を探している人に向けた、親しみやすい口調'}
{('今は' + event + 'の時期。') if event else ''}
{RULES}
- 1本あたり{(200 if threads else limit - 10)}文字以内。先頭の【PR】は自分で書かない（後から付ける）
商品:
{briefs}
JSONで {shape} だけを出力してください。"""
    data = _extract_json(_ai(prompt, 1500) or "")
    raw = (data or {}).get("posts", [])
    if not threads:
        posts = [s.strip() for s in raw if isinstance(s, str) and s.strip()]
        if len(posts) < n:
            posts += _template_social(products, n - len(posts), event)
        out = []
        for body in posts[:n]:
            room = limit - len("【PR】\n") - (24 if url else 0)
            out.append(f"【PR】{body[:room]}" + (f"\n{url}" if url else ""))
        return out
    pairs = []
    for it in raw:
        if isinstance(it, dict) and str(it.get("main", "")).strip() and str(it.get("reply", "")).strip():
            pairs.append((it["main"].strip(), it["reply"].strip()))
        elif isinstance(it, str) and it.strip():
            pairs.append((it.strip(), "詳しい比較はこちら"))
    for body in _template_social(products, max(0, n - len(pairs)), event):
        pairs.append(("これ、気になってた人いませんか？", body))
    out = []
    for main, reply in pairs[:n]:
        tail = (f"\n{url}" if url else "") + "\nPR"
        out.append({"text": f"{main[:400]}\n【PR】", "reply": reply[:480 - len(tail)] + tail})
    return out


def _template_social(products: list[Product], n: int, event: str | None) -> list[str]:
    outs = []
    for p in random.sample(products, k=min(n, len(products))):
        hook = random.choice(["地味に助かる定番", "買い替えるならこれ", "レビューが多くて安心な一品"])
        ev = f"{event}のまとめ買いにも。" if event else ""
        outs.append(f"{hook}。{p.short_name[:30]}は{p.review_count:,}件のレビュー{('で平均' + format(p.review_average, '.1f')) if p.review_average else ''}。{_yen(p.price)}{'・送料無料' if p.postage_free else ''}。{ev}")
    while len(outs) < n:
        outs.append(outs[-1] if outs else "楽天の売れ筋からまとめました。")
    return outs
