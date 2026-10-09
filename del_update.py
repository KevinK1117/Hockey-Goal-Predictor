"""DEL 2026/27: sicherer Discovery-Test ohne Datenbank-Schreibzugriff.

Prueft Spielerlinks aus der offiziellen Basis-Tabelle und deren
Einzelspieltabellen. Noch KEIN vollstaendiger Liga-Import.
"""
from __future__ import annotations

import io
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests

BASE = 'https://www.penny-del.org'
LIST_URL = BASE + '/statistik/saison-2026-27/hauptrunde/playerstats/basis'
PROFILE_PATH = '/statistik/spielerdetails/hauptrunde-2627/'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; HockeyGoalPredictor/1.0)'}


class PlayerLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if tag != 'a':
            return
        href = dict(attrs).get('href', '')
        absolute = urljoin(BASE, href)
        parsed = urlparse(absolute)
        if (parsed.netloc == 'www.penny-del.org'
                and parsed.path.startswith(PROFILE_PATH)
                and parsed.path.endswith('/details')):
            self.links.add(absolute)


def get_html(session, url):
    response = session.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def get_game_table(html):
    for table in pd.read_html(io.StringIO(html), displayed_only=False):
        columns = [re.sub(r'\s+', ' ', str(c)).strip() for c in table.columns]
        if 'Datum' in columns and 'Gegner' in columns and 'Schüsse' in columns and 'T' in columns:
            table.columns = columns
            return table
    return None


def main():
    with requests.Session() as session:
        session.headers.update(HEADERS)
        listing = get_html(session, LIST_URL)
        parser = PlayerLinks()
        parser.feed(listing)
        links = sorted(parser.links)
        print(f'Spielerprofile auf der geladenen Listenseite: {len(links)}')
        if not links:
            raise RuntimeError('Keine Spielerprofil-Links gefunden. Kein Import.')

        # Bewusst nur drei Profile: erst die Tabellenstruktur pruefen.
        valid = 0
        for url in links[:3]:
            html = get_html(session, url)
            table = get_game_table(html)
            if table is None:
                print(f'Keine passende Einzelspieltabelle: {url}')
                continue
            print(f'Profil: {url}')
            print(f'Einzelspielzeilen: {len(table)}')
            print(table[['Datum', 'Gegner', 'T', 'Schüsse']].head(3).to_string(index=False))
            valid += 1

        if valid == 0:
            raise RuntimeError('Keine gueltigen Spieler-Einzelspieltabellen. Kein Import.')
        print('Discovery-Test erfolgreich. Keine Daten in Supabase geschrieben.')
        print('Hinweis: Die Vollstaendigkeit der Spielerliste ist noch NICHT geprueft.')


if __name__ == '__main__':
    main()
