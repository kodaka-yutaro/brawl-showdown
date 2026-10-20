"""Brawl Stars 公式APIからショーダウン（ソロ/デュオ）の試合を集めて data/battles.jsonl に追記する。

使い方:
  BRAWL_API_KEY=... python3 collect.py [--countries global,jp,...] [--max-players 3000] [--workers 8] [--days 7]

直近 --days 日（既定7日）の試合だけを追記する。過去の実行で集めた試合は残るので、
繰り返し実行すればバランス調整の前後を比べられる。

APIキーは「APIを呼ぶ側のIP」でしか使えない。既定ではRoyaleAPIの公開プロキシ
(https://bsproxy.royaleapi.dev/v1) を経由するので、キー作成時にプロキシのIPを登録しておく。
自分のPCなど固定IPから直接呼ぶ場合は BRAWL_API_BASE=https://api.brawlstars.com/v1 を指定する。
"""
import argparse
import gzip
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_BASE = os.environ.get("BRAWL_API_BASE", "https://bsproxy.royaleapi.dev/v1")
SHOWDOWN_MODES = {"soloShowdown", "duoShowdown"}
# gzip で保存（毎日コミットするのでリポジトリを軽く保つ）
DATA = Path(__file__).parent / "data" / "battles.jsonl.gz"
# 名前を覚えておくプレイヤー（デュオの組み合わせはトロフィーに関係なくアカウントを出すので全員）
NAME_MIN_TROPHIES = 0


