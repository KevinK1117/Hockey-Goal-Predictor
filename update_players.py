"""Import NHL player box scores into Supabase (last N calendar days)."""
import os
import sys
import time
from datetime import date, timedelta

import requests

NHL_API = "https://api-web.nhle.com/v1"
SUPABASE_URL = os.environ["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = os.environ["SUPABASE_SECRET_KEY"]
DAYS_BACK = int(os.getenv("NHL_DAYS_BACK", "30"))
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "HockeyGoalPredictor/1.0"})

def get_json(url):
    for attempt in range(4):
        try:
            response = SESSION.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)

def seconds(value):
    try:
        minutes, secs = str(value or "0:00").split(":", 1)
        return int(minutes) * 60 + int(secs)
    except (ValueError, TypeError):
        return 0

def team_code(team):
    return (team or {}).get("abbrev", "")

def player_rows(box, game_id, game_date):
    home = team_code(box.get("homeTeam"))
    away = team_code(box.get("awayTeam"))
    result = []
    for side, opponent in (("homeTeam", away), ("awayTeam", home)):
        team = home if side == "homeTeam" else away
        roster = box.get("playerByGameStats", {}).get(side, {})
        for group in ("forwards", "defense"):
            for player in roster.get(group, []):
                pid = player.get("playerId")
                if pid is None:
                    continue
                name = player.get("name", {})
                if isinstance(name, dict):
                    name = name.get("default", "")
                result.append({
                    "game_id": str(game_id),
                    "player_id": str(pid),
                    "game_date": game_date,
                    "team": team,
                    "opponent": opponent,
                    "player_name": str(name),
                    "goals": int(player.get("goals") or 0),
                    "assists": int(player.get("assists") or 0),
                    "shots": int(player.get("sog") or 0),
                    "powerplay_goals": int(player.get("powerPlayGoals") or 0),
                    "time_on_ice_seconds": seconds(player.get("toi")),
                })
    return result

def save(rows):
    if not rows:
        return
    url = f"{SUPABASE_URL}/rest/v1/nhl_player_games"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }
    for start in range(0, len(rows), 150):
        response = SESSION.post(
            url,
            params={"on_conflict": "game_id,player_id"},
            headers=headers,
            json=rows[start:start + 150],
            timeout=45,
        )
        if not response.ok:
            raise RuntimeError(f"Supabase HTTP {response.status_code}: {response.text[:600]}")

def main():
    if not 1 <= DAYS_BACK <= 365:
        raise ValueError("NHL_DAYS_BACK muss zwischen 1 und 365 liegen")
    total_games = 0
    total_rows = 0
    today = date.today()
    for offset in range(DAYS_BACK):
        day = (today - timedelta(days=offset)).isoformat()
        schedule = get_json(f"{NHL_API}/score/{day}")
        for game in schedule.get("games", []):
            if game.get("gameState") != "OFF":
                continue
            gid = game.get("id")
            if not gid:
                continue
            box = get_json(f"{NHL_API}/gamecenter/{gid}/boxscore")
            rows = player_rows(box, gid, game.get("gameDate") or day)
            save(rows)
            total_games += 1
            total_rows += len(rows)
        print(f"{day}: fertig", flush=True)
    print(f"Import abgeschlossen: {total_games} Spiele, {total_rows} Spieler-Spiel-Datensätze")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Import fehlgeschlagen: {exc}", file=sys.stderr)
        sys.exit(1)
