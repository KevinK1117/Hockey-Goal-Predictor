"""Read-only mobile DEL regular-season schedule, from the public official page.

Experimental HTML adapter: if the official page changes or does not expose a
parseable HTML table, show the official link rather than inventing games.
"""
from __future__ import annotations

import datetime as dt
import io
import re
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

DEL_URL = 'https://www.penny-del.org/statistik/saison-2026-27/hauptrunde/spielplan'
BERLIN = ZoneInfo('Europe/Berlin')
GERMAN_MONTHS = {'januar': 1, 'februar': 2, 'märz': 3, 'maerz': 3,
                 'april': 4, 'mai': 5, 'juni': 6, 'juli': 7,
                 'august': 8, 'september': 9, 'oktober': 10,
                 'november': 11, 'dezember': 12}


def _flat_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [' '.join(str(p) for p in col if not str(p).startswith('Unnamed'))
                  if isinstance(col, tuple) else str(col) for col in df.columns]
    df.columns = [re.sub(r'\s+', ' ', x).strip().lower() for x in df.columns]
    return df


def _date(value: object) -> dt.date | None:
    s = str(value).replace('\xa0', ' ').strip()
    match = re.search(r'(\d{1,2})\.(\d{1,2})\.(20\d{2})', s)
    if match:
        try:
            return dt.date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        except ValueError:
            return None
    match = re.search(r'(\d{1,2})\.\s*([A-Za-zÄÖÜäöüß]+)\s*(20\d{2})', s)
    if match:
        month = GERMAN_MONTHS.get(match.group(2).lower())
        if month:
            try:
                return dt.date(int(match.group(3)), month, int(match.group(1)))
            except ValueError:
                pass
    return None


def _field(row: pd.Series, names: tuple[str, ...]) -> str:
    for name in names:
        for column in row.index:
            if column == name or column.startswith(name + ' '):
                value = str(row[column]).strip()
                if value and value.lower() != 'nan':
                    return value
    return ''


@st.cache_data(ttl=1800, show_spinner=False)
def load_del_schedule() -> pd.DataFrame:
    """Parse only verifiable game rows. No writes, keys, or hidden API calls."""
    response = requests.get(DEL_URL, timeout=25,
                            headers={'User-Agent': 'Mozilla/5.0 (compatible; HockeyGoalPredictor/1.0)'})
    response.raise_for_status()
    tables = pd.read_html(io.StringIO(response.text), displayed_only=False)
    games = []
    for raw in tables:
        table = _flat_columns(raw)
        for _, row in table.iterrows():
            day = _date(_field(row, ('datum', 'date')))
            home = _field(row, ('heim', 'home'))
            away = _field(row, ('gast', 'auswärts', 'away'))
            if not day or not home or not away or home == away:
                continue
            if not (dt.date(2026, 9, 17) <= day <= dt.date(2027, 3, 9)):
                continue
            time_str = _field(row, ('uhrzeit', 'zeit', 'time'))
            match = re.search(r'\b([01]?\d|2[0-3]):([0-5]\d)\b', time_str)
            kickoff = f'{int(match.group(1)):02d}:{match.group(2)}' if match else 'Zeit offen'
            result = _field(row, ('ergebnis', 'resultat', 'result', 'stand'))
            if not result:
                # Some official tables have an unlabeled score column.
                for value in row.values:
                    candidate = str(value).strip()
                    if re.fullmatch(r'\d{1,2}\s*:\s*\d{1,2}', candidate):
    left, right = map(int, candidate.split(':'))
    if left <= 15 and right <= 15:
        result = candidate
        break
                        
                    
            games.append({'Datum': day, 'Uhrzeit': kickoff,
                          'Heim': home, 'Gast': away,
                          'Ergebnis': result if re.search(r'\d+\s*:\s*\d+', result) else '–'})
    if not games:
        return pd.DataFrame(columns=['Datum', 'Uhrzeit', 'Heim', 'Gast', 'Ergebnis'])
    return (pd.DataFrame(games).drop_duplicates(subset=['Datum', 'Heim', 'Gast'])
            .sort_values(['Datum', 'Uhrzeit', 'Heim']).reset_index(drop=True))


def render_del_schedule() -> None:
    st.subheader('🇩🇪 PENNY DEL – Spielplan 2026/27')
    st.caption('Hauptrunde · deutsche Zeit · öffentliche offizielle Quelle · nur Lesezugriff')
    st.link_button('Offiziellen DEL-Spielplan öffnen', DEL_URL, use_container_width=True)
    try:
        games = load_del_schedule()
    except (requests.RequestException, ValueError, ImportError, AttributeError) as exc:
        st.warning('Der offizielle Spielplan konnte derzeit nicht automatisch eingelesen werden. '
                   'Bitte den offiziellen Link oben verwenden.')
        st.caption(f'Technischer Hinweis: {type(exc).__name__}')
        return
    if games.empty:
        st.info('Die DEL-Webseite liefert derzeit keine zuverlässig auslesbare Spielplantabelle. '
                'Es werden keine Begegnungen erfunden.')
        return
    today = dt.datetime.now(BERLIN).date()
    selection = st.radio('Zeitraum', ['Heute', 'Morgen', 'Nächste 7 Tage', 'Datum wählen'],
                         horizontal=True, key='del_period')
    if selection == 'Heute':
        filtered = games[games['Datum'] == today]
    elif selection == 'Morgen':
        filtered = games[games['Datum'] == today + dt.timedelta(days=1)]
    elif selection == 'Nächste 7 Tage':
        filtered = games[(games['Datum'] >= today) &
                         (games['Datum'] <= today + dt.timedelta(days=6))]
    else:
        chosen = st.date_input('DEL-Spieltag', value=today, key='del_selected_date')
        filtered = games[games['Datum'] == chosen]
    if filtered.empty:
        st.info('Für diesen Zeitraum sind im eingelesenen Spielplan keine DEL-Spiele vorhanden.')
        return
    st.caption(f'{len(filtered)} Begegnung(en)')
    for _, game in filtered.iterrows():
        with st.container(border=True):
            st.markdown(f"**{game['Heim']} – {game['Gast']}**")
            st.caption(f"{game['Datum'].strftime('%d.%m.%Y')} · {game['Uhrzeit']} Uhr")
            if game['Ergebnis'] != '–':
                st.markdown(f"**Ergebnis: {game['Ergebnis']}**")
            else:
                st.caption('Noch kein Ergebnis')
    with st.expander('Alle eingelesenen Spiele als Tabelle'):
        st.dataframe(games, hide_index=True, use_container_width=True)
