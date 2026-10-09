"""Streamlit player-form table based on public.nhl_player_form."""
import math
import os

import pandas as pd
import requests
import streamlit as st


@st.cache_data(ttl=900, show_spinner=False)
def load_player_form(url: str, key: str) -> pd.DataFrame:
    endpoint = url.rstrip('/') + '/rest/v1/nhl_player_form'
    headers = {'apikey': key, 'Authorization': f'Bearer {key}'}
    rows = []
    offset = 0
    while True:
        response = requests.get(
            endpoint,
            headers=headers,
            params={'select': 'player_id,player_name,team,games_available,games_last5,games_last10,goals_last5,goals_last10,shots_last10,last_goal_date',
                    'order': 'player_name.asc', 'limit': 1000, 'offset': offset},
            timeout=30,
        )
        response.raise_for_status()
        batch = response.json()
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return pd.DataFrame(rows)


def get_setting(name: str) -> str:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, '')


def render_player_predictions():
    st.subheader('🏒 NHL – Spielerform & Torschützenchancen')
    st.caption('Einfaches, noch nicht kalibriertes Poisson-Modell. Nur gespeicherte Spiele werden berücksichtigt.')
    url = get_setting('SUPABASE_URL')
    key = get_setting('SUPABASE_SECRET_KEY') or get_setting('SUPABASE_SERVICE_ROLE_KEY')
    if not url or not key:
        st.warning('SUPABASE_URL und SUPABASE_SECRET_KEY fehlen in den Streamlit-Secrets.')
        return
    try:
        df = load_player_form(url, key)
    except requests.RequestException as exc:
        st.error('Spielerstatistiken konnten nicht geladen werden. Bitte Supabase-URL, Schlüssel und View-Zugriff prüfen.')
        return
    if df.empty:
        st.info('Noch keine Spielerstatistiken vorhanden.')
        return

    numeric = ['games_available', 'games_last5', 'games_last10', 'goals_last5', 'goals_last10', 'shots_last10']
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # Shrink small samples toward a conservative illustrative baseline of 0.15 goals/game.
    # This is NOT a calibrated player-specific forecast.
    prior_games = 10.0
    prior_rate = 0.15
    df['lambda'] = (df['goals_last10'] + prior_games * prior_rate) / (df['games_last10'] + prior_games)
    df['torchance_pct'] = (100 * (1 - df['lambda'].map(lambda x: math.exp(-x)))).round(1)
    df['sample_ok'] = df['games_last10'] >= 5

    teams = sorted(str(t) for t in df['team'].dropna().unique() if str(t).strip())
    chosen = st.selectbox('Team', ['Alle Teams'] + teams, key='player_form_team')
    if chosen != 'Alle Teams':
        df = df[df['team'] == chosen]
    df = df.sort_values(['torchance_pct', 'shots_last10'], ascending=False)
    display = df.rename(columns={
        'player_name': 'Spieler', 'team': 'Team', 'games_last5': 'Spiele (5)',
        'goals_last5': 'Tore (5)', 'games_last10': 'Spiele (10)',
        'goals_last10': 'Tore (10)', 'shots_last10': 'Schüsse (10)',
        'last_goal_date': 'Letztes Tor', 'torchance_pct': 'Torschance (%)',
    })
    st.dataframe(
        display[['Spieler', 'Team', 'Spiele (5)', 'Tore (5)', 'Spiele (10)',
                 'Tore (10)', 'Schüsse (10)', 'Letztes Tor', 'Torschance (%)']],
        hide_index=True, use_container_width=True,
    )
    st.caption('Achtung: Bei weniger als 10 gespeicherten Spielen ist die Datengrundlage begrenzt. '
               'Die Torschance gilt für ein hypothetisches nächstes Spiel, nicht für eine konkrete Paarung.')
