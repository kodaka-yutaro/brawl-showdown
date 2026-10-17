"""Brawl Stars 公式APIからショーダウン（ソロ/デュオ）の試合を集めて data/battles.jsonl に追記する。

使い方:
  BRAWL_API_KEY=... python3 collect.py [--countries global,jp] [--max-players 500]

APIキーは「APIを呼ぶ側のIP」でしか使えない。既定ではRoyaleAPIの公開プロキシ
(https://bsproxy.royaleapi.dev/v1) を経由するので、キー作成時にプロキシのIPを登録しておく。
自分のPCなど固定IPから直接呼ぶ場合は BRAWL_API_BASE=https://api.brawlstars.com/v1 を指定する。
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API_BASE = os.environ.get("BRAWL_API_BASE", "https://bsproxy.royaleapi.dev/v1")
SHOWDOWN_MODES = {"soloShowdown", "duoShowdown"}
DATA = Path(__file__).parent / "data" / "battles.jsonl"


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


def normalize(b):
    """battlelogの1件をショーダウンの試合レコードに変換。対象外ならNone。"""
    battle = b.get("battle", {})
    mode = battle.get("mode") or b.get("event", {}).get("mode")
    if mode not in SHOWDOWN_MODES:
        return None
    if mode == "soloShowdown":
        teams = [[p] for p in battle.get("players", [])]
    else:
        teams = battle.get("teams", [])
    out = []
    for rank, team in enumerate(teams, start=1):
        out.append([
            {"tag": p["tag"], "brawler": p["brawler"]["name"], "trophies": p["brawler"].get("trophies", 0), "rank": rank}
            for p in team
        ])
    if not out:
        return None
    tags = sorted(p["tag"] for t in out for p in t)
    return {
        "id": b["battleTime"] + "|" + ",".join(tags),
        "time": b["battleTime"],
        "mode": mode,
        "map": b.get("event", {}).get("map"),
        "teams": out,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="global,jp", help="ランキングを取る地域（カンマ区切り）")
    ap.add_argument("--max-players", type=int, default=400, help="battlelogを取るプレイヤー数の上限")
    ap.add_argument("--min-trophies", type=int, default=1000,
                    help="試合で見つけたプレイヤーを追加調査する最低キャラトロフィー")
    args = ap.parse_args()
    if "BRAWL_API_KEY" not in os.environ:
        sys.exit("BRAWL_API_KEY を設定してください")

    DATA.parent.mkdir(exist_ok=True)
    seen = set()
    if DATA.exists():
        with DATA.open() as f:
            seen = {json.loads(line)["id"] for line in f if line.strip()}

    queue, queued = [], set()
    for c in args.countries.split(","):
        r = get(f"/rankings/{c}/players?limit=200") or {}
        for p in r.get("items", []):
            if p["tag"] not in queued:
                queued.add(p["tag"])
                queue.append(p["tag"])

    added = done = 0
    with DATA.open("a") as f:
        while queue and done < args.max_players:
            tag = queue.pop(0)
            done += 1
            log = get(f"/players/{tag_path(tag)}/battlelog") or {}
            for b in log.get("items", []):
                rec = normalize(b)
                if not rec or rec["id"] in seen:
                    continue
                seen.add(rec["id"])
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                added += 1
                # 高レートの対戦相手も調査対象に加えて、サンプルを広げる
                for team in rec["teams"]:
                    for p in team:
                        if p["trophies"] >= args.min_trophies and p["tag"] not in queued:
                            queued.add(p["tag"])
                            queue.append(p["tag"])
            time.sleep(0.05)
            if done % 50 == 0:
                print(f"{done} players, +{added} matches", file=sys.stderr)
    print(f"done: {done} players checked, {added} new showdown matches, total {len(seen)}")


if __name__ == "__main__":
    main()
