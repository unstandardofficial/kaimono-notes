"""楽天APIが使えない間の代わり：人が確認した売れ筋リスト（data/curated/<slug>.json）から商品を出す。

アフィリエイトURLは、楽天ウェブサービスのAPIが返すものと同じ形式
（https://hb.afl.rakuten.co.jp/hgc/<アフィリエイトID>/?pc=<商品URL>&m=<商品URL>）で作る。
"""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from bot.rakuten import Product


def affiliate_url(item_url: str, affiliate_id: str) -> str:
    u = quote(item_url, safe="")
    return f"https://hb.afl.rakuten.co.jp/hgc/{affiliate_id}/?pc={u}&m={u}"


def load(root: Path, slug: str, affiliate_id: str, theme: str = "楽天の売れ筋") -> tuple[str, list[Product]] | None:
    p = root / "data" / "curated" / f"{slug}.json"
    if not p.exists() or not affiliate_id:
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for it in d.get("items", []):
        code = it["item_url"].replace("https://item.rakuten.co.jp/", "").strip("/").replace("/", ":")
        out.append(Product(code=code, name=it["name"], price=int(it["price"]), url=affiliate_url(it["item_url"], affiliate_id),
                           image=it.get("image", ""), shop=it.get("shop", ""), review_average=float(it.get("review_average") or 0),
                           review_count=int(it.get("review_count") or 0), rank=it.get("rank"),
                           catchcopy=f"価格・レビュー数は{d.get('as_of', '')}時点", extra={"as_of": d.get("as_of", "")}))
    return theme, out
