"""下書きの品質を上げて、検索の設計図と追加記事を作る（python -m bot.refine <slug>）。

1) guides.json の各記事を上位モデルで点検→書き直し        → guides_refined.json
2) threads.json を10本ずつ点検→書き直し                    → threads_refined.json
3) 検索キーワードの設計図（約100語・優先度つき）           → keywords.json
4) 設計図の上位から、既存と重ならない記事を10本追加＋点検  → guides_extra.json
途中で止まっても、できた分から再開する。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from bot.bulk import BIG, EXTRA, ai, ai_json, brand_brief
from bot.main import load_accounts
from bot.writer import RULES

CHECK = """点検する観点：
1. 事実の誤り・あいまいな数字（不確かなら「目安」「商品ページで確認」に直す）
2. 規約・法律：体験談の捏造、効果効能の断定（薬機法・景品表示法）、最安・絶対などの断定、セール日程の予告
3. 読みやすさ：一文を短く、結論を先に、スマホで読みやすい段落
4. 検索：狙う検索語をタイトル・冒頭・見出しに自然に入れる。読者の検索意図に最後まで答える"""


def load(p: Path, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(p: Path, data) -> None:
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def refine_article(brief: str, title: str, keyword: str, md: str) -> dict:
    out = ai(BIG, f"{brief}\n\nあなたは編集長。次の記事を点検し、改善版を書く。\n{CHECK}\n\n{RULES}\n{EXTRA}\n\n"
                  f"狙う検索語：{keyword}\n記事タイトル：{title}\n\n--- 記事 ---\n{md}\n--- ここまで ---\n\n"
                  "出力形式：1行目に「REVIEW: 主な指摘（直した点）を1〜3文」、2行目以降に改善版の記事Markdown全文（# タイトルから）。"
                  "【商品枠】の位置は残す。", 9000)
    m = re.match(r"\s*REVIEW:\s*(.*?)\n(.*)", out, re.S)
    review, body = (m.group(1).strip(), m.group(2).strip()) if m else ("", out.strip())
    t = re.match(r"#\s+(.+)", body)
    return {"title": t.group(1).strip() if t else title, "keyword": keyword, "review": review, "markdown": body}


def run(slug: str) -> None:
    acct = next(a for a in load_accounts(Path(".")) if a["slug"] == slug)
    brief, d = brand_brief(acct), Path(f"data/bulk/{slug}")

    # 1) 記事の点検
    src, done = load(d / "guides.json", []), load(d / "guides_refined.json", [])
    for g in src[len(done):]:
        done.append(refine_article(brief, g["title"], g.get("keyword", g["title"]), g["markdown"]))
        save(d / "guides_refined.json", done); print(f"[{slug}] 記事 {len(done)}/{len(src)}")

    # 2) Threadsの点検（10本ずつ）
    posts, tdone = load(d / "threads.json", []), load(d / "threads_refined.json", [])
    while len(tdone) < len(posts):
        chunk = posts[len(tdone):len(tdone) + 10]
        got = ai_json(BIG, f"{brief}\n\nあなたは編集長。次のThreads投稿{len(chunk)}本を1本ずつ点検し、改善版にする。\n{CHECK}\n"
                      "Threadsでは1行目で手を止めさせること、150〜300字、改行多め、リンク・宣伝なし。"
                      f"同じ順番・同じ本数で返す。\n\n{RULES}\n{EXTRA}\n\n投稿：{json.dumps(chunk, ensure_ascii=False)}\n\n"
                      '形式：[{"title":"見出し","body":"本文","review":"直した点を1文"}]', 8000)
        if not got or len(got) != len(chunk):
            got = [{**p, "review": "（点検に失敗したため原文のまま）"} for p in chunk]
        tdone += [g for g in got if isinstance(g, dict)]
        save(d / "threads_refined.json", tdone); print(f"[{slug}] Threads {len(tdone)}/{len(posts)}")

    # 3) 検索キーワードの設計図
    kws = load(d / "keywords.json", [])
    for part in range(2):
        if len(kws) >= 90:
            break
        got = ai_json(BIG, f"{brief}\n\nこのブランドのブログで狙う検索キーワードを50個。日本の楽天・Googleで実際に検索されそうな語に限る。"
                      f"既に出したもの（重複禁止）：{[k['keyword'] for k in kws]}\n"
                      "各語に、どんな人が・何に困って検索するか、検索意図（知りたい／比べたい／買いたい）、"
                      "優先度（1=すぐ書く 2=次に書く 3=あとで）、記事タイトル案を付ける。"
                      "優先度1は、購入に近く、かつ個人ブログでも上位を狙える語。"
                      '形式：[{"keyword":"","who":"","problem":"","intent":"","priority":1,"article_title":""}]', 9000) or []
        kws += [k for k in got if isinstance(k, dict) and k.get("keyword")]
        save(d / "keywords.json", kws); print(f"[{slug}] キーワード {len(kws)}")

    # 4) 追加記事（設計図の上位・既存と重ならないもの）
    extra = load(d / "guides_extra.json", [])
    have = " ".join(g["title"] + g.get("keyword", "") for g in src + extra)
    cands = sorted((k for k in kws if k["keyword"] not in have), key=lambda k: int(k.get("priority", 3) or 3))
    for k in cands:
        if len(extra) >= 10:
            break
        draft = ai(BIG, f"{brief}\n\n記事タイトル：{k['article_title']}\n狙う検索語：{k['keyword']}\n読者：{k.get('who','')}／困りごと：{k.get('problem','')}\n\n"
                        "この記事を日本語のMarkdownで書く。構成：導入（読者の困りごと）→結論（選ぶ観点3〜5個）→観点ごとの解説→"
                        "比較表（観点×タイプ別、商品名なし）→【商品枠】を3つ置く場所→よくある質問3つ→まとめ。2500〜3500字。"
                        f"見出しは##と###。\n\n{RULES}\n{EXTRA}", 8000)
        extra.append(refine_article(brief, k["article_title"], k["keyword"], draft))
        save(d / "guides_extra.json", extra); print(f"[{slug}] 追加記事 {len(extra)}/10")


if __name__ == "__main__":
    run(sys.argv[1])
