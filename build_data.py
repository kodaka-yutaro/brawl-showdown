"""data/battles.jsonl から サイト用の site/data.json を作る。

キャラごとの使用は「その試合でそのキャラのトロフィー」をレートとして保存し、
レート帯・マップ・試合日での絞り込みはページ側で行う。デュオの組み合わせはチーム2人の平均トロフィーで絞る。
試合日は日本時間の YYYYMMDD（整数）で持つ。

使い方:
  python3 build_data.py [--days 14] [--keep-days 14] [--sample]

--days: 最新の試合から何日前までをサイトに載せるか（ページでは既定で直近7日を表示し、それより前は期間を広げて見る）
--keep-days: battles.jsonl に残す期間。これより古い試合はファイルから削除する（0なら削除しない）
"""
import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).parent
JST = timezone(timedelta(hours=9))
# アカウントは キャラトロフィー（デュオの組み合わせはチーム平均）がこの値以上のときだけ出す
ACCOUNT_MIN = 3000


def parse_time(s):
    return datetime.strptime(s[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=ROOT / "data" / "battles.jsonl", type=Path)
    ap.add_argument("--dst", default=ROOT / "site" / "data.json", type=Path)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--keep-days", type=int, default=14)
    ap.add_argument("--sample", action="store_true", help="画面確認用のダミーデータとして印をつける")
    args = ap.parse_args()

    with args.src.open() as f:
        matches = [json.loads(line) for line in f if line.strip()]
    newest = max(parse_time(m["time"]) for m in matches)

    if args.keep_days:
        keep_from = newest - timedelta(days=args.keep_days)
        kept = [m for m in matches if parse_time(m["time"]) >= keep_from]
        if len(kept) != len(matches):
            with args.src.open("w") as f:
                for m in kept:
                    f.write(json.dumps(m, ensure_ascii=False, separators=(",", ":")) + "\n")
            print(f"pruned {len(matches) - len(kept)} matches older than {args.keep_days} days")
        matches = kept

    ids_file = args.src.parent / "brawlers.json"
    brawler_ids = json.loads(ids_file.read_text()) if ids_file.exists() else {}
    names_file = args.src.parent / "names.json"
    player_names = json.loads(names_file.read_text()) if names_file.exists() else {}

    names, index = [], {}
    maps, map_index = [], {}
    players, pindex = [], {}

    def idx(p):
        name = p["brawler"]
        if p.get("brawlerId"):
            brawler_ids.setdefault(name, p["brawlerId"])
        if name not in index:
            index[name] = len(names)
            names.append(name)
        return index[name]

    def pidx(p, rate=None):
        if (p["trophies"] if rate is None else max(rate, p["trophies"])) < ACCOUNT_MIN:
            return -1
        if p.get("name"):
            player_names.setdefault(p["tag"], p["name"])
        if p["tag"] not in pindex:
            pindex[p["tag"]] = len(players)
            players.append(p["tag"])
        return pindex[p["tag"]]

    def midx(m):
        name = m.get("map") or "不明"
        if name not in map_index:
            map_index[name] = len(maps)
            maps.append({"name": name, "ids": {}})
        if m.get("mapId"):
            maps[map_index[name]]["ids"]["solo" if m["mode"] == "soloShowdown" else "duo"] = m["mapId"]
        return map_index[name]

    # 1試合 = [マップ, 日付, 各チーム（順位順）...]。
    # ソロのチームは [キャラ, トロフィー, プレイヤー]、デュオは [キャラA, トロA, プレイヤーA, キャラB, トロB, プレイヤーB]
    show_from = newest - timedelta(days=args.days)
    solo, duo = [], []
    days = set()
    for m in matches:
        t = parse_time(m["time"])
        if t < show_from:
            continue
        day = int(t.astimezone(JST).strftime("%Y%m%d"))
        days.add(day)
        head = [midx(m), day]
        if m["mode"] == "soloShowdown":
            solo.append(head + [[idx(t[0]), t[0]["trophies"], pidx(t[0])] for t in m["teams"]])
        else:
            teams = []
            for team in m["teams"]:
                if len(team) != 2:
                    continue
                a, b = sorted(team, key=lambda p: p["brawler"])
                avg = (a["trophies"] + b["trophies"]) / 2
                teams.append([idx(a), a["trophies"], pidx(a, avg), idx(b), b["trophies"], pidx(b, avg)])
            duo.append(head + teams)
    out = {
        "sample": args.sample,
        "days": sorted(days),
        "accountMin": ACCOUNT_MIN,
        "brawlers": [{"name": n, "id": brawler_ids.get(n)} for n in names],
        "maps": maps,
        "players": [[tag, player_names.get(tag, "")] for tag in players],
        "solo": solo,
        "duo": duo,
    }
    args.dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {args.dst}: solo {len(solo)} matches, duo {len(duo)} matches, {len(maps)} maps (last {args.days} days)")


if __name__ == "__main__":
    main()
