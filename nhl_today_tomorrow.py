"""Mobile-first NHL scorer predictions for today and tomorrow (Europe/Berlin)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

from player_predictions import get_setting, load_player_form, mobile_card, mobile_styles, prepare_player_form

BERLIN = ZoneInfo('Europe/Berlin')
SEASON = 20262027


@st.cache_data(ttl=900, show_spinner=False)
def load_nhl_games(start_date: str, end_date: str) -> list[dict]:
    first = datetime.fromisoformat(start_date).date() - timedelta(days=1)
    last = datetime.fromisoformat(end_date).date() + timedelta(days=1)
    games_by_id = {}
    day = first
    while day <= last:
        response = requests.get(f'https://api-web.nhle.com/v1/schedule/{day.isoformat()}', timeout=25)
        response.raise_for_status()
        for week in response.json().get('gameWeek', []):
            for game in week.get('games', []):
                if game.get('gameType') != 2 or game.get('season') != SEASON:
                    continue
                if not game.get('startTimeUTC'):
                    continue
                local_time = datetime.fromisoformat(game['startTimeUTC'].replace('Z', '+00:00')).astimezone(BERLIN)
                if start_date <= local_time.date().isoformat() <= end_date:
                    home, away = game.get('homeTeam') or {}, game.get('awayTeam') or {}
                    if home.get('abbrev') and away.get('abbrev'):
                        games_by_id[game['id']] = {
                            'date': local_time.date().isoformat(),
                            'time': local_time.strftime('%H:%M'),
                            'home': home['abbrev'], 'away': away['abbrev'], 'id': game['id'],
                        }
        day += timedelta(days=1)
    return sorted(games_by_id.values(), key=lambda g: (g['date'], g['time'], g['id']))


def render_nhl_today_tomorrow():
    st.subheader('🎯 NHL – Torschützen heute & morgen')
    st.caption('Deutsche Zeit · reguläre Saison 2026/27 · unverändertes Poisson-Modell')
    mobile_styles()
    url = get_setting('SUPABASE_URL')
    key = get_setting('SUPABASE_SECRET_KEY') or get_setting('SUPABASE_SERVICE_ROLE_KEY')
    if not url or not key:
        st.warning('Supabase-Secrets fehlen. Bitte die bestehenden Streamlit-Secrets prüfen.')
        return
    today = datetime.now(BERLIN).date()
    tomorrow = today + timedelta(days=1)
    try:
        games = load_nhl_games(today.isoformat(), tomorrow.isoformat())
        players = load_player_form(url, key)
    except (requests.RequestException, ValueError, KeyError, TypeError):
        st.error('Spielplan oder Spielerform konnte nicht geladen werden. Bitte später erneut versuchen.')
        return
    if players.empty:
        st.info('Noch keine Spielerform-Daten vorhanden.')
        return
    players = prepare_player_form(players)
    players['team'] = players['team'].astype(str).str.upper().str.strip()
    players['match_team'] = players['team'].replace({'UTAH': 'UTA'})

    selected = st.radio('Spieltag', ['Heute', 'Morgen'], horizontal=True, key='nhl_scorer_day')
    selected_date = today if selected == 'Heute' else tomorrow
    st.caption(selected_date.strftime('%d.%m.%Y'))
    selected_games = [g for g in games if g['date'] == selected_date.isoformat()]
    if not selected_games:
        st.info('Für diesen Tag sind keine NHL-Regular-Season-Spiele angesetzt.')
        return

    for game in selected_games:
        matchup = f"{game['away']} @ {game['home']}"
        with st.expander(f"🏒 {game['time']} Uhr · {matchup}", expanded=True):
            matchup_players = players[players['match_team'].isin((game['away'], game['home']))]
            if matchup_players.empty:
                st.info('Für diese Teams sind noch keine Spielerstatistiken gespeichert.')
                continue
            view = matchup_players.sort_values(['torchance_pct', 'shots_last10'], ascending=False).head(20)
            card_tab, table_tab = st.tabs(['📱 Top-Torschützen', '📊 Tabelle'])
            with card_tab:
                for _, player in view.iterrows():
                    mobile_card(player, compact=True)
            with table_tab:
                display = view.rename(columns={
                    'player_name': 'Spieler', 'team': 'Team',
                    'games_last10': 'Spiele (10)', 'goals_last10': 'Tore (10)',
                    'shots_last10': 'Schüsse (10)', 'torchance_pct': 'Torschance (%)',
                })
                st.dataframe(display[['Spieler', 'Team', 'Spiele (10)', 'Tore (10)',
                                      'Schüsse (10)', 'Torschance (%)']],
                             hide_index=True, use_container_width=True)
    st.caption('Schätzung für mindestens ein Tor im nächsten Spiel. Nicht kalibriert, '
               'nicht gegnerbereinigt; tatsächliche Aufstellung und Einsatzzeit sind nicht berücksichtigt.')