def get(path):
    req = urllib.request.Request(
        API_BASE + path,
        headers={"Authorization": "Bearer " + os.environ["BRAWL_API_KEY"], "Accept": "application/json"},
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429 or e.code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise SystemExit(f"API error {e.code} on {path}: {e.read()[:300]!r}")
    return None


def tag_path(tag):
    return urllib.parse.quote(tag if tag.startswith("#") else "#" + tag, safe="")


def valid_shape(mode, teams):
    """通常のトロフィー戦の形か。ソロは1人×10、デュオは2人×5。
    APIはトリオショーダウンを battle.mode=duoShowdown、別モードの hunterSurvivor を soloShowdown として返すことがあるので、
    人数の形でも弾く（event.mode を持たない古いレコードもこれで判定できる）。"""
    if mode not in SHOWDOWN_MODES or not isinstance(teams, list):
        return False
    size, count = (1, 10) if mode == "soloShowdown" else (2, 5)
    return len(teams) == count and all(isinstance(t, list) and len(t) == size for t in teams)


def valid_match(match):
    """保存済みの試合にも収集時と同じモード・種別・人数の条件を適用する。

    古いレコードには eventMode がないため、その場合だけ既存の mode と人数で判定する。
    eventMode を保存しているレコードでは、別イベントや不明なイベントを再び混ぜない。
    """
    mode = match.get("mode")
    return (
        match.get("type") == "ranked"
        and valid_shape(mode, match.get("teams"))
        and ("eventMode" not in match or match["eventMode"] == mode)
    )


def normalize(b, source_tag=None):
    """battlelogの1件をショーダウンの試合レコードに変換。対象外ならNone。"""
    battle = b.get("battle", {})
    event_mode = b.get("event", {}).get("mode")
    mode = battle.get("mode")
    # トロフィー戦（type=ranked）の通常ソロ/デュオだけを残す。event.mode が別モード（trioShowdown, hunterSurvivor など）や、
    # フレンドバトル・イベント戦は対象外
    if mode not in SHOWDOWN_MODES or event_mode != mode or battle.get("type") != "ranked":
        return None
    if mode == "soloShowdown":
        teams = [[p] for p in battle.get("players", [])]
    else:
        teams = battle.get("teams", [])
    if not valid_shape(mode, teams):
        return None
    out = []
    for team in teams:
        out.append([
            {"tag": p["tag"], "brawler": p["brawler"]["name"], "brawlerId": p["brawler"].get("id"), "trophies": p["brawler"].get("trophies", 0)}
            for p in team
        ])
    if not out:
        return None
    tags = sorted(p["tag"] for t in out for p in t)
    record = {
        "id": b["battleTime"] + "|" + ",".join(tags),
        "time": b["battleTime"],
        "mode": mode,
        "eventMode": event_mode,
        "type": battle.get("type"),
        "map": b.get("event", {}).get("map"),
        "mapId": b.get("event", {}).get("id"),
        "teams": out,
    }
    if source_tag is not None:
        # 取得元プレイヤーの確定順位で配列順を照合する。合わない試合も使用数には残すが、
        # 順位の集計には使わない（取得元の順位を他の参加者へ割り当てない）。
        rank = battle.get("rank")
        record["rankOrderValid"] = (
            type(rank) is int
            and 1 <= rank <= len(out)
            and any(p["tag"] == source_tag for p in out[rank - 1])
        )
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="global,jp,kr,tw,us,br,mx,de,fr,es,it,ru,tr,gb",
                    help="ランキングを取る地域（カンマ区切り）")
    ap.add_argument("--max-players", type=int, default=3000, help="battlelogを取るプレイヤー数の上限")
    ap.add_argument("--workers", type=int, default=8, help="同時に問い合わせる数")
    ap.add_argument("--days", type=float, default=7, help="この日数より前の試合は集めない")
    ap.add_argument("--min-trophies", type=int, default=1000,
                    help="試合で見つけたプレイヤーを追加調査する最低キャラトロフィー")
    args = ap.parse_args()
    if "BRAWL_API_KEY" not in os.environ:
        sys.exit("BRAWL_API_KEY を設定してください")

    DATA.parent.mkdir(exist_ok=True)
    # キャラ名→ID（サイトで画像を出すのに使う）
    brawlers = get("/brawlers") or {}
    (DATA.parent / "brawlers.json").write_text(json.dumps(
        {b["name"]: b["id"] for b in brawlers.get("items", [])}, ensure_ascii=False))
    seen = set()
    if DATA.exists():
        with gzip.open(DATA, "rt") as f:
            seen = {json.loads(line)["id"] for line in f if line.strip()}

    since = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%Y%m%dT%H%M%S")

    queue, queued = [], set()
    for c in args.countries.split(","):
        r = get(f"/rankings/{c}/players?limit=200") or {}
        for p in r.get("items", []):
            if p["tag"] not in queued:
                queued.add(p["tag"])
                queue.append(p["tag"])

    # タグ→プレイヤー名（重複で捨てた試合からも拾い、サイトでアカウント名を出すのに使う）
    names_file = DATA.parent / "names.json"
    names = json.loads(names_file.read_text()) if names_file.exists() else {}

    added = done = 0
    with gzip.open(DATA, "at") as f, ThreadPoolExecutor(args.workers) as pool:
        while queue and done < args.max_players:
            batch = [queue.pop(0) for _ in range(min(args.workers * 4, len(queue), args.max_players - done))]
            done += len(batch)
            for source_tag, log in zip(batch, pool.map(lambda tag: get(f"/players/{tag_path(tag)}/battlelog") or {}, batch)):
                for b in log.get("items", []):
                    battle = b.get("battle", {})
                    for p in battle.get("players", []) + [p for t in battle.get("teams", []) for p in t]:
                        # 名前はサイトでアカウントを出す高トロフィー帯の分だけ残す
                        if p.get("name") and p.get("brawler", {}).get("trophies", 0) >= NAME_MIN_TROPHIES:
                            names[p["tag"]] = p["name"]
                    rec = normalize(b, source_tag)
                    if not rec or rec["id"] in seen or rec["time"] < since:
                        continue
                    seen.add(rec["id"])
                    f.write(json.dumps(rec, ensure_ascii=False, separators=(",", ":")) + "\n")
                    added += 1
                    # 高レートの対戦相手も調査対象に加えて、サンプルを広げる
                    for team in rec["teams"]:
                        for p in team:
                            if p["trophies"] >= args.min_trophies and p["tag"] not in queued:
                                queued.add(p["tag"])
                                queue.append(p["tag"])
            print(f"{done} players, +{added} matches", file=sys.stderr)
    names_file.write_text(json.dumps(names, ensure_ascii=False))
    print(f"done: {done} players checked, {added} new showdown matches, total {len(seen)}")


if __name__ == "__main__":
    main()
