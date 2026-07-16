"""
fetch_data.py
Descarga partidos próximos, cuotas promedio y forma reciente de:
  - Mundial 2026        (API-Football)
  - Liga MX              (API-Football)
  - UEFA Champions League (API-Football)
  - NBA                  (API-Basketball)

Guarda todo en data/raw_snapshot.json para que generate_predictions.py
lo procese después.

Requiere la variable de entorno API_FOOTBALL_KEY (secret de GitHub).
La misma key sirve para api-football y api-basketball (cuenta api-sports.io),
pero debes tener el plan gratuito activado para CADA producto por separado
en tu dashboard de https://dashboard.api-football.com/
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone

API_KEY = os.environ.get("API_FOOTBALL_KEY")
if not API_KEY:
    print("ERROR: falta la variable de entorno API_FOOTBALL_KEY")
    sys.exit(1)

FOOTBALL_BASE = "https://v3.football.api-sports.io"
BASKETBALL_BASE = "https://v1.basketball.api-sports.io"

FOOTBALL_HEADERS = {"x-apisports-key": API_KEY}
BASKETBALL_HEADERS = {"x-apisports-key": API_KEY}

# Nombres a buscar. El script resuelve el league_id Y la temporada actual
# automáticamente, para no depender de números que cambian cada año.
FOOTBALL_LEAGUES = {
    "mundial_2026": "FIFA World Cup",
    "liga_mx": "Liga MX",
    "champions_league": "UEFA Champions League",
}

# Sufijos que indican que NO es la liga principal (categorías juveniles/femeniles)
EXCLUDE_SUFFIXES = ("u17", "u20", "u21", "u23", "women", "femenil", "youth")

REQUEST_DELAY = 1.2  # segundos entre llamadas para no pegarle al rate limit


def _get(base, path, headers, params=None):
    url = f"{base}{path}"
    resp = requests.get(url, headers=headers, params=params or {}, timeout=20)
    time.sleep(REQUEST_DELAY)
    if resp.status_code != 200:
        print(f"WARN: {url} -> HTTP {resp.status_code}: {resp.text[:200]}")
        return {}
    data = resp.json()
    if data.get("errors"):
        print(f"WARN: {url} -> errors de la API: {data['errors']}")
    return data


def _is_main_league(name):
    lname = name.lower()
    return not any(suf in lname for suf in EXCLUDE_SUFFIXES)


def find_league_and_season(name):
    """Busca la liga por nombre y devuelve (league_id, season_year) usando
    la temporada marcada como 'current' en la respuesta de la API."""
    data = _get(FOOTBALL_BASE, "/leagues", FOOTBALL_HEADERS, {"search": name})
    resp = data.get("response", [])
    if not resp:
        print(f"WARN: no se encontró liga '{name}'")
        return None, None

    candidates = [r for r in resp if _is_main_league(r["league"]["name"])]
    if not candidates:
        candidates = resp

    exact = [r for r in candidates if r["league"]["name"].lower() == name.lower()]
    chosen = exact[0] if exact else candidates[0]

    league_id = chosen["league"]["id"]
    league_name_found = chosen["league"]["name"]

    current_season = None
    for s in chosen.get("seasons", []):
        if s.get("current"):
            current_season = s["year"]
            break
    if current_season is None and chosen.get("seasons"):
        current_season = max(s["year"] for s in chosen["seasons"])

    if current_season is None:
        print(f"WARN: '{league_name_found}' (id {league_id}) no tiene temporadas listadas")
        return league_id, None

    print(f"Liga encontrada: {league_name_found} (id {league_id}), temporada actual: {current_season}")
    return league_id, current_season


def get_upcoming_fixtures(league_id, season, next_n=6):
    data = _get(FOOTBALL_BASE, "/fixtures", FOOTBALL_HEADERS,
                {"league": league_id, "season": season, "next": next_n})
    return data.get("response", [])


def get_average_odds(fixture_id):
    """Devuelve cuotas promedio para Match Winner y Over/Under 2.5."""
    data = _get(FOOTBALL_BASE, "/odds", FOOTBALL_HEADERS,
                {"fixture": fixture_id})
    resp = data.get("response", [])
    if not resp:
        return None

    match_winner_odds = []  # lista de [home, draw, away] por casa
    over_under_odds = []    # lista de [over, under] por casa

    for bookmaker_block in resp[0].get("bookmakers", []):
        for bet in bookmaker_block.get("bets", []):
            if bet["name"] == "Match Winner":
                vals = {v["value"]: float(v["odd"]) for v in bet["values"]}
                if all(k in vals for k in ("Home", "Draw", "Away")):
                    match_winner_odds.append(vals)
            elif bet["name"] == "Goals Over/Under" :
                for v in bet["values"]:
                    if v["value"] in ("Over 2.5", "Under 2.5"):
                        over_under_odds.append(v)

    def avg(key, records):
        vals = [r[key] for r in records if key in r]
        return round(sum(vals) / len(vals), 2) if vals else None

    result = {}
    if match_winner_odds:
        result["home"] = avg("Home", match_winner_odds)
        result["draw"] = avg("Draw", match_winner_odds)
        result["away"] = avg("Away", match_winner_odds)

    over_vals = [float(v["odd"]) for v in over_under_odds if v["value"] == "Over 2.5"]
    under_vals = [float(v["odd"]) for v in over_under_odds if v["value"] == "Under 2.5"]
    if over_vals:
        result["over_2_5"] = round(sum(over_vals) / len(over_vals), 2)
    if under_vals:
        result["under_2_5"] = round(sum(under_vals) / len(under_vals), 2)

    return result or None


def get_team_form(team_id, season, last_n=5):
    """Puntos de forma: W=3, D=1, L=0, normalizado 0-1."""
    data = _get(FOOTBALL_BASE, "/fixtures", FOOTBALL_HEADERS,
                {"team": team_id, "season": season, "last": last_n})
    resp = data.get("response", [])
    if not resp:
        return None
    points = 0
    for f in resp:
        goals = f.get("goals", {})
        home_id = f["teams"]["home"]["id"]
        is_home = home_id == team_id
        gh, ga = goals.get("home"), goals.get("away")
        if gh is None or ga is None:
            continue
        team_goals = gh if is_home else ga
        opp_goals = ga if is_home else gh
        if team_goals > opp_goals:
            points += 3
        elif team_goals == opp_goals:
            points += 1
    max_points = 3 * len(resp)
    return round(points / max_points, 3) if max_points else None


def fetch_football_snapshot():
    snapshot = {}
    for key, name in FOOTBALL_LEAGUES.items():
        print(f"Buscando liga: {name}")
        league_id, season = find_league_and_season(name)
        if not league_id or not season:
            snapshot[key] = {"league_name": name, "matches": []}
            continue

        fixtures = get_upcoming_fixtures(league_id, season)
        if not fixtures:
            print(f"  sin fixtures 'next' para {name} temporada {season} (puede que el plan free no cubra fixtures futuros de esta liga)")
        matches = []
        for fx in fixtures:
            fixture_id = fx["fixture"]["id"]
            home = fx["teams"]["home"]
            away = fx["teams"]["away"]

            odds = get_average_odds(fixture_id)
            home_form = get_team_form(home["id"], season)
            away_form = get_team_form(away["id"], season)

            matches.append({
                "fixture_id": fixture_id,
                "date_utc": fx["fixture"]["date"],
                "home_team": home["name"],
                "away_team": away["name"],
                "odds": odds,
                "home_form": home_form,
                "away_form": away_form,
            })

        snapshot[key] = {"league_name": name, "matches": matches}
    return snapshot


def fetch_nba_snapshot():
    print("Buscando NBA en API-Basketball...")
    data = _get(BASKETBALL_BASE, "/leagues", BASKETBALL_HEADERS, {"search": "NBA"})
    resp = data.get("response", [])
    if not resp:
        print("WARN: no se encontró la NBA (¿activaste el plan de API-Basketball?)")
        return {"league_name": "NBA", "matches": []}
    league_id = resp[0]["id"]

    # API-Basketball devuelve la lista de temporadas como strings (ej "2024-2025").
    # Tomamos la última (más reciente) en vez de un valor fijo.
    seasons = resp[0].get("seasons", [])
    nba_season = seasons[-1] if seasons else None
    if not nba_season:
        print("WARN: la liga NBA no trae temporadas listadas")
        return {"league_name": "NBA", "matches": []}
    print(f"NBA encontrada (id {league_id}), temporada usada: {nba_season}")

    games_data = _get(BASKETBALL_BASE, "/games", BASKETBALL_HEADERS,
                       {"league": league_id, "season": nba_season, "next": 6})
    games = games_data.get("response", [])

    matches = []
    for g in games:
        game_id = g["id"]
        home = g["teams"]["home"]["name"]
        away = g["teams"]["away"]["name"]

        odds_data = _get(BASKETBALL_BASE, "/odds", BASKETBALL_HEADERS, {"game": game_id})
        odds = None
        odds_resp = odds_data.get("response", [])
        if odds_resp:
            for bookmaker in odds_resp[0].get("bookmakers", []):
                for bet in bookmaker.get("bets", []):
                    if bet["name"].lower() in ("home/away", "moneyline"):
                        vals = {v["value"]: float(v["odd"]) for v in bet["values"]}
                        odds = vals
                        break
                if odds:
                    break

        matches.append({
            "game_id": game_id,
            "date_utc": g["date"],
            "home_team": home,
            "away_team": away,
            "odds": odds,
        })

    return {"league_name": "NBA", "matches": matches}


def main():
    snapshot = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "football": fetch_football_snapshot(),
        "nba": fetch_nba_snapshot(),
    }

    os.makedirs("data", exist_ok=True)
    with open("data/raw_snapshot.json", "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

    print("Listo: data/raw_snapshot.json")


if __name__ == "__main__":
    main()
