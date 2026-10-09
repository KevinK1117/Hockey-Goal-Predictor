import datetime as dt
import streamlit as st
from nhl import games_for_date, skaters_from_boxscore, player_recent
from model import baseline_probability
from player_predictions import render_player_predictions
st.set_page_config(page_title='Hockey Goal Predictor', page_icon='🏒', layout='wide')
st.title('🏒 Hockey Goal Predictor – NHL & DEL')
st.warning('Prototyp: Prozentwerte sind unkalibrierte Basisschätzungen, keine belastbaren Vorhersagen. DEL noch nicht angebunden.')
league = st.selectbox('Liga', ['NHL', 'DEL'])
date = st.date_input('Spieltag (Datum)', dt.date.today())
if league == 'DEL':
    st.info('DEL-Datenquelle wird nach Prüfung der Nutzungsrechte integriert. Keine erfundenen Daten.')
else:
    if st.button('NHL-Spiele laden'):
        try:
            games = games_for_date(date.isoformat())
            if not games:
                st.info('Keine NHL-Spiele für dieses Datum gefunden.')
            for game in games:
                with st.expander(f"{game['away']} @ {game['home']} — {game['startUTC'] or 'Zeit offen'}"):
                    try:
                        skaters = skaters_from_boxscore(game['id'])
                        if not skaters:
                            st.info('Noch keine Spielerliste im Boxscore verfügbar. Keine Prognose möglich.')
                            continue
                        ranked = []
                        for p in skaters:
                            if not p['id']:
                                continue
                            try:
                                logs = player_recent(p['id'])
                                prob = baseline_probability(logs)
                                if prob is not None:
                                    ranked.append({'Spieler': p['name'], 'Team': p['team'],
                                                   'Torwahrscheinlichkeit (%, vorläufig)': prob,
                                                   'Tore letzte 10': sum(int(x.get('goals', 0) or 0) for x in logs),
                                                   'Spiele in Stichprobe': len(logs)})
                            except Exception:
                                continue
                        ranked.sort(key=lambda r: r['Torwahrscheinlichkeit (%, vorläufig)'], reverse=True)
                        if ranked:
                            st.dataframe(ranked[:5], hide_index=True, use_container_width=True)
                        else:
                            st.info('Für dieses Spiel liegen keine ausreichenden Spielerdaten vor.')
                    except Exception as exc:
                        st.error(f'Boxscore derzeit nicht verfügbar: {exc}')
        except Exception as exc:
            st.error(f'NHL-Abruf fehlgeschlagen: {exc}') 
st.divider()
render_player_predictions()
