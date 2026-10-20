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
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collect import valid_match

ROOT = Path(__file__).parent
JST = timezone(timedelta(hours=9))
# ソロ・デュオのアカウントは キャラトロフィーがこの値以上のときだけ出す
ACCOUNT_MIN = 3000
# デュオの組み合わせのアカウントは、トロフィーに関係なく同じ2人でその組み合わせを期間中にこの回数以上使ったペアだけ出す
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
    bad = [m for m in matches if not valid_match(m)]
    if bad:
        matches = [m for m in matches if valid_match(m)]
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
    brawler_names_file = ROOT / "i18n" / "brawler-names.json"
    brawler_local = json.loads(brawler_names_file.read_text()) if brawler_names_file.exists() else {}
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
    rank_sums = {"solo": Counter(), "duo": Counter(), "pair": Counter()}

    def add_use(view, key, place):
        count[view][key] += 1
        previous = rank_sums[view][key]
        rank_sums[view][key] = None if place is None or previous is None else previous + place

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
        for order, team in enumerate(m["teams"], start=1):
            # 旧レコードは従来の配列順。APIの順位との照合が不一致なら、使用数を残して順位だけ欠損にする。
            place = None if m.get("rankOrderValid") is False else order
            if solo:
                p = team[0]
                add_use("solo", (mi, day, idx(p), band(p["trophies"])), place)
                if (pi := pidx(p)) >= 0:
                    acc["solo"].append([mi, day, idx(p), pi, p["trophies"], place])
                continue
            a, b = sorted(team, key=lambda p: p["brawler"])
            avg = (a["trophies"] + b["trophies"]) // 2
            add_use("pair", (mi, day, idx(a), idx(b), band(avg)), place)
            for p in (a, b):
                add_use("duo", (mi, day, idx(p), band(p["trophies"])), place)
                if (pi := pidx(p)) >= 0:
                    acc["duo"].append([mi, day, idx(p), pi, p["trophies"], place])
            pair_games[(idx(a), idx(b), a["tag"], b["tag"])] += 1
            pair_uses.append((mi, day, a, b, avg, place))
    for mi, day, a, b, avg, place in pair_uses:
        if pair_games[(idx(a), idx(b), a["tag"], b["tag"])] >= PAIR_ACCOUNT_GAMES:
            acc["pair"].append([mi, day, idx(a), idx(b), pidx(a, need_min=False), pidx(b, need_min=False), avg, place])
    rows = lambda c: [[*k, n] for k, n in c.items()]
    out = {
        "sample": args.sample,
        # サイト用データを作った時刻（UTC）。ページで「最終更新」として出す
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days": sorted(days),
        "bucket": BUCKET,
        "accountMin": ACCOUNT_MIN,
        "pairAccountGames": PAIR_ACCOUNT_GAMES,
        "brawlers": [{"name": n, "id": brawler_ids.get(n), "local": brawler_local.get(n, {})} for n in names],
        "maps": maps,
        "players": [[tag, player_names.get(tag, "")] for tag in players],
        # [ソロ/デュオ, マップ, 日付, 試合数]
        "matches": rows(count["matches"]),
        # [マップ, 日付, キャラ, トロフィー帯, 使用数]（pair は [マップ, 日付, キャラA, キャラB, 平均トロフィー帯, チーム数]）
        "solo": rows(count["solo"]),
        "duo": rows(count["duo"]),
        "pair": rows(count["pair"]),
        # solo/duo/pair の各行と同じ順の順位合計（順位を確認できない試合を含む行は null）。
        # 絞り込み後に使用数で割り、試合数で重み付けした平均を出す。
        "rankSums": {view: [rank_sums[view][key] for key in count[view]] for view in rank_sums},
        # [マップ, 日付, キャラ, プレイヤー, トロフィー, 順位]（pair は [マップ, 日付, キャラA, キャラB, キャラAのプレイヤー, キャラBのプレイヤー, チーム平均トロフィー, 順位]）
        "accounts": acc,
    }
    args.dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    if not args.sample:
        write_snapshot(out, args.dst.parent)
    n_solo = sum(n for (mode, *_), n in count["matches"].items() if mode == "solo")
    n_duo = sum(n for (mode, *_), n in count["matches"].items() if mode == "duo")
    print(f"wrote {args.dst}: solo {n_solo} matches, duo {n_duo} matches, {len(maps)} maps (last {args.days} days)")


