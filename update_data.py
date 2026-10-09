
import os
import sys
from datetime import datetime, timezone

import requests

NHL_API = "https://api-web.nhle.com/v1/schedule/now"

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", ""
).rstrip("/")

SUPABASE_KEY = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY", ""
)


def get_nhl_games():
    response = requests.get(
        NHL_API,
        timeout=30
    )
    response.raise_for_status()

    data = response.json()
    games = []

    for day in data.get("gameWeek", []):
        for game in day.get("games", []):
            game_id = game.get("id")

            if game_id is None:
                continue

            games.append({
                "league": "NHL",
                "game_id": str(game_id),
                "game_date": game.get("gameDate"),
                "start_utc": game.get("startTimeUTC"),
                "home_team": game.get(
                    "homeTeam", {}
                ).get("abbrev"),
                "away_team": game.get(
                    "awayTeam", {}
                ).get("abbrev"),
                "game_state": game.get("gameState"),
                "updated_at": datetime.now(
                    timezone.utc
                ).isoformat()
            })

    return games


def save_to_supabase(games):
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "Supabase-Zugangsdaten fehlen."
        )

    if not games:
        print("Keine NHL-Spiele gefunden.")
        return

    endpoint = (
        f"{SUPABASE_URL}/rest/v1/hockey_games"
    )

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,"
                  "return=minimal"
    }

    response = requests.post(
        endpoint,
        headers=headers,
        params={
            "on_conflict": "league,game_id"
        },
        json=games,
        timeout=60
    )

    response.raise_for_status()

    print(
        f"{len(games)} NHL-Spiele "
        "an Supabase übertragen."
    )


def main():
    print("Starte NHL-Datenimport...")

    games = get_nhl_games()
    print(f"NHL-Spiele gefunden: {len(games)}")

    save_to_supabase(games)

    print("Datenimport abgeschlossen.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Fehler: {error}", file=sys.stderr)
        sys.exit(1)


