"""data/battles.jsonl.gz から サイト用の site/data.json を作る。

キャラごとの使用は「その試合でそのキャラのトロフィー」をレートとして保存し、
レート帯・マップ・試合日での絞り込みはページ側で行う。デュオの組み合わせはチーム2人の平均トロフィーで絞る。
試合日は日本時間の YYYYMMDD（整数）で持つ。

使い方:
  python3 build_data.py [--days 14] [--keep-days 14] [--sample]

--days: 最新の試合から何日前までをサイトに載せるか（ページでは既定で直近7日を表示し、それより前は期間を広げて見る）
--keep-days: battles.jsonl に残す期間。これより古い試合はファイルから削除する（0なら削除しない）
"""
import argparse
import gzip
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collect import valid_shape

ROOT = Path(__file__).parent
JST = timezone(timedelta(hours=9))
# ソロ・デュオのアカウントは キャラトロフィーがこの値以上のときだけ出す
ACCOUNT_MIN = 3000
# デュオの組み合わせのアカウントは、トロフィーに関係なくその組み合わせを期間中にこの回数以上使った人だけ出す
PAIR_ACCOUNT_GAMES = 5
# 使用数を数えるトロフィー帯の幅（ページの入力もこの刻み）
BUCKET = 50


def parse_time(s):
    return datetime.strptime(s[:15], "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=ROOT / "data" / "battles.jsonl.gz", type=Path)
    ap.add_argument("--dst", default=ROOT / "site" / "data.json", type=Path)
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--keep-days", type=int, default=14)
    ap.add_argument("--sample", action="store_true", help="画面確認用のダミーデータとして印をつける")
    args = ap.parse_args()

    with gzip.open(args.src, "rt") as f:
        matches = [json.loads(line) for line in f if line.strip()]
    # トロフィー戦と確認できない試合（種別を記録していない古いレコード、他モード、フレンドバトル）を除く
    bad = [m for m in matches if not valid_shape(m["mode"], m["teams"]) or m.get("type") != "ranked"]
    if bad:
        matches = [m for m in matches if valid_shape(m["mode"], m["teams"]) and m.get("type") == "ranked"]
        with gzip.open(args.src, "wt") as f:
            for m in matches:
                f.write(json.dumps(m, ensure_ascii=False, separators=(",", ":")) + "\n")
        print(f"removed {len(bad)} matches that are not solo/duo showdown")
    # 同じ試合を別のプレイヤーの戦績から拾うと終了時刻が数分ずれることがあるので、
    # 同じモード・同じ顔ぶれで5分以内の試合は1試合として数える
    last, uniq = {}, []
    for m in sorted(matches, key=lambda m: m["time"]):
        key = (m["mode"], m["id"].split("|", 1)[1])
        t = parse_time(m["time"])
        if key in last and t - last[key] <= timedelta(minutes=5):
            continue
        last[key] = t
        uniq.append(m)
    if len(uniq) != len(matches):
        print(f"merged {len(matches) - len(uniq)} duplicate matches")
    matches = uniq
    newest = max(parse_time(m["time"]) for m in matches)

    if args.keep_days:
        keep_from = newest - timedelta(days=args.keep_days)
        kept = [m for m in matches if parse_time(m["time"]) >= keep_from]
        if len(kept) != len(matches):
            with gzip.open(args.src, "wt") as f:
                for m in kept:
                    f.write(json.dumps(m, ensure_ascii=False, separators=(",", ":")) + "\n")
            print(f"pruned {len(matches) - len(kept)} matches older than {args.keep_days} days")
        matches = kept

    ids_file = args.src.parent / "brawlers.json"
    brawler_ids = json.loads(ids_file.read_text()) if ids_file.exists() else {}
    # マップ名の日本語・中国語・韓国語（ゲームの翻訳ファイルから作ったもの。英語名がキー）
    map_names_file = ROOT / "i18n" / "map-names.json"
    map_names = json.loads(map_names_file.read_text()) if map_names_file.exists() else {}
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

    def pidx(p, need_min=True):
        if need_min and p["trophies"] < ACCOUNT_MIN:
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
            maps.append({"name": name, "ids": {}, "local": map_names.get(name, {})})
        if m.get("mapId"):
            maps[map_index[name]]["ids"]["solo" if m["mode"] == "soloShowdown" else "duo"] = m["mapId"]
        return map_index[name]

    # 試合が増えてもファイルが膨らまないよう、使用数は (マップ, 日付, キャラ, トロフィー帯) ごとに数えて持つ。
    # トロフィー帯は BUCKET 刻みの下限値。デュオの組み合わせは2人の平均トロフィーの帯。
    # アカウント表示用の個別の使用（ACCOUNT_MIN 以上）だけは1件ずつ持つ。
    show_from = newest - timedelta(days=args.days)
    count = {"solo": Counter(), "duo": Counter(), "pair": Counter(), "matches": Counter()}
    acc = {"solo": [], "duo": [], "pair": []}
    pair_uses, pair_games = [], Counter()
    days = set()
    band = lambda tr: tr // BUCKET * BUCKET
    for m in matches:
        t = parse_time(m["time"])
        if t < show_from:
            continue
        day = int(t.astimezone(JST).strftime("%Y%m%d"))
        days.add(day)
        mi = midx(m)
        solo = m["mode"] == "soloShowdown"
        count["matches"][("solo" if solo else "duo", mi, day)] += 1
        for place, team in enumerate(m["teams"], start=1):
            if solo:
                p = team[0]
                count["solo"][(mi, day, idx(p), band(p["trophies"]))] += 1
                if (pi := pidx(p)) >= 0:
                    acc["solo"].append([mi, day, idx(p), pi, p["trophies"], place])
                continue
            a, b = sorted(team, key=lambda p: p["brawler"])
            avg = (a["trophies"] + b["trophies"]) // 2
            count["pair"][(mi, day, idx(a), idx(b), band(avg))] += 1
            for p in (a, b):
                count["duo"][(mi, day, idx(p), band(p["trophies"]))] += 1
                if (pi := pidx(p)) >= 0:
                    acc["duo"].append([mi, day, idx(p), pi, p["trophies"], place])
            for side, p in enumerate((a, b)):
                pair_games[(idx(a), idx(b), p["tag"])] += 1
                pair_uses.append((mi, day, idx(a), idx(b), p, side, avg, place))
    for mi, day, ia, ib, p, side, avg, place in pair_uses:
        if pair_games[(ia, ib, p["tag"])] >= PAIR_ACCOUNT_GAMES:
            acc["pair"].append([mi, day, ia, ib, pidx(p, need_min=False), side, avg, place])
    rows = lambda c: [[*k, n] for k, n in c.items()]
    out = {
        "sample": args.sample,
        "days": sorted(days),
        "bucket": BUCKET,
        "accountMin": ACCOUNT_MIN,
        "pairAccountGames": PAIR_ACCOUNT_GAMES,
        "brawlers": [{"name": n, "id": brawler_ids.get(n)} for n in names],
        "maps": maps,
        "players": [[tag, player_names.get(tag, "")] for tag in players],
        # [ソロ/デュオ, マップ, 日付, 試合数]
        "matches": rows(count["matches"]),
        # [マップ, 日付, キャラ, トロフィー帯, 使用数]（pair は [マップ, 日付, キャラA, キャラB, 平均トロフィー帯, チーム数]）
        "solo": rows(count["solo"]),
        "duo": rows(count["duo"]),
        "pair": rows(count["pair"]),
        # [マップ, 日付, キャラ, プレイヤー, トロフィー, 順位]（pair は [マップ, 日付, キャラA, キャラB, プレイヤー, A/Bどちらを使ったか(0/1), チーム平均トロフィー, 順位]）
        "accounts": acc,
    }
    args.dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    n_solo = sum(n for (mode, *_), n in count["matches"].items() if mode == "solo")
    n_duo = sum(n for (mode, *_), n in count["matches"].items() if mode == "duo")
    print(f"wrote {args.dst}: solo {n_solo} matches, duo {n_duo} matches, {len(maps)} maps (last {args.days} days)")


if __name__ == "__main__":
    main()
