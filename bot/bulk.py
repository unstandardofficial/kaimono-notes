"""プロモーションクレジットの期限（11/17朝）までに、後から使える下書きをまとめて作る。

python -m bot.bulk <slug>
  ① 選び方ガイド記事 10本（上位モデル） → data/bulk/<slug>/guides.json
  ② Threads役立ち投稿 40本               → data/bulk/<slug>/threads.json
  ③ セール用の投稿の型（BF・SS・初売り）  → data/bulk/<slug>/sale_templates.json
  ④ Instagramカルーセル台本 10本          → data/bulk/<slug>/carousels.json
どれも下書き。公開・投稿は人が確認してから。商品名・価格は書かず、後から楽天の商品を差し込む前提。
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

from bot.main import load_accounts
from bot.writer import RULES

BIG = os.environ.get("BULK_MODEL_BIG", "claude-opus-5-5")
MID = os.environ.get("BULK_MODEL_MID", "claude-sonnet-5-5")

EXTRA = """追加ルール:
- 特定の商品名・ブランド名・価格は書かない（後から楽天の売れ筋を差し込む）。差し込む場所は【商品枠】と書く
- ブランドの中の人は実体験を名乗らない。親・家族・使用者だと名乗らない
- 楽天のセールの日程や割引率を予告・断定しない。期間限定クーポンのURLは書かない
- 事実として不確かな数字は書かない。書くなら「目安」「商品ページで確認」と添える"""


def ai(model: str, prompt: str, max_tokens: int) -> str:
    key = os.environ["ANTHROPIC_API_KEY"]
    for attempt in range(4):
        try:
            r = requests.post("https://api.anthropic.com/v1/messages", timeout=300,
                              headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                              json={"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]})
            if r.status_code in (429, 500, 502, 503, 529):
                time.sleep(20 * (attempt + 1)); continue
            r.raise_for_status()
            return "".join(b.get("text", "") for b in r.json().get("content", []))
        except requests.RequestException as e:
            print(f"  retry: {e}"); time.sleep(20 * (attempt + 1))
    raise RuntimeError("AIの呼び出しに失敗しました")


def ai_json(model: str, prompt: str, max_tokens: int):
    for attempt in range(3):
        text = ai(model, prompt + "\n\n出力はJSONだけ。前後に説明や```を付けない。文字列の中の改行は\\nで書く。文字列の中で半角の\"は使わず、引用は「」を使う。", max_tokens)
        m = re.search(r"[\[{].*[\]}]", text, re.S)
        if not m:
            continue
        try:
            return json.loads(m.group(0), strict=False)
        except json.JSONDecodeError as e:
            print(f"  JSONの読み取りに失敗（{attempt + 1}回目）: {e}")
    return None


def brand_brief(a: dict) -> str:
    s = a["site"]
    return f"ブランド：{s['title']}\n扱うもの：{s['description']}\n口調：{s.get('voice','')}\n切り口：{s.get('angles','')}"


def run(slug: str) -> None:
    acct = next(a for a in load_accounts(Path(".")) if a["slug"] == slug)
    out = Path(f"data/bulk/{slug}"); out.mkdir(parents=True, exist_ok=True)
    brief = brand_brief(acct)

    def save(name, data):
        (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{slug}] {name} を保存")

    # ① 選び方ガイド
    if not (out / "guides.json").exists():
        topics = ai_json(MID, f"{brief}\n\nこのブランドのブログに置く「選び方ガイド」記事のテーマを10個。"
                         "検索されやすい悩み（例：〇〇 選び方、〇〇 おすすめ 比較、〇〇 失敗しない）から逆算する。"
                         '形式：[{"title":"記事タイトル（32字以内）","keyword":"狙う検索語"}]', 2000) or []
        guides = []
        for t in [x for x in topics if isinstance(x, dict) and x.get('title')][:10]:
            body = ai(BIG, f"{brief}\n\n記事タイトル：{t['title']}\n狙う検索語：{t.get('keyword', t.get('title', ''))}\n\n"
                      "この記事を日本語のMarkdownで書く。構成：導入（読者の困りごと）→結論（選ぶ観点3〜5個）→観点ごとの解説→"
                      "比較表（観点×タイプ別、商品名なし）→【商品枠】を3つ置く場所→よくある質問3つ→まとめ。2500〜3500字。"
                      f"見出しは##と###。\n\n{RULES}\n{EXTRA}", 8000)
            guides.append({**t, "markdown": body})
            save("guides.json", guides)
    # ② Threads 40本
    posts = json.loads((out / "threads.json").read_text(encoding="utf-8")) if (out / "threads.json").exists() else []
    posts = [p for p in (posts or []) if isinstance(p, dict)]
    if len(posts) < 40:
        for i in range(6):
            if len(posts) >= 40:
                break
            got = ai_json(MID, f"{brief}\n\nThreads用の、商品リンクなし・宣伝なしの役立ち投稿を10本。"
                          f"テーマが重ならないように（{i+1}回目／4回。前の回と別テーマ：{[p.get('title', '') for p in posts if isinstance(p, dict)]}）。"
                          "1本150〜300字。1行目で手を止めさせる見出し、本文は改行多め。季節（12〜1月の大掃除・帰省・年末年始・新生活準備）も混ぜる。"
                          f'形式：[{{"title":"見出し","body":"本文"}}]\n\n{RULES}\n{EXTRA}', 6000) or []
            posts += [p for p in got if isinstance(p, dict)]
        save("threads.json", posts)
    # ③ セールの型
    if not (out / "sale_templates.json").exists():
        tpl = ai_json(MID, f"{brief}\n\n楽天の大型セール中（ブラックフライデー、スーパーSALE、初売り）に出すThreads投稿の型を、"
                      "セールごとに5本ずつ。商品は【商品名】【価格】【レビュー件数】【平均評価】【1回あたり】のように差し込み枠で書く。"
                      "冒頭に【PR】。セールの日程・割引率は書かない（当日に事実を入れる）。"
                      f'形式：{{"blackfriday":["..."],"supersale":["..."],"hatsuuri":["..."]}}\n\n{RULES}\n{EXTRA}', 6000)
        save("sale_templates.json", tpl)
    # ④ カルーセル台本
    old = json.loads((out / "carousels.json").read_text(encoding="utf-8")) if (out / "carousels.json").exists() else None
    if not old:
        car = []
        for i in range(2):
            got = ai_json(MID, f"{brief}\n\nInstagramの保存されやすいカルーセル投稿（画像5〜7枚）の台本を5本。前と別テーマ：{[c.get('title') for c in car]}"
                      "1枚目は大きな見出し、2〜6枚目は1枚1ポイント（20〜40字）、最後は「保存して買う前に見返す」。キャプションも付ける。"
                      f'形式：[{{"title":"","slides":["1枚目","2枚目"],"caption":""}}]\n\n{RULES}\n{EXTRA}', 6000) or []
            car += [c for c in got if isinstance(c, dict)]
        save("carousels.json", car)


if __name__ == "__main__":
    run(sys.argv[1])
