"""data/battles.jsonl から サイト用の site/data.json を作る。

キャラごとの使用は「その試合でそのキャラのトロフィー」をレートとして保存し、
レート帯での絞り込みはページ側で行う。デュオの組み合わせはチーム2人の平均トロフィーで絞る。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent


def main(src=ROOT / "data" / "battles.jsonl", dst=ROOT / "site" / "data.json", sample=False):
    names, index = [], {}

    def idx(name):
        if name not in index:
            index[name] = len(names)
            names.append(name)
        return index[name]

    solo, duo = [], []
    counts = {"solo": 0, "duo": 0}
    times = []
    with open(src) as f:
        for line in f:
            if not line.strip():
                continue
            m = json.loads(line)
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
        "sample": sample,
        "from": min(times) if times else None,
        "to": max(times) if times else None,
        "matches": counts,
        "brawlers": names,
        "solo": solo,
        "duo": duo,
    }
    Path(dst).write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {dst}: solo {counts['solo']} matches, duo {counts['duo']} matches")


if __name__ == "__main__":
    args = sys.argv[1:]
    sample = "--sample" in args
    args = [a for a in args if a != "--sample"]
    main(*(args or []), sample=sample) if args else main(sample=sample)
