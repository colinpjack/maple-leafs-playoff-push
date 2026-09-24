#!/usr/bin/env python3
"""Fetch Maple Leafs playoff-race data and write data.json for GitHub Pages."""

from __future__ import annotations

import hashlib
import json
import random
import ssl
import subprocess
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Toronto")
USER_AGENT = "MapleLeafsPlayoffDash/1.0 (+github-pages refresh)"
ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data.json"
LEAF = "TOR"
FINAL_STATES = {"OFF", "FINAL", "OVER"}
CLINCHED = {"x", "y", "z", "p"}
OT_RATE = 0.23
HOME_BUMP = 0.04
SIMS = 2500

_PREFER_CURL = False


def toronto_now() -> datetime:
    return datetime.now(TZ)


def target_season_id(now: datetime) -> int:
    """NHL seasons turn over in July, after the Cup and before camp."""
    start = now.year if now.month >= 7 else now.year - 1
    return int(f"{start}{start + 1}")


def previous_season_id(season: int) -> int:
    start = int(str(season)[:4]) - 1
    return int(f"{start}{start + 1}")


def season_label(season: int) -> str:
    text = str(season)
    return f"{text[:4]}–{text[6:]}"


def loc(value) -> str:
    if isinstance(value, dict):
        return str(value.get("default") or next(iter(value.values()), "") or "")
    return "" if value is None else str(value)


def fetch_json(url: str, retries: int = 3) -> dict:
    global _PREFER_CURL
    last_err: Exception | None = None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if not _PREFER_CURL:
        for attempt in range(retries):
            try:
                req = urllib.request.Request(url, headers=headers)
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=45, context=ctx) as resp:
                    return json.load(resp)
            except Exception as err:
                last_err = err
                time.sleep(0.4 * (attempt + 1))
        _PREFER_CURL = True
    for attempt in range(retries):
        try:
            completed = subprocess.run(
                ["curl", "-fsSL", "-A", USER_AGENT, url],
                check=True,
                capture_output=True,
                text=True,
                timeout=45,
            )
            return json.loads(completed.stdout)
        except Exception as err:
            last_err = err
            time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_err}") from last_err


def wlt(wins: int, losses: int, otl: int) -> str:
    return f"{wins}-{losses}-{otl}"


def streak_label(code: str | None, count: int | None) -> str:
    if not code or not count:
        return "—"
    return f"{code}{int(count)}"


def blank_counts() -> dict:
    return {
        "gp": 0,
        "wins": 0,
        "losses": 0,
        "otl": 0,
        "points": 0,
        "rw": 0,
        "row": 0,
        "gf": 0,
        "ga": 0,
        "diff": 0,
        "homeWins": 0,
        "homeLosses": 0,
        "homeOtl": 0,
        "homePoints": 0,
        "roadWins": 0,
        "roadLosses": 0,
        "roadOtl": 0,
        "roadPoints": 0,
        "l10Wins": 0,
        "l10Losses": 0,
        "l10Otl": 0,
        "l10Points": None,
        "l10gp": 0,
        "streak": "—",
        "clinch": "",
        "pointPct": None,
        "record": "0-0-0",
        "home": "0-0-0",
        "road": "0-0-0",
        "l10": "—",
    }


def finish_rates(team: dict, season_games: int) -> None:
    team["diff"] = int(team["gf"]) - int(team["ga"])
    team["record"] = wlt(team["wins"], team["losses"], team["otl"])
    team["home"] = wlt(team["homeWins"], team["homeLosses"], team["homeOtl"])
    team["road"] = wlt(team["roadWins"], team["roadLosses"], team["roadOtl"])
    if team["l10gp"]:
        team["l10"] = wlt(team["l10Wins"], team["l10Losses"], team["l10Otl"])
    else:
        team["l10"] = "—"
        team["l10Points"] = None
    gp = int(team["gp"])
    team["pointPct"] = round(team["points"] / (2 * gp), 3) if gp else None
    scheduled = int(team.get("seasonGames") or season_games or 0)
    team["pace"] = round(team["points"] / gp * scheduled) if gp and scheduled else None
    team["maxPoints"] = int(team["points"]) + 2 * int(team.get("gr") or 0)
    team["xpts"] = expected_points(team["gf"], team["ga"], gp)
    team["otWins"] = max(0, int(team["row"]) - int(team["rw"]))
    team["soWins"] = max(0, int(team["wins"]) - int(team["row"]))


def expected_points(gf: int, ga: int, gp: int) -> float | None:
    if gp <= 0 or (gf <= 0 and ga <= 0):
        return None
    exp = 2.05
    gf_e = max(gf, 0) ** exp
    ga_e = max(ga, 0) ** exp
    if gf_e + ga_e == 0:
        return None
    return round((gf_e / (gf_e + ga_e)) * 2 * gp, 1)


def meta_from_row(row: dict) -> dict:
    return {
        "abbr": loc(row.get("teamAbbrev")),
        "name": loc(row.get("teamName")),
        "common": loc(row.get("teamCommonName")),
        "place": loc(row.get("placeName")),
        "logo": row.get("teamLogo") or "",
        "conference": row.get("conferenceName") or "",
        "conferenceAbbrev": row.get("conferenceAbbrev") or "",
        "division": row.get("divisionName") or "",
        "divisionAbbrev": row.get("divisionAbbrev") or "",
    }


def apply_official_row(team: dict, row: dict) -> None:
    team.update(blank_counts())
    team.update(
        {
            "gp": int(row.get("gamesPlayed") or 0),
            "wins": int(row.get("wins") or 0),
            "losses": int(row.get("losses") or 0),
            "otl": int(row.get("otLosses") or 0),
            "points": int(row.get("points") or 0),
            "rw": int(row.get("regulationWins") or 0),
            "row": int(row.get("regulationPlusOtWins") or 0),
            "gf": int(row.get("goalFor") or 0),
            "ga": int(row.get("goalAgainst") or 0),
            "diff": int(row.get("goalDifferential") or 0),
            "homeWins": int(row.get("homeWins") or 0),
            "homeLosses": int(row.get("homeLosses") or 0),
            "homeOtl": int(row.get("homeOtLosses") or 0),
            "homePoints": int(row.get("homePoints") or 0),
            "roadWins": int(row.get("roadWins") or 0),
            "roadLosses": int(row.get("roadLosses") or 0),
            "roadOtl": int(row.get("roadOtLosses") or 0),
            "roadPoints": int(row.get("roadPoints") or 0),
            "l10Wins": int(row.get("l10Wins") or 0),
            "l10Losses": int(row.get("l10Losses") or 0),
            "l10Otl": int(row.get("l10OtLosses") or 0),
            "l10Points": int(row.get("l10Points") or 0),
            "l10gp": int(row.get("l10GamesPlayed") or 0),
            "streak": streak_label(row.get("streakCode"), row.get("streakCount")),
            "clinch": (row.get("clinchIndicator") or "") or "",
        }
    )
    if not team["l10gp"]:
        team["l10Points"] = None


