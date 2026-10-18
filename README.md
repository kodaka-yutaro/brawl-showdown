# バトロワ使用率

https://brawl.kdking-tools.com/

ブロスタのソロ・デュオバトルロワイヤル（ショーダウン）で、マップ・期間・トロフィー帯ごとによく使われているキャラ（デュオはキャラの組み合わせも）を集計して表示するサイト。日本語・英語・中国語（簡体字）・韓国語に対応（`?lang=en|zh|ko`、未指定ならブラウザの言語）。

- `collect.py`: 世界と14地域のランキング上位、その対戦相手の battlelog から直近7日のソロ・デュオショーダウン（トロフィー戦のみ）の試合を8並列で集め、`data/battles.jsonl.gz` に追記する。キャラIDを `data/brawlers.json`、トロフィー2500以上のプレイヤー名を `data/names.json` に保存
  - APIはトリオを `duoShowdown`、hunterSurvivor を `soloShowdown` として返すので、`event.mode`・`type=ranked`・人数（ソロ1人×10、デュオ2人×5）で判定する
- `build_data.py`: `data/battles.jsonl.gz` から直近14日分の `site/data.json` を作る（14日より古い試合は削除）。試合が増えてもページが重くならないよう、使用数は (マップ, 日付, キャラ, 50刻みのトロフィー帯) ごとに数えて持つ。ページは既定で直近7日を表示し、期間を広げるとバランス調整前と比べられる
- `i18n/map-names.json`: マップ名の日本語・中国語・韓国語（ゲームの翻訳ファイル `localization/*.csv` と `csv_logic/locations.csv` から作成。英語名がキー）
- `site/`: 公開するページ（GitHub Pages）。キャラ・マップ画像は Brawlify の CDN から読む（読めなければ頭文字で代用）。キャラトロフィー3000以上で絞ったときだけ、行を押すと使っていたアカウントを出す
- `.github/workflows/update.yml`: 1時間ごとに収集 → 集計 → Pages へ公開。試合データは履歴が増えないよう `data` ブランチに毎回1コミットで置き換えて保存する

## 設定

- リポジトリの Settings → Secrets and variables → Actions に `BRAWL_API_KEY` を登録する（許可IPは RoyaleAPI プロキシの 45.79.218.79）
- Settings → Pages の Source を「GitHub Actions」にし、Custom domain に `brawl.kdking-tools.com` を入れる
- Cloudflare DNS に CNAME `brawl` → `kodaka-yutaro.github.io`

## 手元で動かす

```
git fetch origin data && git checkout FETCH_HEAD -- data/ && git reset -q data/   # これまでの試合データ
BRAWL_API_KEY=... python3 collect.py --max-players 3000
python3 build_data.py
cd site && python3 -m http.server
```