SNAP_MIN = 2000  # まとめに使うトロフィーの下限
SNAP_DAYS = 7


def write_snapshot(d, site):
    """検索エンジンにも読める日本語のまとめを index.html に書き込み、sitemap の更新日を今日にする。

    ページ本体の表はブラウザで data.json から作るので、ここでは直近7日・トロフィー2000以上の上位だけを静的な文で残す。
    """
    days = set(d["days"][-SNAP_DAYS:])
    ja = lambda i: d["brawlers"][i]["local"].get("ja") or d["brawlers"][i]["name"]
    map_ja = lambda i: d["maps"][i]["local"].get("ja") or d["maps"][i]["name"]
    esc = lambda x: x.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def top(rows, key, n, map_i=None):
        c = Counter()
        for r in rows:
            if r[1] in days and r[-2] >= SNAP_MIN and (map_i is None or r[0] == map_i):
                c[key(r)] += r[-1]
        return c.most_common(n)

    solo = top(d["solo"], lambda r: r[2], 10)
    duo = top(d["duo"], lambda r: r[2], 10)
    pair = top(d["pair"], lambda r: (r[2], r[3]), 10)
    li = lambda rows, f: "".join(f"<li>{esc(f(k))}</li>" for k, _ in rows)
    maps = []
    for mode, rows in (("ソロ", d["solo"]), ("デュオ", d["duo"])):
        mm = Counter()
        for r in d["matches"]:
            if r[0] == ("solo" if mode == "ソロ" else "duo") and r[2] in days and d["maps"][r[1]]["name"] != "不明":
                mm[r[1]] += r[3]
        for mi, _ in mm.most_common():
            t3 = top(rows, lambda r: r[2], 3, mi)
            if t3:
                maps.append(f"<dt>{esc(map_ja(mi))}（{mode}）</dt><dd>{esc('、'.join(ja(k) for k, _ in t3))}</dd>")
    first, last = d["days"][-SNAP_DAYS:][0], d["days"][-1]
    fmt = lambda x: f"{x // 10000}/{x // 100 % 100}/{x % 100}"
    html = f"""<section class="intro snapshot" id="snapshot">
    <h2>ブロスタ バトロワ最強キャラランキング（トロフィー{SNAP_MIN}以上）</h2>
    <p>{fmt(first)}〜{fmt(last)}の試合で、キャラトロフィー{SNAP_MIN}以上のプレイヤーによく使われたキャラです。1時間ごとに自動で更新しています。</p>
    <h3>ソロバトロワ 使用数トップ10</h3><ol>{li(solo, ja)}</ol>
    <h3>デュオバトロワ 使用数トップ10</h3><ol>{li(duo, ja)}</ol>
    <h3>デュオバトロワ 組み合わせトップ10</h3><ol>{li(pair, lambda k: ja(k[0]) + "＋" + ja(k[1]))}</ol>
    <h3>マップ別 よく使われるキャラ</h3><dl class="maplist">{"".join(maps)}</dl>
  </section>"""
    index = site / "index.html"
    page = index.read_text()
    start, end = "<!-- snapshot:start -->", "<!-- snapshot:end -->"
    a, b = page.index(start) + len(start), page.index(end)
    index.write_text(page[:a] + html + page[b:])
    today = datetime.now(JST).strftime("%Y-%m-%d")
    sitemap = site / "sitemap.xml"
    sitemap.write_text(re.sub(r"(<loc>https://brawl\.kdking-tools\.com/</loc><lastmod>)[^<]*", rf"\g<1>{today}", sitemap.read_text()))


if __name__ == "__main__":
    main()