def teams_from_rows(rows: list[dict], season_games: int) -> list[dict]:
    teams = []
    for row in rows:
        team = meta_from_row(row)
        apply_official_row(team, row)
        team["gr"] = max(0, season_games - team["gp"]) if season_games else 0
        team["seasonGames"] = season_games
        finish_rates(team, season_games)
        teams.append(team)
    return teams


def zero_teams(templates: list[dict], season_games: int) -> list[dict]:
    teams = []
    for src in templates:
        team = {
            "abbr": src["abbr"],
            "name": src["name"],
            "common": src["common"],
            "place": src["place"],
            "logo": src["logo"],
            "conference": src["conference"],
            "conferenceAbbrev": src["conferenceAbbrev"],
            "division": src["division"],
            "divisionAbbrev": src["divisionAbbrev"],
        }
        team.update(blank_counts())
        team["gr"] = season_games
        team["seasonGames"] = season_games
        team["maxPoints"] = 2 * season_games
        team["otWins"] = 0
        team["soWins"] = 0
        team["xpts"] = None
        team["pace"] = None
        teams.append(team)
    return teams


def parse_game(raw: dict) -> dict:
    home = raw.get("homeTeam") or {}
    away = raw.get("awayTeam") or {}
    outcome = raw.get("gameOutcome") or {}
    period = outcome.get("lastPeriodType") or (raw.get("periodDescriptor") or {}).get("periodType") or "REG"
    return {
        "id": raw.get("id"),
        "gameType": raw.get("gameType"),
        "date": raw.get("gameDate"),
        "start": raw.get("startTimeUTC"),
        "state": raw.get("gameState") or "",
        "venue": loc(raw.get("venue")),
        "home": home.get("abbrev"),
        "away": away.get("abbrev"),
        "homeScore": home.get("score"),
        "awayScore": away.get("score"),
        "periodType": period,
        "ot": period in {"OT", "SO"},
        "homeLogo": home.get("logo") or "",
        "awayLogo": away.get("logo") or "",
    }


def collect_games(schedules: dict[str, dict]) -> list[dict]:
    found: dict[int, dict] = {}
    for payload in schedules.values():
        for raw in payload.get("games") or []:
            game = parse_game(raw)
            if game["id"] is not None and game["home"] and game["away"]:
                found[int(game["id"])] = game
    return sorted(found.values(), key=lambda g: (g["date"] or "", g["id"] or 0))


def result_for(abbr: str, game: dict) -> str | None:
    if game.get("homeScore") is None or game.get("awayScore") is None:
        return None
    us = game["homeScore"] if game["home"] == abbr else game["awayScore"]
    them = game["awayScore"] if game["home"] == abbr else game["homeScore"]
    if us > them:
        return "W"
    if game["ot"]:
        return "OTL"
    return "L"


def points_for(result: str) -> int:
    if result == "W":
        return 2
    if result == "OTL":
        return 1
    return 0


def apply_results(teams: list[dict], games: list[dict], season_games: int) -> None:
    by_abbr = {team["abbr"]: team for team in teams}
    for team in teams:
        clinch = team.get("clinch") or ""
        team.update(blank_counts())
        team["clinch"] = clinch
        team["seasonGames"] = season_games
    finals = [
        game for game in games
        if game["gameType"] == 2 and game["state"] in FINAL_STATES and game["homeScore"] is not None
    ]
    for game in finals:
        home = by_abbr.get(game["home"])
        away = by_abbr.get(game["away"])
        if not home or not away or game["homeScore"] == game["awayScore"]:
            continue
        if game["homeScore"] > game["awayScore"]:
            winner, loser = home, away
            wscore, lscore = game["homeScore"], game["awayScore"]
            winner_home = True
        else:
            winner, loser = away, home
            wscore, lscore = game["awayScore"], game["homeScore"]
            winner_home = False
        winner["wins"] += 1
        winner["points"] += 2
        winner["gf"] += wscore
        winner["ga"] += lscore
        loser["gf"] += lscore
        loser["ga"] += wscore
        winner["gp"] += 1
        loser["gp"] += 1
        if winner_home:
            winner["homeWins"] += 1
            winner["homePoints"] += 2
        else:
            winner["roadWins"] += 1
            winner["roadPoints"] += 2
        if game["ot"]:
            loser["otl"] += 1
            loser["points"] += 1
            winner["row"] += 1
            if winner_home:
                loser["roadOtl"] += 1
                loser["roadPoints"] += 1
            else:
                loser["homeOtl"] += 1
                loser["homePoints"] += 1
        else:
            loser["losses"] += 1
            winner["rw"] += 1
            winner["row"] += 1
            if winner_home:
                loser["roadLosses"] += 1
            else:
                loser["homeLosses"] += 1
    for team in teams:
        theirs = [
            game for game in finals
            if team["abbr"] in (game["home"], game["away"])
        ]
        theirs.sort(key=lambda game: (game["date"] or "", game["id"] or 0))
        last = theirs[-10:]
        if last:
            results = [result_for(team["abbr"], game) or "L" for game in last]
            team["l10Wins"] = results.count("W")
            team["l10Losses"] = results.count("L")
            team["l10Otl"] = results.count("OTL")
            team["l10gp"] = len(results)
            team["l10Points"] = sum(points_for(item) for item in results)
            streak_code = {"W": "W", "L": "L", "OTL": "OT"}[results[-1]]
            count = 1
            for item in reversed(results[:-1]):
                if {"W": "W", "L": "L", "OTL": "OT"}[item] != streak_code:
                    break
                count += 1
            team["streak"] = f"{streak_code}{count}"
        remaining = sum(
            1
            for game in games
            if game["gameType"] == 2
            and game["state"] not in FINAL_STATES
            and team["abbr"] in (game["home"], game["away"])
        )
        team["gr"] = remaining
        finish_rates(team, season_games)


def tie_key(team: dict) -> tuple:
    return (
        -int(team.get("points") or 0),
        -int(team.get("rw") or 0),
        -int(team.get("row") or 0),
        -int(team.get("wins") or 0),
        -int(team.get("diff") or 0),
        team.get("abbr") or "",
    )


