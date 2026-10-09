"""Mobile DEL scorer view, read-only; season 2026/27 only.

Requires an independently populated Supabase view `del_player_form` with
player_name, team, games_last10, goals_last10, shots_last10, season.
No fictional player statistics are generated.
"""
from __future__ import annotations

import html
import math
import datetime as dt
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

from del_schedule import load_del_schedule, DEL_URL
from player_predictions import get_setting

BERLIN = ZoneInfo('Europe/Berlin')
SEASON = '2026/27'
COLUMNS = 'player_name,team,games_last10,goals_last10,shots_last10,season'


@st.cache_data(ttl=900, show_spinner=False)
def load_del_player_form(url: str, key: str) -> pd.DataFrame:
    endpoint = url.rstrip('/') + '/rest/v1/del_player_form'
    response = requests.get(endpoint, headers={'apikey': key, 'Authorization': f'Bearer {key}'},
                            params={'select': COLUMNS, 'season': 'eq.' + SEASON,
                                    'limit': 1000}, timeout=25)
    response.raise_for_status()
    return pd.DataFrame(response.json())


def render_del_scorers() -> None:
    st.subheader('🎯 DEL – Torschützen heute & morgen')
    st.caption('Saison 2026/27 · deutsche Zeit · nur vorhandene Spielerdaten · vorläufiges, nicht kalibriertes Modell')
    day = st.radio('DEL-Spieltag', ['Heute', 'Morgen'], horizontal=True, key='del_scorer_day')
    date = dt.datetime.now(BERLIN).date() + dt.timedelta(days=int(day == 'Morgen'))
    st.caption(date.strftime('%d.%m.%Y'))
    try:
        games = load_del_schedule()
    except (requests.RequestException, ValueError, ImportError, AttributeError):
        st.warning('DEL-Spielplan gerade nicht abrufbar.')
        st.link_button('Offiziellen Spielplan öffnen', DEL_URL)
        return
    matches = games[games['Datum'] == date] if not games.empty else games
    if matches.empty:
        st.info('Für diesen Tag wurden keine DEL-Begegnungen gefunden.')
        return
    url = get_setting('SUPABASE_URL')
    key = get_setting('SUPABASE_SECRET_KEY') or get_setting('SUPABASE_SERVICE_ROLE_KEY')
    players = pd.DataFrame()
    if url and key:
        try:
            players = load_del_player_form(url, key)
        except requests.RequestException:
            pass
    if not players.empty:
        for col in ('games_last10', 'goals_last10', 'shots_last10'):
            players[col] = pd.to_numeric(players[col], errors='coerce').fillna(0)
        players = players[(players['games_last10'] > 0) &
                          (players['season'].astype(str) == SEASON)].copy()
        # Same illustrative prior and Poisson transformation as the NHL model.
        rate = (players['goals_last10'] + 1.5) / (players['games_last10'] + 10.0)
        players['chance'] = (100 * (1 - rate.map(lambda x: math.exp(-x)))).round(1)
    for _, game in matches.iterrows():
        home, away = str(game['Heim']), str(game['Gast'])
        with st.expander(f"🏒 {game['Uhrzeit']} · {home} – {away}", expanded=False):
            if players.empty:
                st.info('Noch keine verifizierten DEL-Spielerformdaten angebunden. Keine Prognose möglich.')
                continue
            # Match only exact official team names; no guessed abbreviations.
            current = players[players['team'].isin([home, away])].sort_values(
                ['chance', 'shots_last10'], ascending=False).head(10)
            if current.empty:
                st.info('Für diese Mannschaften liegen noch keine passenden Spielerformdaten vor.')
                continue
            for _, player in current.iterrows():
                name = html.escape(str(player['player_name']))
                team = html.escape(str(player['team']))
                st.markdown(f"**{name}** · {team} — **{player['chance']:.1f} %**")
                st.caption(f"{int(player['goals_last10'])} Tore · {int(player['games_last10'])} Spiele · "
                           f"{int(player['shots_last10'])} Schüsse (max. letzte 10)")
    st.caption('Schätzungen für mindestens ein Tor im nächsten Spiel, ohne Gegner- oder Aufstellungsabgleich. '
               'Wenige Saisonspiele bedeuten hohe Unsicherheit.')
