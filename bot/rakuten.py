"""楽天ウェブサービス（2026年刷新後の新API）から商品を取ってくる。

新APIのポイント:
  - 接続先は openapi.rakuten.co.jp
  - applicationId と accessKey の両方が必要
  - Referer ヘッダーが必須。アプリ登録時に入れた「WebサイトURL」と同じにする
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import requests

RANKING_URL = "https://openapi.rakuten.co.jp/ichibaranking/api/IchibaItem/Ranking/20220601"
SEARCH_URL = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20220601"


class RakutenError(RuntimeError):
    pass


@dataclass
class Product:
    code: str
    name: str
    price: int
    url: str            # アフィリエイトURL（affiliateId を渡したとき）
    image: str
    shop: str
    review_average: float
    review_count: int
    catchcopy: str = ""
    caption: str = ""
    rank: int | None = None
    genre_name: str = ""
    postage_free: bool = False
    point_rate: int = 1
    extra: dict = field(default_factory=dict)

    @property
    def short_name(self) -> str:
        """楽天の商品名は長くて【】だらけなので、見出し用に短くする。"""
        import re
        name = re.sub(r"【[^】]*】|\[[^\]]*\]|＼[^／]*／|★[^★]*★", " ", self.name)
        name = re.sub(r"\s+", " ", name).strip()
        return (name[:38] + "…") if len(name) > 40 else name


def _first(value):
    if isinstance(value, list) and value:
        v = value[0]
        return v.get("imageUrl", v) if isinstance(v, dict) else v
    return value or ""


def parse_item(raw: dict, genre_name: str = "") -> Product:
    item = raw.get("Item", raw)  # formatVersion=1 と 2 の両方に対応
    image = _first(item.get("mediumImageUrls")) or _first(item.get("smallImageUrls"))
    if isinstance(image, str):
        image = image.split("?")[0] + "?_ex=400x400"
    return Product(
        code=str(item.get("itemCode", "")),
        name=item.get("itemName", ""),
        price=int(item.get("itemPrice", 0) or 0),
        url=item.get("affiliateUrl") or item.get("itemUrl", ""),
        image=image or "",
        shop=item.get("shopName", ""),
        review_average=float(item.get("reviewAverage", 0) or 0),
        review_count=int(item.get("reviewCount", 0) or 0),
        catchcopy=item.get("catchcopy", "") or "",
        caption=(item.get("itemCaption", "") or "")[:600],
        rank=int(item["rank"]) if item.get("rank") else None,
        genre_name=genre_name,
        postage_free=str(item.get("postageFlag", "1")) == "0",
        point_rate=int(item.get("pointRate", 1) or 1),
    )


class RakutenClient:
    def __init__(self, app_id: str, access_key: str, affiliate_id: str, referer: str,
                 session: requests.Session | None = None):
        if not (app_id and access_key and affiliate_id and referer):
            raise RakutenError("楽天の鍵（アプリID・アクセスキー・アフィリエイトID・サイトURL）が足りません")
        self.params = {
            "applicationId": app_id,
            "accessKey": access_key,
            "affiliateId": affiliate_id,
            "format": "json",
            "formatVersion": 2,
        }
        self.headers = {"Referer": referer, "Origin": referer.rstrip("/")}
        self.s = session or requests.Session()

    def _get(self, url: str, params: dict) -> dict:
        for attempt in range(4):
            r = self.s.get(url, params={**self.params, **params}, headers=self.headers, timeout=20)
            if r.status_code == 429:  # 叩きすぎ。少し待つ
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 403:
                raise RakutenError(
                    "楽天APIが403を返しました。アプリ登録の『WebサイトURL』とSITE_URLが一致しているか、"
                    f"アクセスキーが正しいか確認してください。応答: {r.text[:300]}")
            if r.status_code >= 400:
                raise RakutenError(f"楽天APIエラー {r.status_code}: {r.text[:300]}")
            time.sleep(1.1)  # 1秒1回程度に抑える
            return r.json()
        raise RakutenError("楽天APIが混んでいて応答しません（429が続きました）")

    def ranking(self, genre_id: int, genre_name: str = "", page: int = 1) -> list[Product]:
        data = self._get(RANKING_URL, {"genreId": genre_id, "page": page})
        return [parse_item(i, genre_name) for i in data.get("Items", [])]

    def search(self, keyword: str, sort: str = "-reviewCount", hits: int = 30,
               postage_free_only: bool = True) -> list[Product]:
        params = {"keyword": keyword, "sort": sort, "hits": hits, "availability": 1}
        if postage_free_only:
            params["postageFlag"] = 1
        data = self._get(SEARCH_URL, params)
        return [parse_item(i, "まとめ買い") for i in data.get("Items", [])]


def pick_products(products: list[Product], posted_codes: set[str], n: int,
                  min_reviews: int, min_avg: float) -> list[Product]:
    """まだ紹介していない・レビューが十分ある商品を、ショップが偏らないように選ぶ。"""
    chosen, shops = [], set()
    for p in products:
        if not p.code or p.code in posted_codes or not p.url:
            continue
        if p.review_count < min_reviews or p.review_average < min_avg:
            continue
        if p.shop in shops:
            continue
        chosen.append(p)
        shops.add(p.shop)
        if len(chosen) >= n:
            break
    return chosen
