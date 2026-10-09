"""NHL player-form predictions from the existing Supabase view (read-only)."""
import html
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
            params={
                'select': 'player_id,player_name,team,games_available,games_last5,games_last10,goals_last5,goals_last10,shots_last10,last_goal_date',
                'order': 'player_name.asc', 'limit': 1000, 'offset': offset,
            },
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


def prepare_player_form(df: pd.DataFrame) -> pd.DataFrame:
    """Use exactly the same illustrative Poisson model as before."""
    df = df.copy()
    numeric = ['games_available', 'games_last5', 'games_last10',
               'goals_last5', 'goals_last10', 'shots_last10']
    for col in numeric:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    prior_games = 10.0
    prior_rate = 0.15
    df['lambda'] = (df['goals_last10'] + prior_games * prior_rate) / (df['games_last10'] + prior_games)
    df['torchance_pct'] = (100 * (1 - df['lambda'].map(lambda x: math.exp(-x)))).round(1)
    df['sample_ok'] = df['games_last10'] >= 5
    return df


def mobile_card(player: pd.Series, compact: bool = False) -> None:
    """A full-width responsive card with the player and probability together."""
    name = html.escape(str(player.get('player_name') or 'Unbekannt'))
    team = html.escape(str(player.get('team') or '–'))
    pct = float(player['torchance_pct'])
    games = int(player['games_last10'])
    goals = int(player['goals_last10'])
    shots = int(player['shots_last10'])
    last_goal = player.get('last_goal_date')
    last_goal_text = '' if compact or pd.isna(last_goal) or not str(last_goal).strip() else (
        f'<div class="hgp-last">Letztes Tor: {html.escape(str(last_goal))}</div>'
    )
    st.markdown(f'''
<div class="hgp-card">
  <div class="hgp-card-head">
    <div class="hgp-identity"><div class="hgp-name">{name}</div><div class="hgp-team">{team}</div></div>
    <div class="hgp-prob"><strong>{pct:.1f} %</strong><span>Torschance</span></div>
  </div>
  <div class="hgp-stats"><span><b>{goals}</b> Tore</span><span><b>{games}</b> Spiele</span><span><b>{shots}</b> Schüsse</span></div>
  {last_goal_text}
</div>''', unsafe_allow_html=True)


def mobile_styles() -> None:
    st.markdown('''<style>
.hgp-card {border:1px solid rgba(128,128,128,.28);border-radius:14px;padding:13px 15px;margin:0 0 10px 0;background:rgba(128,128,128,.045)}
.hgp-card-head {display:flex;justify-content:space-between;align-items:center;gap:10px}
.hgp-identity {min-width:0;flex:1}.hgp-name {font-weight:700;font-size:1rem;overflow-wrap:anywhere}
.hgp-team {font-size:.82rem;opacity:.7;margin-top:2px}
.hgp-prob {text-align:right;white-space:nowrap}.hgp-prob strong {display:block;font-size:1.4rem;line-height:1.2}
.hgp-prob span {font-size:.74rem;opacity:.7}
.hgp-stats {display:flex;gap:8px;flex-wrap:wrap;margin-top:11px;font-size:.83rem}
.hgp-stats span {background:rgba(128,128,128,.12);padding:5px 9px;border-radius:8px}
.hgp-last {font-size:.75rem;opacity:.7;margin-top:9px}
@media(max-width:600px){.block-container{padding-left:1rem;padding-right:1rem}.hgp-card{padding:12px}}
</style>''', unsafe_allow_html=True)


def render_player_predictions():
    st.subheader('🏒 NHL – Spielerform & Torschützenchancen')
    st.caption('Einfaches, noch nicht kalibriertes Poisson-Modell. Nur gespeicherte Spiele werden berücksichtigt.')
    mobile_styles()
    url = get_setting('SUPABASE_URL')
    key = get_setting('SUPABASE_SECRET_KEY') or get_setting('SUPABASE_SERVICE_ROLE_KEY')
    if not url or not key:
        st.warning('SUPABASE_URL und SUPABASE_SECRET_KEY fehlen in den Streamlit-Secrets.')
        return
    try:
        df = load_player_form(url, key)
    except requests.RequestException:
        st.error('Spielerstatistiken konnten nicht geladen werden. Bitte Supabase-URL, Schlüssel und View-Zugriff prüfen.')
        return
    if df.empty:
        st.info('Noch keine Spielerstatistiken vorhanden.')
        return
    df = prepare_player_form(df)
    teams = sorted(str(t) for t in df['team'].dropna().unique() if str(t).strip())
    chosen = st.selectbox('Team', ['Alle Teams'] + teams, key='player_form_team')
    if chosen != 'Alle Teams':
        df = df[df['team'] == chosen]
    df = df.sort_values(['torchance_pct', 'shots_last10'], ascending=False)
    card_tab, table_tab = st.tabs(['📱 Übersicht', '📊 Tabelle'])
    with card_tab:
        if df.empty:
            st.info('Keine Spieler für dieses Team gefunden.')
        else:
            count = st.selectbox('Spieler anzeigen', [10, 20, 50, 100], index=1, key='player_mobile_count')
            for _, player in df.head(count).iterrows():
                mobile_card(player)
    with table_tab:
        display = df.rename(columns={
            'player_name': 'Spieler', 'team': 'Team', 'games_last5': 'Spiele (5)',
            'goals_last5': 'Tore (5)', 'games_last10': 'Spiele (10)',
            'goals_last10': 'Tore (10)', 'shots_last10': 'Schüsse (10)',
            'last_goal_date': 'Letztes Tor', 'torchance_pct': 'Torschance (%)',
        })
        st.dataframe(display[['Spieler', 'Team', 'Spiele (5)', 'Tore (5)',
                              'Spiele (10)', 'Tore (10)', 'Schüsse (10)',
                              'Letztes Tor', 'Torschance (%)']],
                     hide_index=True, use_container_width=True)
    st.caption('Achtung: Bei weniger als 10 gespeicherten Spielen ist die Datengrundlage begrenzt. '
               'Die Torschance gilt für ein hypothetisches nächstes Spiel, nicht für eine konkrete Paarung.')