def playoff_field(teams: list[dict]) -> tuple[list[dict], list[dict]]:
    east = [team for team in teams if team.get("conferenceAbbrev") == "E"]
    inside: set[str] = set()
    for division in ("A", "M"):
        ranked = sorted((team for team in east if team.get("divisionAbbrev") == division), key=tie_key)
        inside.update(team["abbr"] for team in ranked[:3])
    outsiders = sorted((team for team in east if team["abbr"] not in inside), key=tie_key)
    inside.update(team["abbr"] for team in outsiders[:2])
    ordered_in = sorted((team for team in east if team["abbr"] in inside), key=tie_key)
    ordered_out = sorted((team for team in east if team["abbr"] not in inside), key=tie_key)
    return ordered_in, ordered_out


def division_rank_map(teams: list[dict]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    east = [team for team in teams if team.get("conferenceAbbrev") == "E"]
    for division in {team["divisionAbbrev"] for team in east}:
        ranked = sorted((team for team in east if team["divisionAbbrev"] == division), key=tie_key)
        for index, team in enumerate(ranked, start=1):
            ranks[team["abbr"]] = index
    return ranks


def path_label(team: dict, ranks: dict[str, int], in_field: bool) -> str:
    if not in_field:
        return "Out"
    rank = ranks.get(team["abbr"]) or 99
    if rank <= 3:
        return f"{team['division']} {rank}"
    return "Wild card"


def gap_text(ahead: bool, points: int) -> str:
    if ahead:
        return "In" if points <= 0 else f"{points} up"
    return "0" if points == 0 else str(points)


def path_summary(leafs: dict, teams: list[dict]) -> dict:
    ranks = division_rank_map(teams)
    ordered_in, _ordered_out = playoff_field(teams)
    in_lookup = {team["abbr"] for team in ordered_in}
    atlantic = sorted(
        (team for team in teams if team.get("divisionAbbrev") == "A"),
        key=tie_key,
    )
    outsiders = sorted(
        (
            team for team in teams
            if team.get("conferenceAbbrev") == "E" and ranks.get(team["abbr"], 99) > 3
        ),
        key=tie_key,
    )

    def describe(contenders: list[dict], spots: int, title: str, empty_detail: str) -> dict:
        if not any(team["abbr"] == LEAF for team in contenders):
            return {
                "title": title,
                "in": True,
                "value": "In",
                "points": 0,
                "detail": empty_detail,
                "rival": None,
            }
        index = next(i for i, team in enumerate(contenders) if team["abbr"] == LEAF)
        if index < spots:
            rival = contenders[spots] if len(contenders) > spots else None
            cushion = (leafs["points"] - rival["points"]) if rival else leafs["points"]
            rival_name = rival["common"] if rival else "the field"
            return {
                "title": title,
                "in": True,
                "value": gap_text(True, cushion),
                "points": cushion,
                "detail": f"{cushion} points up on {rival_name}." if rival else "Every other club is behind.",
                "rival": rival["abbr"] if rival else None,
            }
        last_in = contenders[spots - 1]
        back = last_in["points"] - leafs["points"]
        return {
            "title": title,
            "in": False,
            "value": gap_text(False, back),
            "points": back,
            "detail": (
                f"{last_in['place']} holds the last spot on {last_in['points']} points. "
                f"Toronto is {back} back."
            ),
            "rival": last_in["abbr"],
            "rivalPoints": last_in["points"],
            "rivalName": last_in["common"],
        }

    division = describe(
        atlantic,
        3,
        "Atlantic top three",
        "Toronto is inside the Atlantic three, which is an automatic playoff berth.",
    )
    wildcard = describe(
        outsiders,
        2,
        "Eastern wild card",
        "A wild card is not required. Toronto is already inside its division's top three.",
    )
    if division["in"] or wildcard["in"]:
        easier = division if division["in"] else wildcard
        if division["in"] and wildcard["in"]:
            easier = division if division["points"] >= wildcard["points"] else wildcard
    else:
        easier = division if division["points"] <= wildcard["points"] else wildcard
    return {
        "division": division,
        "wildcard": wildcard,
        "easier": easier,
        "inField": LEAF in in_lookup,
        "ranks": ranks,
    }


def max_points(team: dict) -> int:
    return int(team["points"]) + 2 * int(team.get("gr") or 0)


def clinch_points(leafs: dict, rivals: list[dict], must_clear: int) -> int | None:
    if len(rivals) < must_clear:
        return None
    maxima = sorted(max_points(team) for team in rivals)
    threshold = maxima[must_clear - 1]
    return max(0, threshold + 1 - int(leafs["points"]))


def magic_payload(leafs: dict, teams: list[dict], season_over: bool, in_field: bool) -> dict:
    if (leafs.get("clinch") or "") in CLINCHED or (season_over and in_field):
        return {
            "kind": "clinched",
            "value": "IN",
            "label": "Playoff berth clinched",
            "sub": "Eastern Conference",
            "note": "Toronto is in. The remaining games are about seeding.",
        }
    east = [team for team in teams if team.get("conferenceAbbrev") == "E" and team["abbr"] != LEAF]
    atlantic = [team for team in east if team.get("divisionAbbrev") == "A"]
    division_need = clinch_points(leafs, atlantic, 5)
    conference_need = clinch_points(leafs, east, 8)
    options = [value for value in (division_need, conference_need) if value is not None]
    if not options:
        return {
            "kind": "pending",
            "value": "—",
            "label": "Magic number to clinch",
            "sub": "Points still to bank",
            "note": "A berth is a top-three Atlantic finish or one of the two Eastern wild cards.",
        }
    needed = min(options)
    reachable = 2 * int(leafs.get("gr") or 0)
    cap = max_points(leafs)
    teams_ahead = sum(1 for team in east if team["points"] > cap)
    if teams_ahead >= 8 or (leafs.get("clinch") == "e" and season_over):
        return {
            "kind": "eliminated",
            "value": "OUT",
            "label": "Mathematically eliminated",
            "sub": "No path back",
            "note": "Eight Eastern clubs already have more points than Toronto can reach.",
        }
    if needed == 0:
        return {
            "kind": "clinched",
            "value": "IN",
            "label": "Playoff berth clinched",
            "sub": "Eastern Conference",
            "note": "No remaining result can push eight Eastern teams past Toronto.",
        }
    if needed > reachable:
        return {
            "kind": "pending",
            "value": "—",
            "label": "Magic number to clinch",
            "sub": "Nobody has dropped enough points",
            "note": (
                "Every contender can still finish level with a Leafs team that wins out. "
                "The clinch number appears once rivals are capped below Toronto's maximum."
            ),
        }
    path = "Atlantic top three" if division_need == needed else "a wild card"
    other = conference_need if path.startswith("Atlantic") else division_need
    note = (
        f"{needed} more points guarantees {path}, no matter how the rest of the East finishes. "
        "A win is worth 2. An overtime loss still hands the other team a point."
    )
    if other is not None and other != needed:
        note += f" The other route needs {other}."
    return {
        "kind": "clinch",
        "value": str(needed),
        "label": "Magic number to clinch",
        "sub": f"Points to lock {path}",
        "note": note,
    }


def eliminated_now(leafs: dict, teams: list[dict], magic: dict) -> bool:
    if (leafs.get("clinch") or "") in CLINCHED or magic.get("kind") == "clinched":
        return False
    if magic.get("kind") == "eliminated":
        return True
    if leafs.get("clinch") == "e" and int(leafs.get("gr") or 0) == 0:
        return True
    return False


def strength_of(team: dict, prior: dict | None) -> float:
    prior_pct = None if not prior else prior.get("pointPct")
    if prior_pct is None and prior and prior.get("gp"):
        prior_pct = prior["points"] / (2 * prior["gp"])
    base = 0.5 if prior_pct is None else (0.7 * float(prior_pct) + 0.3 * 0.5)
    gp = int(team.get("gp") or 0)
    if gp <= 0 or team.get("pointPct") is None:
        return base
    weight = min(gp, 30) / 30
    return weight * float(team["pointPct"]) + (1 - weight) * base


def home_win_prob(home_strength: float, away_strength: float) -> float:
    sh = min(0.85, max(0.15, home_strength))
    sa = min(0.85, max(0.15, away_strength))
    denom = sh + sa - 2 * sh * sa
    prob = ((sh - sh * sa) / denom) if denom else 0.5
    return min(0.82, max(0.18, prob + HOME_BUMP))


def simulate(teams: list[dict], games: list[dict], strength: dict[str, float], seed: str) -> int:
    pending = [
        game for game in games
        if game["gameType"] == 2 and game["state"] not in FINAL_STATES
    ]
    if not pending:
        ordered_in, _out = playoff_field(teams)
        return 100 if any(team["abbr"] == LEAF for team in ordered_in) else 0
    rng = random.Random(int(hashlib.md5(seed.encode()).hexdigest()[:16], 16))
    index = {team["abbr"]: i for i, team in enumerate(teams)}
    base_pts = [int(team["points"]) for team in teams]
    base_rw = [int(team["rw"]) for team in teams]
    base_row = [int(team["row"]) for team in teams]
    base_wins = [int(team["wins"]) for team in teams]
    matchups = []
    for game in pending:
        home_i = index.get(game["home"])
        away_i = index.get(game["away"])
        if home_i is None or away_i is None:
            continue
        prob = home_win_prob(strength.get(game["home"], 0.5), strength.get(game["away"], 0.5))
        matchups.append((home_i, away_i, prob))
    east = [i for i, team in enumerate(teams) if team.get("conferenceAbbrev") == "E"]
    atlantic = [i for i, team in enumerate(teams) if team.get("divisionAbbrev") == "A"]
    metro = [i for i, team in enumerate(teams) if team.get("divisionAbbrev") == "M"]
    leafs_i = index[LEAF]
    hits = 0

    def key(slot: int, pts: list[int], rw: list[int], row: list[int], wins: list[int]) -> tuple:
        return (-pts[slot], -rw[slot], -row[slot], -wins[slot])

    for _ in range(SIMS):
        pts = base_pts[:]
        rw = base_rw[:]
        row = base_row[:]
        wins = base_wins[:]
        for home_i, away_i, prob in matchups:
            home_wins = rng.random() < prob
            extra = rng.random() < OT_RATE
            winner, loser = (home_i, away_i) if home_wins else (away_i, home_i)
            pts[winner] += 2
            wins[winner] += 1
            if extra:
                pts[loser] += 1
                row[winner] += 1
            else:
                rw[winner] += 1
                row[winner] += 1
        inside = set(sorted(atlantic, key=lambda slot: key(slot, pts, rw, row, wins))[:3])
        inside.update(sorted(metro, key=lambda slot: key(slot, pts, rw, row, wins))[:3])
        if leafs_i in inside:
            hits += 1
            continue
        rest = sorted((slot for slot in east if slot not in inside), key=lambda slot: key(slot, pts, rw, row, wins))
        if leafs_i in rest[:2]:
            hits += 1
    return round(100 * hits / SIMS)


def decorate(teams: list[dict], vs_leafs: dict[str, int]) -> list[dict]:
    ordered_in, ordered_out = playoff_field(teams)
    ranks = division_rank_map(teams)
    rows = []
    for group, inside in ((ordered_in, True), (ordered_out, False)):
        for team in group:
            row = dict(team)
            row["inField"] = inside
            row["path"] = path_label(team, ranks, inside)
            row["divisionRank"] = ranks.get(team["abbr"])
            row["vsLeafs"] = vs_leafs.get(team["abbr"], 0)
            row["isLeafs"] = team["abbr"] == LEAF
            rows.append(row)
    if rows:
        last_in = max((index for index, row in enumerate(rows) if row["inField"]), default=-1)
        if last_in >= 0:
            rows[last_in]["isCut"] = True
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
        row.setdefault("isCut", False)
    return rows


def signed(value: int | None) -> str:
    if value is None:
        return "—"
    return f"{value:+d}"


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    text = f"{float(value):.3f}"
    return text[1:] if text.startswith("0") else text


def game_view(game: dict, teams: dict[str, dict], strength: dict[str, float], leafs_games: list[dict]) -> dict:
    opp = game["away"] if game["home"] == LEAF else game["home"]
    opp_team = teams.get(opp) or {}
    home_prob = home_win_prob(strength.get(game["home"], 0.5), strength.get(game["away"], 0.5))
    leafs_prob = home_prob if game["home"] == LEAF else 1 - home_prob
    dates = [item["date"] for item in leafs_games if item["gameType"] == 2]
    back_to_back = False
    if game["date"] in dates:
        pos = dates.index(game["date"])
        if pos > 0:
            prev = datetime.fromisoformat(dates[pos - 1]).date()
            cur = datetime.fromisoformat(game["date"]).date()
            back_to_back = (cur - prev).days == 1
    return {
        "id": game["id"],
        "date": game["date"],
        "start": game["start"],
        "state": game["state"],
        "venue": game["venue"],
        "isHome": game["home"] == LEAF,
        "opponent": {
            "abbr": opp,
            "name": opp_team.get("name") or opp,
            "common": opp_team.get("common") or opp,
            "logo": (game["awayLogo"] if game["home"] == LEAF else game["homeLogo"]) or opp_team.get("logo") or "",
            "division": opp_team.get("division") or "",
            "pointPct": opp_team.get("pointPct"),
        },
        "leafsWinPct": round(leafs_prob * 100, 1),
        "homeWinPct": round(home_prob * 100, 1),
        "awayWinPct": round((1 - home_prob) * 100, 1),
        "homeAbbr": game["home"],
        "awayAbbr": game["away"],
        "homeScore": game["homeScore"],
        "awayScore": game["awayScore"],
        "ot": game["ot"],
        "backToBack": back_to_back,
        "divisionGame": opp_team.get("divisionAbbrev") == "A",
        "result": result_for(LEAF, game) if game["state"] in FINAL_STATES else None,
        "final": game["state"] in FINAL_STATES,
    }


def player_name(raw: dict) -> str:
    return f"{loc(raw.get('firstName'))} {loc(raw.get('lastName'))}".strip()


def toi_label(seconds: float | None) -> str:
    if not seconds:
        return "—"
    total = int(round(seconds))
    return f"{total // 60}:{total % 60:02d}"


def build_players(roster: dict, stats: dict, stats_label: str) -> dict:
    by_id: dict[int, dict] = {}
    for skater in stats.get("skaters") or []:
        by_id[int(skater["playerId"])] = skater
    goalie_stats = {int(goalie["playerId"]): goalie for goalie in stats.get("goalies") or []}

    def skater_row(player: dict) -> dict:
        stat = by_id.get(int(player["id"])) or {}
        gp = int(stat.get("gamesPlayed") or 0)
        points = int(stat.get("points") or 0) if stat else None
        return {
            "id": player.get("id"),
            "name": player_name(player),
            "position": player.get("positionCode") or stat.get("positionCode") or "",
            "headshot": player.get("headshot") or stat.get("headshot") or "",
            "gp": gp if stat else None,
            "goals": stat.get("goals") if stat else None,
            "assists": stat.get("assists") if stat else None,
            "points": points,
            "plusMinus": stat.get("plusMinus") if stat else None,
            "toi": toi_label(stat.get("avgTimeOnIcePerGame")) if stat else "—",
            "shots": stat.get("shots") if stat else None,
        }

    forwards = [skater_row(player) for player in roster.get("forwards") or []]
    defense = [skater_row(player) for player in roster.get("defensemen") or []]
    forwards.sort(key=lambda player: (-(player["points"] if player["points"] is not None else -1), player["name"]))
    defense.sort(key=lambda player: (-(player["points"] if player["points"] is not None else -1), player["name"]))
    goalies = []
    for player in roster.get("goalies") or []:
        stat = goalie_stats.get(int(player["id"])) or {}
        goalies.append(
            {
                "id": player.get("id"),
                "name": player_name(player),
                "headshot": player.get("headshot") or stat.get("headshot") or "",
                "gp": stat.get("gamesPlayed"),
                "wins": stat.get("wins"),
                "losses": stat.get("losses"),
                "otl": stat.get("overtimeLosses"),
                "sv": stat.get("savePercentage"),
                "gaa": stat.get("goalsAgainstAverage"),
                "so": stat.get("shutouts"),
            }
        )
    goalies.sort(key=lambda player: (-(player["gp"] or 0), player["name"]))
    played_forwards = [player for player in forwards if player["gp"]]
    played_defense = [player for player in defense if player["gp"]]
    return {
        "label": stats_label,
        "forwards": (played_forwards or forwards)[:12],
        "defense": (played_defense or defense)[:8],
        "goalies": goalies,
    }


def fmt_start(iso: str | None) -> str:
    if not iso:
        return ""
    stamp = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ)
    hour = stamp.strftime("%I").lstrip("0") or "12"
    return f"{stamp.strftime('%a, %b')} {stamp.day} · {hour}:{stamp.strftime('%M %p')}"


