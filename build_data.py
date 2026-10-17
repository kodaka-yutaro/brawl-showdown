"""data/battles.jsonl から サイト用の site/data.json を作る。

キャラごとの使用は「その試合でそのキャラのトロフィー」をレートとして保存し、
レート帯での絞り込みはページ側で行う。デュオの組み合わせはチーム2人の平均トロフィーで絞る。

使い方:
  python3 build_data.py [--days 30] [--keep-days 60] [--sample]

--days: 最新の試合から何日前までをサイトに載せるか（休止中のプレイヤーの古い試合を除くため）
--keep-days: battles.jsonl に残す期間。これより古い試合はファイルから削除する（0なら削除しない）
"""
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent


def parse_time(s):
    return datetime.strptime(s[:15], "%Y%m%dT%H%M%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=ROOT / "data" / "battles.jsonl", type=Path)
    ap.add_argument("--dst", default=ROOT / "site" / "data.json", type=Path)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--keep-days", type=int, default=60)
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
                    f.write(json.dumps(m, ensure_ascii=False) + "\n")
            print(f"pruned {len(matches) - len(kept)} matches older than {args.keep_days} days")
        matches = kept

    show_from = newest - timedelta(days=args.days)
    names, index = [], {}

    def idx(name):
        if name not in index:
            index[name] = len(names)
            names.append(name)
        return index[name]

    solo, duo = [], []
    counts = {"solo": 0, "duo": 0}
    times = []
    for m in matches:
        if parse_time(m["time"]) < show_from:
            continue
        times.append(m["time"])
        if m["mode"] == "soloShowdown":
            counts["solo"] += 1
            for team in m["teams"]:
                p = team[0]
                solo.append([idx(p["brawler"]), p["trophies"]])
        else:
            counts["duo"] += 1
            for team in m["teams"]:
                if len(team) != 2:
                    continue
                a, b = sorted(team, key=lambda p: p["brawler"])
                duo.append([idx(a["brawler"]), a["trophies"], idx(b["brawler"]), b["trophies"]])
    out = {
        "sample": args.sample,
        "from": min(times) if times else None,
        "to": max(times) if times else None,
        "matches": counts,
        "brawlers": names,
        "solo": solo,
        "duo": duo,
    }
    args.dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {args.dst}: solo {counts['solo']} matches, duo {counts['duo']} matches (last {args.days} days)")


if __name__ == "__main__":
    main()
