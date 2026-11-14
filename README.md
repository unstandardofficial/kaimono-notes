# 楽天アフィリエイト自動投稿（5ブランド）

1つのリポジトリで5つのブランド（ブログ＋Threads＋X）を回します。GitHub Actions が毎時起動し、各ブランドは自分の `run_hours` の回だけ動きます。

| スラッグ | ブランド | ジャンル | 動く時刻（日本時間） |
|---|---|---|---|
| kurashi | くらしの買い物メモ | 日用品雑貨 | 7・12・20時 |
| kitchen | 台所と収納のちいさな工夫 | キッチン用品／インテリア・収納 | 8・13・18時 |
| kosodate | 子育て買いものノート | キッズ・ベビー・マタニティ | 9・14・21時 |
| otoriyose | お取り寄せとまとめ買い帖 | 食品／水・ソフトドリンク | 11・17・22時 |
| gadget | 家電とガジェットの選びかた | 家電／TV・オーディオ・カメラ | 10・19・23時 |

## 重ならない仕組み
- 一度紹介した商品は、どのブランドでも二度と紹介しない（`data/posted_codes.json`）
- ジャンル・読者・口調（`accounts/*.json` の `voice`）・投稿時刻をブランドごとに分けている
- 楽天アフィリエイトは同じSNSで複数アカウントから同じ・似た内容を投稿することを禁止しているため

## 設定（Settings → Secrets and variables → Actions）
| 種類 | 名前 | 中身 |
|---|---|---|
| Variables | `SITE_URL` | `https://<ユーザー名>.github.io/<リポジトリ名>/`（楽天アプリ登録のWebサイトURLと同じ） |
| Secrets | `RAKUTEN_APP_ID` `RAKUTEN_ACCESS_KEY` `RAKUTEN_AFFILIATE_ID` | 全ブランド共通 |
| Secrets（任意） | `ANTHROPIC_API_KEY` | 文章をAIで書くとき（全ブランド共通） |
| Secrets | `THREADS_ACCESS_TOKEN_<スラッグ大文字>` `THREADS_USER_ID_<スラッグ大文字>` | 例 `THREADS_ACCESS_TOKEN_KITCHEN`。ブランドごと |
| Secrets | `X_API_KEY` `X_API_SECRET`（共通）＋ `X_ACCESS_TOKEN_<スラッグ大文字>` `X_ACCESS_TOKEN_SECRET_<スラッグ大文字>` | Xを使うブランドだけ |

鍵を入れたら、そのブランドの `accounts/<スラッグ>.json` で `channels.threads.enabled`（や `x.enabled`）を `true` にします。

## 動かし方
- 手動：Actions → auto-post → Run workflow（アカウント欄を空にすると全ブランド、`kitchen` などで1つだけ）
- 試運転：`python -m bot.main --dry-run --all`（外部につながず `preview/` に出力）
- テスト：`python -m pytest -q`