def write_payload(payload: dict) -> None:
    fresh = json.dumps({key: value for key, value in payload.items() if key != "generatedAt"}, sort_keys=True)
    if OUT_PATH.exists():
        try:
            old = json.loads(OUT_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            old = {}
        previous = json.dumps({key: value for key, value in old.items() if key != "generatedAt"}, sort_keys=True)
        if previous == fresh:
            print("No standings or schedule changes.")
            return
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


def main() -> None:
    now = toronto_now()
    today = now.date()
    target = target_season_id(now)
    prior_id = previous_season_id(target)
    label = season_label(target)
    prior_label = season_label(prior_id)

    standings_payload = fetch_json("https://api-web.nhle.com/v1/standings/now")
    standing_rows = standings_payload.get("standings") or []
    if not standing_rows:
        raise RuntimeError("NHL standings feed was empty")
    standings_season = int(standing_rows[0].get("seasonId") or 0)

    if standings_season == target:
        prior_schedule = fetch_json(f"https://api-web.nhle.com/v1/club-schedule-season/TOR/{prior_id}")
        prior_dates = [
            game.get("gameDate")
            for game in prior_schedule.get("games") or []
            if game.get("gameType") == 2 and game.get("gameDate")
        ]
        prior_rows = standing_rows
        if prior_dates:
            prior_payload = fetch_json(f"https://api-web.nhle.com/v1/standings/{max(prior_dates)}")
            if prior_payload.get("standings"):
                prior_rows = prior_payload["standings"]
        closing_games = collect_games({"TOR": prior_schedule})
    else:
        prior_rows = standing_rows
        prior_schedule = fetch_json(f"https://api-web.nhle.com/v1/club-schedule-season/TOR/{standings_season}")
        closing_games = collect_games({"TOR": prior_schedule})

    prior_teams = teams_from_rows(prior_rows, 82)
    prior_by_abbr = {team["abbr"]: team for team in prior_teams}
    abbrs = [team["abbr"] for team in prior_teams]

    def load_schedule(abbr: str) -> tuple[str, dict]:
        return abbr, fetch_json(f"https://api-web.nhle.com/v1/club-schedule-season/{abbr}/{target}")

    schedules: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for abbr, payload in pool.map(load_schedule, abbrs):
            schedules[abbr] = payload

    games = collect_games(schedules)
    leafs_schedule = [game for game in games if LEAF in (game["home"], game["away"])]
    regular = [game for game in leafs_schedule if game["gameType"] == 2]
    season_games = len(regular) or 82
    finals = [game for game in regular if game["state"] in FINAL_STATES and game["homeScore"] is not None]
    remaining_games = [game for game in regular if game["state"] not in FINAL_STATES]

    if standings_season == target and any(int(row.get("gamesPlayed") or 0) > 0 for row in standing_rows):
        current = teams_from_rows(standing_rows, season_games)
        by_abbr = {team["abbr"]: team for team in current}
        for team in current:
            left = sum(
                1
                for game in games
                if game["gameType"] == 2
                and game["state"] not in FINAL_STATES
                and team["abbr"] in (game["home"], game["away"])
            )
            team["gr"] = left
            team["seasonGames"] = season_games
            finish_rates(team, season_games)
        mode = "over" if not remaining_games else "live"
    elif finals:
        current = zero_teams(prior_teams, season_games)
        apply_results(current, games, season_games)
        mode = "over" if not remaining_games else "live"
    else:
        current = zero_teams(prior_teams, season_games)
        for team in current:
            team["gr"] = season_games
            team["maxPoints"] = 2 * season_games
        mode = "preview"

    current_by = {team["abbr"]: team for team in current}
    leafs_now = current_by[LEAF]
    shown_source = prior_teams if mode == "preview" else current
    shown_by = {team["abbr"]: team for team in shown_source}
    leafs_shown = shown_by[LEAF]

    vs_leafs: dict[str, int] = {}
    for game in remaining_games:
        other = game["away"] if game["home"] == LEAF else game["home"]
        vs_leafs[other] = vs_leafs.get(other, 0) + 1

    conference = decorate(shown_source, vs_leafs)
    atlantic = [row for row in conference if row["divisionAbbrev"] == "A"]
    atlantic.sort(key=lambda row: row.get("divisionRank") or 99)
    for row in atlantic:
        row["divisionCut"] = row.get("divisionRank") == 3
    leaders = []
    for division in ("Atlantic", "Metropolitan"):
        club = next((row for row in conference if row["division"] == division and row.get("divisionRank") == 1), None)
        if club:
            leaders.append(club)

    paths = path_summary(leafs_shown, shown_source)
    easier = paths["easier"]
    magic = magic_payload(leafs_now, current, mode == "over", paths["inField"] if mode != "preview" else False)
    eliminated = mode != "preview" and eliminated_now(leafs_now, current, magic)

    strength = {
        team["abbr"]: strength_of(team, prior_by_abbr.get(team["abbr"]))
        for team in current
    }
    odds_pct = simulate(current, games, strength, f"{target}-{today.isoformat()}")
    odds = {
        "percent": odds_pct,
        "sims": SIMS,
        "note": (
            "Each remaining game is simulated from points percentage, shrunk toward .500, "
            "with a home-ice bump. About 23% of games go past regulation and give the loser a point. "
            "Not a betting line."
        ),
    }
    if mode == "preview":
        odds["note"] = (
            "Full season, simulated from last year's points percentage shrunk toward .500, "
            "plus home ice, on this year's schedule. About 23% of games go past regulation. "
            "The number moves once this season's points replace last year's. Not a betting line."
        )

    opener_raw = remaining_games[0] if remaining_games else (regular[0] if regular else None)
    opener = None
    if opener_raw:
        opener_day = datetime.fromisoformat(opener_raw["date"]).date()
        opp = opener_raw["away"] if opener_raw["home"] == LEAF else opener_raw["home"]
        opener = {
            "date": opener_raw["date"],
            "start": opener_raw["start"],
            "label": fmt_start(opener_raw["start"]) or opener_raw["date"],
            "days": (opener_day - today).days,
            "isHome": opener_raw["home"] == LEAF,
            "opponent": opp,
            "opponentName": (current_by.get(opp) or prior_by_abbr.get(opp) or {}).get("place") or opp,
            "venue": opener_raw["venue"],
        }

    timeframe = prior_label if mode == "preview" else label
    if mode == "preview" and opener:
        days = opener["days"]
        when = "tonight" if days == 0 else "tomorrow" if days == 1 else f"in {days} days"
        where = "at home against" if opener["isHome"] else "at"
        if paths["inField"]:
            last = f"Last spring they were in, {easier['value']} on the {easier['title'].lower()}."
        else:
            last = (
                f"Last spring they finished {easier['points']} points back of the easier route in, "
                f"the {easier['title']}."
            )
        narrative = {
            "status": "preview",
            "kicker": f"{label} opens {opener['label']}",
            "headline": f"Puck drop {when}",
            "blurb": (
                f"The Leafs open {where} {opener['opponentName']} on {opener['label']}. "
                f"A full-season simulation gives Toronto a {odds_pct}% chance to still be playing in April. "
                f"{last}"
            ),
        }
        meters = {
            "primary": {
                "label": "Points back last spring",
                "value": easier["value"],
                "sub": easier["title"],
                "note": easier["detail"],
                "heatLabel": f"{prior_label} points rate",
                "heat": round(float(leafs_shown["pointPct"] or 0) * 100),
                "heatText": fmt_pct(leafs_shown["pointPct"]),
            },
            "third": {
                "label": "Days to opening night",
                "value": str(max(days, 0)),
                "sub": opener["label"],
                "note": "Exhibition games do not count. The standings start at zero on opening night.",
            },
        }
    elif eliminated:
        narrative = {
            "status": "eliminated",
            "kicker": f"{label} playoff race",
            "headline": "See ya next season",
            "blurb": "The Toronto Maple Leafs have been mathematically eliminated from the Stanley Cup playoffs.",
        }
        meters = {
            "primary": {
                "label": "Points back of the cut line",
                "value": "OUT",
                "sub": leafs_shown["record"],
                "note": "Eight Eastern clubs are out of reach.",
                "heatLabel": "Last 10 points rate",
                "heat": round(100 * (leafs_shown["l10Points"] or 0) / 20),
                "heatText": f"{leafs_shown['l10Points'] or 0}/20",
            },
            "third": magic,
        }
    elif paths["inField"]:
        narrative = {
            "status": "in",
            "kicker": "Holding a playoff spot",
            "headline": "In the field",
            "blurb": (
                f"Toronto is in through the {easier['title'].lower()}. "
                f"The cushion is {easier['value']}. Every remaining point is about staying there."
            ),
        }
        meters = {
            "primary": {
                "label": "Points up on the cut line",
                "value": easier["value"],
                "sub": easier["title"],
                "note": easier["detail"],
                "heatLabel": "Last 10 points rate",
                "heat": round(100 * (leafs_shown["l10Points"] or 0) / 20),
                "heatText": f"{leafs_shown['l10Points'] or 0}/20",
            },
            "third": magic,
        }
    else:
        gap = easier["points"]
        if gap <= 4:
            headline, status = "Right on the cut line", "chasing"
        elif gap <= 10:
            headline, status = "Still in the hunt", "hunting"
        else:
            headline, status = "Long way back", "longshot"
        narrative = {
            "status": status,
            "kicker": "Eastern Conference chase",
            "headline": headline,
            "blurb": (
                f"Toronto is {gap} points back of the {easier['title']}, the easier of the two routes in. "
                f"The model has them at {odds_pct}% to make it."
            ),
        }
        meters = {
            "primary": {
                "label": "Points back of the easier path",
                "value": easier["value"],
                "sub": easier["title"],
                "note": easier["detail"],
                "heatLabel": "Last 10 points rate",
                "heat": round(100 * (leafs_shown["l10Points"] or 0) / 20),
                "heatText": f"{leafs_shown['l10Points'] or 0}/20",
            },
            "third": magic,
        }

    if mode == "live" and leafs_shown["streak"].startswith("W") and narrative["status"] in {"chasing", "hunting"}:
        narrative["blurb"] += f" They are on a {leafs_shown['streak']} run."

    strength_bits = []
    division_left = 0
    conference_left = 0
    home_left = 0
    for game in remaining_games:
        opp = game["away"] if game["home"] == LEAF else game["home"]
        strength_bits.append(strength.get(opp, 0.5))
        opp_team = current_by.get(opp) or {}
        if opp_team.get("divisionAbbrev") == "A":
            division_left += 1
        if opp_team.get("conferenceAbbrev") == "E":
            conference_left += 1
        if game["home"] == LEAF:
            home_left += 1
    dates = [datetime.fromisoformat(game["date"]).date() for game in remaining_games]
    back_to_backs = sum(1 for prev, cur in zip(dates, dates[1:]) if (cur - prev).days == 1)
    sos = round(sum(strength_bits) / len(strength_bits), 3) if strength_bits else None

    focus_games = [game for game in leafs_schedule if game["gameType"] == 2]
    upcoming = [game_view(game, shown_by, strength, focus_games) for game in remaining_games[:12]]
    if mode == "preview":
        recent_source = [
            game for game in closing_games
            if game["gameType"] == 2 and game["state"] in FINAL_STATES and LEAF in (game["home"], game["away"])
        ][-8:]
        recent_teams = prior_by_abbr
    else:
        recent_source = finals[-8:]
        recent_teams = current_by
    recent = [game_view(game, recent_teams, strength, recent_source) for game in recent_source]
    preseason = [
        game_view(game, current_by, strength, leafs_schedule)
        for game in leafs_schedule
        if game["gameType"] == 1
    ]

    rooting = []
    for game in remaining_games[:6]:
        view = game_view(game, shown_by, strength, focus_games)
        view["interest"] = "Leafs game"
        view["note"] = (
            f"A win banks 2 points. An overtime loss still salvages 1. "
            f"Model has Toronto at {view['leafsWinPct']}%."
        )
        view["wantWinner"] = LEAF
        rooting.append(view)

    roster = fetch_json(f"https://api-web.nhle.com/v1/roster/TOR/{target}")
    current_stats = fetch_json(f"https://api-web.nhle.com/v1/club-stats/TOR/{target}/2")
    if (current_stats.get("skaters") or current_stats.get("goalies")):
        players = build_players(roster, current_stats, f"{label} regular season")
    else:
        prior_stats = fetch_json(f"https://api-web.nhle.com/v1/club-stats/TOR/{prior_id}/2")
        players = build_players(
            roster,
            prior_stats,
            f"{prior_label} numbers in a Toronto jersey. They reset once the regular season starts.",
        )

    chips = [
        {"label": "Record", "value": leafs_shown["record"]},
        {"label": "Points", "value": str(leafs_shown["points"])},
        {"label": "RW", "value": str(leafs_shown["rw"])},
        {"label": "Diff", "value": signed(leafs_shown["diff"])},
    ]
    if mode == "preview":
        chips = [
            {"label": "Last year", "value": leafs_shown["record"]},
            {"label": "Points", "value": str(leafs_shown["points"])},
            {"label": "Reg. wins", "value": str(leafs_shown["rw"])},
            {"label": "Diff", "value": signed(leafs_shown["diff"])},
        ]

    pace_value = "—" if leafs_shown["pace"] is None else str(leafs_shown["pace"])
    kpis = [
        {
            "label": "Playoff odds",
            "value": f"{odds_pct}%",
            "hint": f"{SIMS:,} season sims",
            "stat": "Odds",
        },
        {
            "label": "Easier path",
            "value": easier["value"],
            "hint": easier["title"],
            "stat": "Path",
        },
        {
            "label": "Regulation wins",
            "value": str(leafs_shown["rw"]),
            "hint": "First tiebreaker after points",
            "stat": "RW",
        },
        {
            "label": "Goal diff",
            "value": signed(leafs_shown["diff"]),
            "hint": f"Expected points {leafs_shown['xpts'] if leafs_shown['xpts'] is not None else '—'}",
            "stat": "Diff",
        },
        {
            "label": "Games left",
            "value": str(len(remaining_games)),
            "hint": f"{home_left} home · {len(remaining_games) - home_left} road",
            "stat": "GR",
        },
        {
            "label": "Point pace",
            "value": pace_value,
            "hint": (
                f"Points rate stretched over {season_games} games"
                if mode != "preview"
                else f"{prior_label} finish, not a forecast"
            ),
            "stat": "Pace",
        },
        {
            "label": "ROW",
            "value": str(leafs_shown["row"]),
            "hint": "Regulation plus overtime wins. Shootout wins do not count.",
            "stat": "ROW",
        },
        {
            "label": "Schedule",
            "value": fmt_pct(sos),
            "hint": "Average opponent strength still on the board",
            "stat": "SOS",
        },
    ]

    if mode == "preview":
        home_gap = leafs_shown["homePoints"] - leafs_shown["roadPoints"]
        trends = [
            {
                "label": "Wild-card gap",
                "value": paths["wildcard"]["value"],
                "detail": paths["wildcard"]["detail"],
                "direction": "down" if not paths["wildcard"]["in"] else "up",
                "stat": "WC",
            },
            {
                "label": "Atlantic gap",
                "value": paths["division"]["value"],
                "detail": paths["division"]["detail"],
                "direction": "down" if not paths["division"]["in"] else "up",
                "stat": "Path",
            },
            {
                "label": "Home points",
                "value": str(leafs_shown["homePoints"]),
                "detail": f"Home record {leafs_shown['home']}",
                "direction": "up" if home_gap > 0 else "down",
            },
            {
                "label": "Road points",
                "value": str(leafs_shown["roadPoints"]),
                "detail": f"Road record {leafs_shown['road']}",
                "direction": "down" if home_gap > 0 else "up",
            },
            {
                "label": "Last 10 points",
                "value": "—" if leafs_shown["l10Points"] is None else str(leafs_shown["l10Points"]),
                "detail": f"{leafs_shown['l10']} to close the year",
                "direction": "down" if (leafs_shown["l10Points"] or 0) < 10 else "up",
                "stat": "L10",
            },
            {
                "label": "Shootout wins",
                "value": str(leafs_shown["soWins"]),
                "detail": f"{leafs_shown['otWins']} overtime wins sat in ROW. Shootouts did not.",
                "direction": "flat",
                "stat": "SO",
            },
        ]
    else:
        heat = leafs_shown["l10Points"] or 0
        trends = [
            {
                "label": "Last 10 points",
                "value": str(heat),
                "detail": f"{leafs_shown['l10']} · {heat} of a possible 20",
                "direction": "up" if heat >= 12 else "down" if heat < 8 else "flat",
                "stat": "L10",
            },
            {
                "label": "Streak",
                "value": leafs_shown["streak"],
                "detail": "Current run",
                "direction": "up" if leafs_shown["streak"].startswith("W") else "down" if leafs_shown["streak"].startswith("L") else "flat",
            },
            {
                "label": "Point pace",
                "value": pace_value,
                "detail": f"Max still available: {leafs_now['maxPoints']}",
                "direction": "up" if (leafs_shown["pace"] or 0) >= 96 else "down" if leafs_shown["pace"] else "flat",
                "stat": "Pace",
            },
            {
                "label": "Expected points",
                "value": "—" if leafs_shown["xpts"] is None else str(leafs_shown["xpts"]),
                "detail": "What the goal differential says they should have",
                "direction": "up" if (leafs_shown["xpts"] or 0) > leafs_shown["points"] else "down",
                "stat": "xPTS",
            },
            {
                "label": "Home points",
                "value": str(leafs_shown["homePoints"]),
                "detail": leafs_shown["home"],
                "direction": "flat",
            },
            {
                "label": "Road points",
                "value": str(leafs_shown["roadPoints"]),
                "detail": leafs_shown["road"],
                "direction": "flat",
            },
        ]

    compare = [row for row in atlantic]
    rival_abbr = easier.get("rival")
    if rival_abbr and not any(row["abbr"] == rival_abbr for row in compare):
        extra = next((row for row in conference if row["abbr"] == rival_abbr), None)
        if extra:
            compare.append(extra)

    tiebreak = {
        "rw": leafs_shown["rw"],
        "row": leafs_shown["row"],
        "otWins": leafs_shown["otWins"],
        "soWins": leafs_shown["soWins"],
        "otl": leafs_shown["otl"],
        "wins": leafs_shown["wins"],
        "timeframe": timeframe,
        "detail": (
            f"In {timeframe} Toronto had {leafs_shown['wins']} wins, but only {leafs_shown['rw']} came in regulation. "
            f"{leafs_shown['otWins']} overtime wins count toward ROW. "
            f"{leafs_shown['soWins']} shootout {'win does' if leafs_shown['soWins'] == 1 else 'wins do'} not. "
            f"{leafs_shown['otl']} overtime losses salvaged a point each."
        ),
    }

    ticker = [
        f"TORONTO MAPLE LEAFS {leafs_shown['record']}",
        f"{leafs_shown['points']} PTS · {fmt_pct(leafs_shown['pointPct'])}",
        f"PLAYOFF ODDS {odds_pct}%",
        f"EASIER PATH {easier['value']}",
        f"{len(remaining_games)} GAMES LEFT",
        narrative["headline"],
    ]
    if mode == "preview":
        ticker.insert(0, f"{prior_label} FINISH")
        ticker.append("PRESEASON DOES NOT COUNT")
    elif eliminated:
        ticker.append("MATHEMATICALLY ELIMINATED")
    else:
        ticker.append("THE PUSH IS ON")

    table_blurb = (
        f"{prior_label} final standings. The {label} board is zeros until opening night. "
        "Top three in each division are in. Two wild cards join them."
        if mode == "preview"
        else "Top three in the Atlantic and the Metropolitan are in. The next two Eastern clubs are the wild cards."
    )
    compare_title = f"{timeframe} in the Atlantic" if mode == "preview" else "Teams on the Atlantic board"
    recent_blurb = (
        f"How {prior_label} ended. None of this carries over."
        if mode == "preview"
        else "The stretch that moved the points column."
    )

    payload = {
        "generatedAt": now.isoformat(),
        "season": label,
        "seasonId": target,
        "mode": mode,
        "timeframe": timeframe,
        "seasonGames": season_games,
        "source": "NHL API",
        "eliminated": eliminated,
        "narrative": narrative,
        "meters": meters,
        "playoffOdds": odds,
        "magicNumber": magic,
        "leafs": {
            "abbr": LEAF,
            "name": leafs_shown["name"],
            "logo": leafs_shown["logo"],
            "record": leafs_shown["record"],
            "points": leafs_shown["points"],
            "pointPct": leafs_shown["pointPct"],
            "streak": leafs_shown["streak"],
            "l10": leafs_shown["l10"],
            "diff": leafs_shown["diff"],
            "divisionRank": paths["ranks"].get(LEAF),
            "inField": paths["inField"],
            "gamesRemaining": len(remaining_games),
        },
        "chips": chips,
        "kpis": kpis,
        "trends": trends,
        "paths": {"division": paths["division"], "wildcard": paths["wildcard"]},
        "conference": conference,
        "atlantic": atlantic,
        "leaders": [
            {
                "name": team["name"],
                "abbr": team["abbr"],
                "logo": team["logo"],
                "division": team["division"],
                "record": team["record"],
                "points": team["points"],
                "pointPct": team["pointPct"],
            }
            for team in leaders
        ],
        "compare": compare,
        "compareTitle": compare_title,
        "tableBlurb": table_blurb,
        "schedule": upcoming,
        "remaining": {
            "games": len(remaining_games),
            "home": home_left,
            "away": len(remaining_games) - home_left,
            "division": division_left,
            "conference": conference_left,
            "backToBacks": back_to_backs,
            "sos": sos,
        },
        "recent": recent,
        "recentBlurb": recent_blurb,
        "preseason": preseason,
        "rooting": rooting,
        "tiebreak": tiebreak,
        "players": players,
        "opener": opener,
        "ticker": ticker,
        "legend": {
            "in": "Made it last spring" if mode == "preview" else "In a playoff spot",
            "out": "Missed" if mode == "preview" else "Outside",
            "leafs": "Toronto",
        },
    }
    write_payload(payload)
    print(
        f"{mode} {label}  odds {odds_pct}%  "
        f"shown {leafs_shown['record']} {leafs_shown['points']} pts  "
        f"path {easier['value']}  left {len(remaining_games)}"
    )


if __name__ == "__main__":
    main()
