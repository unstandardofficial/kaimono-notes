"""X と Threads への投稿。

X API は従量課金。2026年4月以降、URL付きの投稿は1件0.20ドル（URLなしは0.015ドル）。
Threads API は無料（24時間で250投稿まで、ハッシュタグは1つまで、500文字まで）。
"""
from __future__ import annotations

import time

import requests


class SocialError(RuntimeError):
    pass


def post_x(text: str, keys: list[str]) -> str:
    """keys = [API Key, API Secret, Access Token, Access Token Secret]"""
    from requests_oauthlib import OAuth1

    if len(keys) != 4 or not all(keys):
        raise SocialError("Xの鍵（X_API_KEY など4つ）が設定されていません")
    auth = OAuth1(*keys)
    last = None
    for host in ("https://api.x.com", "https://api.twitter.com"):
        r = requests.post(f"{host}/2/tweets", json={"text": text}, auth=auth, timeout=30)
        if r.status_code in (200, 201):
            return r.json()["data"]["id"]
        last = r
        if r.status_code not in (404, 421):  # 接続先違い以外のエラーはそのまま報告
            break
    if last is not None and last.status_code == 402:
        raise SocialError("Xのクレジットが足りません。開発者コンソールでクレジットを追加してください")
    raise SocialError(f"Xへの投稿に失敗: {last.status_code if last is not None else '-'} {last.text[:300] if last is not None else ''}")


def post_threads(text: str, image_url: str | None, token: str, user: str = "me") -> str:
    if not token:
        raise SocialError("THREADS_ACCESS_TOKEN が設定されていません")
    base = f"https://graph.threads.net/v1.0/{user}"
    params = {"text": text[:500], "access_token": token, "media_type": "TEXT"}
    if image_url:
        params.update(media_type="IMAGE", image_url=image_url)
    r = requests.post(f"{base}/threads", params=params, timeout=30)
    if r.status_code >= 400 and image_url:  # 画像で失敗したら文字だけで再挑戦
        params.update(media_type="TEXT")
        params.pop("image_url", None)
        r = requests.post(f"{base}/threads", params=params, timeout=30)
    if r.status_code >= 400:
        raise SocialError(f"Threadsの下書き作成に失敗: {r.status_code} {r.text[:300]}")
    creation_id = r.json()["id"]
    time.sleep(5 if image_url else 2)  # 公式の推奨どおり少し待ってから公開
    r = requests.post(f"{base}/threads_publish", params={"creation_id": creation_id, "access_token": token}, timeout=30)
    if r.status_code >= 400:
        raise SocialError(f"Threadsの公開に失敗: {r.status_code} {r.text[:300]}")
    return r.json()["id"]
# 注意: Threadsの長期トークンは60日で切れる。公開リポジトリのログは誰でも見られるので、
# 新しいトークンをログに出す自動更新はしない。50日目にカレンダーの予定で手動更新する。
