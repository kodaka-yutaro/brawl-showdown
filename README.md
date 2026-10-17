# ショーダウン使用率

https://brawl.kdking-tools.com/

ブロスタのソロ・デュオショーダウンで、トロフィー帯ごとによく使われているキャラ（デュオはキャラの組み合わせも）を集計して表示するサイト。

- `collect.py`: 公式APIのランキング上位とその対戦相手の battlelog からショーダウンの試合を集め、`data/battles.jsonl` に追記する
- `build_data.py`: `data/battles.jsonl` から `site/data.json` を作る
- `site/`: 公開するページ（GitHub Pages）
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
