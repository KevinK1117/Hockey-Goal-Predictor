import datetime as dt
import streamlit as st
from nhl import games_for_date, skaters_from_boxscore, player_recent
from model import baseline_probability
from player_predictions import render_player_predictions
from nhl_today_tomorrow import render_nhl_today_tomorrow

st.set_page_config(page_title='Hockey Goal Predictor', page_icon='🏒', layout='wide')
st.title('🏒 Hockey Goal Predictor – NHL & DEL')
st.warning('Prototyp: Prozentwerte sind unkalibrierte Basisschätzungen, keine belastbaren Vorhersagen. DEL noch nicht angebunden.')

league = st.selectbox('Liga', ['NHL', 'DEL'])
date = st.date_input('Spieltag (Datum)', dt.date.today())


if league == 'DEL':
    st.subheader('🇩🇪 PENNY DEL – Saison 2026/27')
    st.caption('Reguläre Saison · Offizielle DEL-Daten')

    st.link_button(
        '🏒 Offiziellen DEL-Spielplan öffnen',
        'https://www.penny-del.org/statistik/saison-2026-27/hauptrunde/spielplan',
        use_container_width=True,
    )

    st.info(
        'DEL-Spielerstatistiken und Torschützenprognosen '
        'werden nach Anbindung einer geeigneten Datenquelle ergänzt.'
    )
```
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
                                    ranked.append({
                                        'Spieler': p['name'],
                                        'Team': p['team'],
                                        'Torwahrscheinlichkeit (%, vorläufig)': prob,
                                        'Tore letzte 10': sum(int(x.get('goals', 0) or 0) for x in logs),
                                        'Spiele in Stichprobe': len(logs),
                                    })
                            except Exception:
                                continue
                        ranked.sort(key=lambda r: r['Torwahrscheinlichkeit (%, vorläufig)'], reverse=True)
                        if ranked:
                            cards_tab, table_tab = st.tabs(['📱 Spielerübersicht', '📊 Tabelle'])
                            with cards_tab:
                                for player in ranked[:5]:
                                    with st.container(border=True):
                                        name_col, chance_col = st.columns([3, 2], gap='small')
                                        with name_col:
                                            st.markdown(f"**{player['Spieler']}**")
                                            st.caption(str(player['Team']))
                                        with chance_col:
                                            st.metric('Torschance', f"{player['Torwahrscheinlichkeit (%, vorläufig)']:.1f} %")
                                        st.caption(
                                            f"{player['Tore letzte 10']} Tore · "
                                            f"{player['Spiele in Stichprobe']} Spiele in Stichprobe"
                                        )
                            with table_tab:
                                st.dataframe(ranked[:5], hide_index=True, use_container_width=True)
                        else:
                            st.info('Für dieses Spiel liegen keine ausreichenden Spielerdaten vor.')
                    except Exception as exc:
                        st.error(f'Boxscore derzeit nicht verfügbar: {exc}')
        except Exception as exc:
            st.error(f'NHL-Abruf fehlgeschlagen: {exc}')

st.divider()
render_player_predictions()

st.divider()
render_nhl_today_tomorrow()
