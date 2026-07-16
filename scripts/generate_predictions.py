"""
generate_predictions.py
Toma data/raw_snapshot.json y genera data/snapshot.json con:
  - probabilidad de modelo por partido (cuota promedio + forma reciente)
  - "value" = probabilidad de modelo - probabilidad implícita de mercado
  - parlay "seguro"    (mayor confianza, máximo 1 pata por partido)
  - parlay "arriesgado" (mayor value, no necesariamente mayor confianza)
  - "No bet" si ningún partido cumple el mínimo de valor/confianza

Este es un modelo ESTADÍSTICO simple (v1), no usa IA todavía.
Pensado para poder reemplazar `build_model_probs()` más adelante por un
consenso multi-modelo sin tocar el resto del pipeline.
"""

import json
import hashlib
from datetime import datetime, timezone

RAW_PATH = "data/raw_snapshot.json"
OUT_PATH = "data/snapshot.json"

ENGINE_VERSION = "stats-v1"

# Pesos del blend: cuánto pesa la cuota de mercado vs. la forma reciente
WEIGHT_ODDS = 0.65
WEIGHT_FORM = 0.35

# Umbrales para entrar a cada parlay
MIN_CONFIDENCE_SAFE = 0.55
MIN_EDGE_RISKY = 0.05
MIN_CONFIDENCE_RISKY = 0.35

MAX_LEGS_SAFE = 4
MAX_LEGS_RISKY = 4


def implied_prob(odds):
    return 1.0 / odds if odds else 0.0


def normalize(probs):
    total = sum(probs.values())
    if total <= 0:
        return probs
    return {k: v / total for k, v in probs.items()}


def football_match_probs(match):
    odds = match.get("odds") or {}
    home_form = match.get("home_form")
    away_form = match.get("away_form")

    legs = []

    # --- Mercado 1X2 ---
    if all(k in odds for k in ("home", "draw", "away")):
        implied = normalize({
            "Home": implied_prob(odds["home"]),
            "Draw": implied_prob(odds["draw"]),
            "Away": implied_prob(odds["away"]),
        })

        if home_form is not None and away_form is not None:
            total_form = home_form + away_form
            if total_form > 0:
                form_probs = {
                    "Home": home_form / total_form,
                    "Away": away_form / total_form,
                    "Draw": 0.0,
                }
            else:
                form_probs = {"Home": 0.33, "Draw": 0.34, "Away": 0.33}
        else:
            form_probs = implied  # sin forma, no ajusta

        blended = {}
        for k in ("Home", "Draw", "Away"):
            blended[k] = WEIGHT_ODDS * implied[k] + WEIGHT_FORM * form_probs.get(k, 0.0)
        blended = normalize(blended)

        best_pick = max(blended, key=blended.get)
        legs.append({
            "market": "Match Winner",
            "pick": best_pick,
            "model_prob": round(blended[best_pick], 3),
            "market_prob": round(implied[best_pick], 3),
            "edge": round(blended[best_pick] - implied[best_pick], 3),
            "odds_used": odds.get({"Home": "home", "Draw": "draw", "Away": "away"}[best_pick]),
        })

    # --- Mercado Over/Under 2.5 ---
    if "over_2_5" in odds and "under_2_5" in odds:
        implied = normalize({
            "Over 2.5": implied_prob(odds["over_2_5"]),
            "Under 2.5": implied_prob(odds["under_2_5"]),
        })
        # sin dato de goles esperados propio, se deja el mercado como proxy del modelo
        # (mejora futura: usar promedio de goles anotados/recibidos por equipo)
        best_pick = max(implied, key=implied.get)
        legs.append({
            "market": "Goals Over/Under",
            "pick": best_pick,
            "model_prob": round(implied[best_pick], 3),
            "market_prob": round(implied[best_pick], 3),
            "edge": 0.0,
            "odds_used": odds.get("over_2_5" if best_pick == "Over 2.5" else "under_2_5"),
        })

    return legs


