# バトロワ使用率

https://brawl.kdking-tools.com/

ブロスタのソロ・デュオバトルロワイヤル（ショーダウン）で、マップ・期間・トロフィー帯ごとによく使われているキャラ（デュオはキャラの組み合わせも）を集計して表示するサイト。日本語・英語・中国語（簡体字）・韓国語に対応（`?lang=en|zh|ko`、未指定ならブラウザの言語）。

- `collect.py`: 世界と14地域のランキング上位、その対戦相手の battlelog から直近7日のソロ・デュオショーダウン（トロフィー戦のみ）の試合を8並列で集め、`data/battles.jsonl.gz` に追記する。キャラIDを `data/brawlers.json`、対象試合の参加者名を `data/names.json` に保存
  - APIはトリオを `duoShowdown`、hunterSurvivor を `soloShowdown` として返すので、`event.mode`・`type=ranked`・人数（ソロ1人×10、デュオ2人×5）で判定する
- `build_data.py`: `data/battles.jsonl.gz` から直近7日分の `site/data.json` を作る。最新試合から7日（168時間）より古い試合と、その試合にしか登場しないプレイヤー名は更新時に自動削除する。使用数は (マップ, 日付, キャラ, 50刻みのトロフィー帯) ごとに集約。全参加者の辞書を同時に展開しないことで、集計時のメモリ使用量を抑える
- `i18n/map-names.json`: マップ名の日本語・中国語・韓国語（ゲームの翻訳ファイル `localization/*.csv` と `csv_logic/locations.csv` から作成。英語名がキー）
- `site/`: 公開するページ（GitHub Pages）。キャラ・マップ画像は Brawlify の CDN から読む（読めなければ頭文字で代用）。キャラトロフィー3000以上で絞ったときだけ、行を押すと使っていたアカウントを出す
- `data_storage.py`: Git保存用にJSONをgzip圧縮し、試合データを含む全ファイルを32 MiB以下に分割する。`data/archive/manifest.json` にサイズ・SHA-256を保存し、復元時に検証。旧形式は初回保存時に自動移行する。作業用の展開ファイルはGitに保存しない
- `.github/workflows/update.yml`: 15分間隔の起動設定で収集 → 集計 → 圧縮・分割・検証 → 保存 → Pages公開。GitHub側のスケジュール実行には遅延があるためCloudflareの起動も併用。試合データは履歴が増えないよう `data` ブランチに毎回1コミットで置き換え、同時更新はforce-with-leaseで保護する。保存・検証失敗時は直前の公開サイトを維持する

プレイヤー名は保存期間内の試合参加者だけを残す。保存前には圧縮・分割データを復元して元ファイルと一致することを検証するため、分割によって試合や順位が欠落しないことを確認できる。

## ランキングと表示設定

- 使用数・割合に加え、平均順位を表示する。ソロは `2.3/10`、デュオのキャラ別・組み合わせ別は `2.3/5` の形式。平均は、選択したマップ・期間・トロフィー帯の順位合計を使用数で割る。使用数順のランキングはそのまま。
- `data.json` の `rankSums` は既存の `solo`・`duo`・`pair` の各行に対応する順位合計。使用数の行形式は変更せず、順位情報のないデータは `—` を表示する。
- ヘッダーの「ブラック／ホワイト」で配色を選べる。選択をブラウザ内に保存し、再読み込みや運営者情報・プライバシーポリシーへの移動後も引き継ぐ。未選択時は端末の配色設定に従う。

## 集計対象の確認

収集時と集計時の両方で、通常の `soloShowdown` / `duoShowdown`、`type=ranked`、ソロ1人×10またはデュオ2人×5という条件を検証する。新しい記録には `eventMode` も残し、対戦モードとの一致を再確認する。旧形式では元の `event.mode` を保存していないため、保存済みのモード・種別・人数で判定する。

順位は従来の参加者・チーム配列の並び順を用いる。新しい記録では、取得元プレイヤーの `battle.rank` と、その本人またはチームの配列位置を照合する。照合できない試合は使用数に残し、関連する平均順位は `—` とする。この照合は全参加者の順位を個別に取得するものではなく、旧記録の並び順を遡って検証するものでもない。

回帰テストは `python3 -m unittest discover -s tests -v` と `node tests/test_rank_frontend.js` で実行する。

## 設定

- リポジトリの Settings → Secrets and variables → Actions に `BRAWL_API_KEY` を登録する（許可IPは RoyaleAPI プロキシの 45.79.218.79）
- Settings → Pages の Source を「GitHub Actions」にし、Custom domain に `brawl.kdking-tools.com` を入れる
- Cloudflare DNS に CNAME `brawl` → `kodaka-yutaro.github.io`

## 手元で動かす

```
git fetch origin data && git checkout FETCH_HEAD -- data/ && git reset -q data/   # これまでの試合データ
python3 data_storage.py restore
BRAWL_API_KEY=... python3 collect.py --max-players 3000
python3 build_data.py
cd site && python3 -m http.server
```
