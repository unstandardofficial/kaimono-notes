"""Threadsでの交流（返信・引用）を、下書き→人の承認→投稿の順で回す。

draft: 毎朝、各ブランドの「自分の投稿へのコメント」と「テーマで伸びている他の人の投稿」を集め、
       AIで返信・引用の下書きを作り、GitHubのIssueにチェックリストで並べる。
post : 毎時、Issueでチェックが付いた下書きだけを、1ブランド1回2件・1日8件までThreadsに出す。
いいねはAPIに無いので扱わない。知らない人へ自動で送ることはしない（必ず人のチェックを通す）。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from bot import social, writer
from bot.main import Secrets, load_accounts

JST = timezone(timedelta(hours=9))
STATE = Path("data/engage/state.json")
API = "https://graph.threads.net/v1.0"
GH = "https://api.github.com"
LABEL = "engage"
PER_RUN, PER_DAY = 2, 8
MARK = re.compile(r"^- \[([ xX])\] .*?\[d:([0-9a-f]{8})\]", re.M)


def load_state(path: Path = STATE) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"seen": [], "drafts": {}, "posted": {}}


def save_state(state: dict, path: Path = STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["seen"] = state["seen"][-3000:]
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def checked_ids(body: str) -> list[str]:
    return [d for mark, d in MARK.findall(body or "") if mark in "xX"]


# ---------- Threads ----------
def _get(path: str, token: str, **params) -> list[dict]:
    r = requests.get(f"{API}/{path}", params={"access_token": token, **params}, timeout=30)
    if r.status_code >= 400:
        print(f"  取得失敗 {path}: {r.status_code} {r.text[:200]}")
        return []
    return r.json().get("data", [])


def own_replies(token: str, me: str) -> list[dict]:
    out = []
    for post in _get("me/threads", token, fields="id,text", limit=10):
        for rep in _get(f"{post['id']}/replies", token, fields="id,text,username,timestamp"):
            if rep.get("username") and rep["username"] != me:
                out.append({**rep, "kind": "reply", "context": post.get("text", "")[:120]})
    return out


def search_posts(token: str, keyword: str, exclude: set[str]) -> list[dict]:
    items = _get("keyword_search", token, q=keyword, search_type="TOP",
                 fields="id,text,username,permalink,timestamp,is_reply")
    return [{**p, "kind": "comment"} for p in items
            if not p.get("is_reply") and p.get("username") not in exclude and len(p.get("text") or "") >= 30]


# ---------- 下書き ----------
RULES = ("・150文字以内、です・ます調の丁寧な口調\n・リンク、商品名、宣伝、【PR】は入れない\n"
         "・自分の体験談や「使ってみた」は書かない（ブランドの中の人は実体験を名乗らない）\n"
         "・効果効能を断定しない\n・相手の内容に具体的に触れ、役立つ一言（比べ方・選び方の観点）を1つ添える\n"
         "・相手を否定しない。絵文字は0〜1個")


def draft_text(acct: dict, item: dict) -> str | None:
    site = acct["site"]
    if item["kind"] == "reply":
        task = (f"自分の投稿「{item['context']}」に、@{item['username']} さんから次のコメントが来た。"
                f"お礼と、相手の内容に沿った短い返信を書いて。\nコメント：{item['text']}")
    else:
        task = (f"@{item['username']} さんの次の投稿に、共感と役立つ観点を添えたコメントを書いて。\n投稿：{item['text'][:400]}")
    prompt = (f"あなたはThreadsアカウント「{site['title']}」の中の人。口調：{site.get('voice', '')}\n"
              f"{task}\n\nルール：\n{RULES}\n\n返信の本文だけを出力。")
    text = writer._ai(prompt, max_tokens=400)
    return text.strip().strip("「」") if text else None


def gh(method: str, path: str, **kw):
    token, repo = os.environ.get("GITHUB_TOKEN"), os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        raise RuntimeError("GITHUB_TOKEN / GITHUB_REPOSITORY がありません")
    r = requests.request(method, f"{GH}/repos/{repo}{path}", timeout=30,
                         headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, **kw)
    r.raise_for_status()
    return r.json() if r.text else {}


def run_draft(now: datetime | None = None) -> int:
    now = now or datetime.now(JST)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ANTHROPIC_API_KEY が無いので、交流の下書きは作りません")
        return 0
    secrets, state = Secrets(), load_state()
    accounts = [a for a in load_accounts(Path(".")) if a.get("enabled") and a["channels"]["threads"].get("enabled")]
    handles = {a["engage"]["handle"] for a in accounts if a.get("engage")}
    lines, made = [], 0
    for acct in accounts:
        cfg, slug = acct.get("engage"), acct["slug"]
        token = secrets.get("THREADS_ACCESS_TOKEN", slug)
        if not cfg or not token:
            continue
        cands = own_replies(token, cfg["handle"])
        for kw in cfg.get("keywords", []):
            cands += search_posts(token, kw, handles)
        picked, n_comment = [], 0
        for c in cands:
            if c["id"] in state["seen"]:
                continue
            if c["kind"] == "comment":
                if n_comment >= cfg.get("per_day", 5):
                    continue
                n_comment += 1
            state["seen"].append(c["id"])
            text = draft_text(acct, c)
            if not text:
                continue
            did = hashlib.sha1(f"{slug}:{c['id']}".encode()).hexdigest()[:8]
            state["drafts"][did] = {"slug": slug, "target": c["id"], "kind": c["kind"], "text": text[:300],
                                    "created": now.isoformat(timespec="minutes")}
            label = "コメントへの返信" if c["kind"] == "reply" else "コメント"
            src = (c.get("text") or "").replace("\n", " ")[:80]
            link = f" [元投稿]({c['permalink']})" if c.get("permalink") else ""
            picked.append(f"- [ ] **{label}** @{c['username']}「{src}」{link}\n  → {text} [d:{did}]")
            made += 1
        if picked:
            lines.append(f"### {acct['site']['title']}\n" + "\n".join(picked))
    save_state(state)
    if made:
        body = ("出してよいものにチェックを付けてください。チェックしたものだけが、毎時1ブランド2件までThreadsに投稿されます。"
                "文面を直したいときは、この本文の → の後ろを書き換えてからチェックしてください。\n\n" + "\n\n".join(lines))
        gh("POST", "/issues", json={"title": f"【承認】{now:%m/%d} 返信・コメントの下書き（{made}件）",
                                   "body": body, "labels": [LABEL]})
    print(f"下書き {made} 件")
    return made


def run_post(now: datetime | None = None) -> int:
    now = now or datetime.now(JST)
    secrets, state, posted = Secrets(), load_state(), 0
    today = now.strftime("%Y-%m-%d")
    issues = gh("GET", "/issues", params={"labels": LABEL, "state": "open", "per_page": 20})
    per_slug_run: dict[str, int] = {}
    for iss in issues:
        body, changed = iss.get("body") or "", False
        for did in checked_ids(body):
            d = state["drafts"].get(did)
            if not d or did in state["posted"]:
                continue
            slug = d["slug"]
            day_count = sum(1 for p in state["posted"].values() if p["slug"] == slug and p["at"].startswith(today))
            if per_slug_run.get(slug, 0) >= PER_RUN or day_count >= PER_DAY:
                continue
            m = re.search(r"→ (.*?) \[d:" + did + r"\]", body)
            text = (m.group(1).strip() if m else d["text"])[:500]
            extra = {"reply_to_id": d["target"]}
            try:
                pid = social.post_threads(text, None, secrets.get("THREADS_ACCESS_TOKEN", slug), extra=extra)
            except social.SocialError as e:
                print(f"[{slug}] 失敗: {e}")
                continue
            state["posted"][did] = {"slug": slug, "id": pid, "at": now.isoformat(timespec="minutes")}
            per_slug_run[slug] = per_slug_run.get(slug, 0) + 1
            body = body.replace(f"[d:{did}]", f"[d:{did}] ✅投稿済み")
            changed, posted = True, posted + 1
        remaining = [i for i in checked_ids(body) if i not in state["posted"]]
        old = datetime.fromisoformat(iss["created_at"].replace("Z", "+00:00")) < now - timedelta(days=2)
        patch = {}
        if changed:
            patch["body"] = body
        if old and not remaining:
            patch["state"] = "closed"
        if patch:
            gh("PATCH", f"/issues/{iss['number']}", json=patch)
    save_state(state)
    print(f"投稿 {posted} 件")
    return posted


if __name__ == "__main__":
    {"draft": run_draft, "post": run_post}[sys.argv[1] if len(sys.argv) > 1 else "post"]()