def nba_match_probs(match):
    odds = match.get("odds") or {}
    legs = []
    home_key = next((k for k in odds if k.lower() in ("home", match["home_team"].lower())), None)
    away_key = next((k for k in odds if k.lower() in ("away", match["away_team"].lower())), None)

    if home_key and away_key:
        implied = normalize({
            "Home": implied_prob(odds[home_key]),
            "Away": implied_prob(odds[away_key]),
        })
        best_pick = max(implied, key=implied.get)
        legs.append({
            "market": "Moneyline",
            "pick": best_pick,
            "model_prob": round(implied[best_pick], 3),
            "market_prob": round(implied[best_pick], 3),
            "edge": 0.0,
            "odds_used": odds[home_key if best_pick == "Home" else away_key],
        })
    return legs


def build_all_legs(raw):
    all_legs = []

    for league_key, league_data in raw.get("football", {}).items():
        for match in league_data.get("matches", []):
            for leg in football_match_probs(match):
                all_legs.append({
                    "league": league_data["league_name"],
                    "match": f"{match['home_team']} vs {match['away_team']}",
                    "date_utc": match["date_utc"],
                    "ref_id": match["fixture_id"],
                    **leg,
                })

    for match in raw.get("nba", {}).get("matches", []):
        for leg in nba_match_probs(match):
            all_legs.append({
                "league": "NBA",
                "match": f"{match['home_team']} vs {match['away_team']}",
                "date_utc": match["date_utc"],
                "ref_id": match["game_id"],
                **leg,
            })

    return all_legs


def build_parlay(legs, min_confidence=None, min_edge=None, max_legs=4, sort_by="model_prob"):
    candidates = [l for l in legs if l["odds_used"]]
    if min_confidence is not None:
        candidates = [l for l in candidates if l["model_prob"] >= min_confidence]
    if min_edge is not None:
        candidates = [l for l in candidates if l["edge"] >= min_edge]

    candidates.sort(key=lambda l: l[sort_by], reverse=True)

    chosen = []
    used_matches = set()
    for leg in candidates:
        match_key = (leg["league"], leg["match"])
        if match_key in used_matches:
            continue  # máximo una pata por partido, igual que mtzbets
        chosen.append(leg)
        used_matches.add(match_key)
        if len(chosen) >= max_legs:
            break

    if not chosen:
        return {"status": "no_bet", "legs": [], "combined_odds": None, "combined_prob": None}

    combined_odds = 1.0
    combined_prob = 1.0
    for leg in chosen:
        combined_odds *= leg["odds_used"]
        combined_prob *= leg["model_prob"]

    return {
        "status": "ok",
        "legs": chosen,
        "combined_odds": round(combined_odds, 2),
        "combined_prob": round(combined_prob, 3),
    }


def main():
    with open(RAW_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    all_legs = build_all_legs(raw)

    safe_parlay = build_parlay(
        all_legs, min_confidence=MIN_CONFIDENCE_SAFE, max_legs=MAX_LEGS_SAFE, sort_by="model_prob"
    )
    risky_parlay = build_parlay(
        all_legs, min_confidence=MIN_CONFIDENCE_RISKY, min_edge=MIN_EDGE_RISKY,
        max_legs=MAX_LEGS_RISKY, sort_by="edge"
    )

    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "engine_version": ENGINE_VERSION,
        "leagues": {
            "football": raw.get("football", {}),
            "nba": raw.get("nba", {}),
        },
        "all_legs": all_legs,
        "parlay_seguro": safe_parlay,
        "parlay_arriesgado": risky_parlay,
        "disclaimer": (
            "Contenido informativo de research deportivo. No es asesoria "
            "financiera ni garantiza resultados. Solo para mayores de 18 anos. "
            "Juega con responsabilidad. La ultima decision es tuya."
        ),
    }

    content_for_hash = json.dumps(output, sort_keys=True, ensure_ascii=False)
    output["snapshot_hash"] = hashlib.sha256(content_for_hash.encode("utf-8")).hexdigest()[:12]

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Listo: {OUT_PATH} (hash {output['snapshot_hash']})")


if __name__ == "__main__":
    main()
