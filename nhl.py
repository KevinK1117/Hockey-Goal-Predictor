"""NHL schedule and player game logs; no invented statistics."""
import datetime as dt
import requests

BASE = 'https://api-web.nhle.com/v1'

def get_json(path):
    response = requests.get(f'{BASE}/{path}', timeout=20, headers={'User-Agent': 'HockeyGoalPredictor/0.1'})
    response.raise_for_status()
    return response.json()

def games_for_date(date=None):
    date = date or dt.date.today().isoformat()
    data = get_json(f'schedule/{date}')
    games = []
    for day in data.get('gameWeek', []):
        if day.get('date') != date:
            continue
        for game in day.get('games', []):
            games.append({'id': game.get('id'), 'startUTC': game.get('startTimeUTC'),
                          'away': game.get('awayTeam', {}).get('abbrev', '?'),
                          'home': game.get('homeTeam', {}).get('abbrev', '?')})
    return games

def skaters_from_boxscore(game_id):
    """May be empty before the NHL publishes a game boxscore/roster."""
    data = get_json(f'gamecenter/{game_id}/boxscore')
    result = []
    for side in ('awayTeam', 'homeTeam'):
        for group in ('forwards', 'defense'):
            for p in data.get('playerByGameStats', {}).get(side, {}).get(group, []):
                result.append({'id': p.get('playerId'), 'name': p.get('name', {}).get('default', ''),
                               'team': data.get(side, {}).get('abbrev', '')})
    return result

def player_recent(player_id, season='20262027', count=10):
    data = get_json(f'player/{player_id}/game-log/{season}/2')
    return data.get('gameLog', [])[:count]
