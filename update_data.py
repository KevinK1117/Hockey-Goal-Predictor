
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

API_URL = "https://api-web.nhle.com/v1/schedule/now"


def update_nhl_data():
    response = requests.get(API_URL, timeout=30)
    response.raise_for_status()
    data = response.json()

    games = []

    for day in data.get("gameWeek", []):
        for game in day.get("games", []):
            games.append({
                "id": game.get("id"),
                "date": game.get("gameDate"),
                "home": game.get("homeTeam", {}).get("abbrev"),
                "away": game.get("awayTeam", {}).get("abbrev"),
                "start_utc": game.get("startTimeUTC"),
                "state": game.get("gameState")
            })

    output = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "league": "NHL",
        "games": games
    }

    Path("data").mkdir(exist_ok=True)

    with open(
        "data/nhl_schedule.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(output, file, indent=2)

    print(f"NHL-Spiele geladen: {len(games)}")


if __name__ == "__main__":
    update_nhl_data()
