# バトロワ使用率

https://brawl.kdking-tools.com/

ブロスタのソロ・デュオバトルロワイヤル（ショーダウン）で、マップ・期間・トロフィー帯ごとによく使われているキャラ（デュオはキャラの組み合わせも）を集計して表示するサイト。日本語・英語・中国語（簡体字）・韓国語に対応（`?lang=en|zh|ko`、未指定ならブラウザの言語）。

- `collect.py`: 公式APIのランキング上位とその対戦相手の battlelog から直近7日のショーダウンの試合を集め、`data/battles.jsonl` に追記する。キャラIDを `data/brawlers.json`、トロフィー2500以上のプレイヤー名を `data/names.json` に保存
- `build_data.py`: `data/battles.jsonl` から直近14日分の `site/data.json` を作る（14日より古い試合は battles.jsonl から削除）。ページは既定で直近7日を表示し、期間を広げるとバランス調整前と比べられる
- `site/`: 公開するページ（GitHub Pages）。キャラ・マップ画像は Brawlify の CDN から読む（読めなければ頭文字で代用）。キャラトロフィー3000以上で絞ったときだけ、行を押すと使っていたアカウントを出す
- `.github/workflows/update.yml`: 毎日 3:00 JST に収集 → 集計 → コミット → Pages へ公開

## 設定

- リポジトリの Settings → Secrets and variables → Actions に `BRAWL_API_KEY` を登録する（許可IPは RoyaleAPI プロキシの 45.79.218.79）
- Settings → Pages の Source を「GitHub Actions」にし、Custom domain に `brawl.kdking-tools.com` を入れる
- Cloudflare DNS に CNAME `brawl` → `kodaka-yutaro.github.io`

## 手元で動かす

```
BRAWL_API_KEY=... python3 collect.py --countries global,jp --max-players 400
python3 build_data.py
cd site && python3 -m http.server
```
