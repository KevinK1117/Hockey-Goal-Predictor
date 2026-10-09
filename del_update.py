"""DEL 2026/27: robuster Discovery-Test ohne Supabase-Schreibzugriff.

Liest Spielerlinks aus der offiziellen Statistik und testet wenige Profile.
Timeouts werden begrenzt wiederholt; unerreichbare Profile werden protokolliert.
Keine Aussage zur Vollständigkeit der Liste.
"""
from __future__ import annotations

import io
import re
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = 'https://www.penny-del.org'
LIST_URL = BASE + '/statistik/saison-2026-27/hauptrunde/playerstats/basis'
PROFILE_PATH = '/statistik/spielerdetails/hauptrunde-2627/'
HEADERS = {'User-Agent': 'Mozilla/5.0 (compatible; HockeyGoalPredictor/1.0)'}
TEST_PROFILES = 5


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
    response = session.get(url, timeout=(10, 15))
    response.raise_for_status()
    return response.text


def get_game_table(html):
    try:
        tables = pd.read_html(io.StringIO(html), displayed_only=False)
    except (ValueError, ImportError):
        return None
    for table in tables:
        columns = [re.sub(r'\s+', ' ', str(c)).strip() for c in table.columns]
        required = {'Datum', 'Gegner', 'Schüsse', 'T'}
        if required.issubset(columns):
            table.columns = columns
            return table
    return None


def main():
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=['GET'],
        respect_retry_after_header=True,
    )
    with requests.Session() as session:
        session.headers.update(HEADERS)
        session.mount('https://', HTTPAdapter(max_retries=retry))
        listing = get_html(session, LIST_URL)
        parser = PlayerLinks()
        parser.feed(listing)
        links = sorted(parser.links)
        print(f'Spielerprofile auf der geladenen Listenseite: {len(links)}', flush=True)
        if not links:
            raise RuntimeError('Keine Spielerprofil-Links gefunden. Kein Import.')

        valid = 0
        failed = 0
        missing_table = 0
        # Mehrere Profile testen, damit ein einzelner Timeout den Test nicht stoppt.
        for url in links[:TEST_PROFILES]:
            time.sleep(1)
            try:
                html = get_html(session, url)
            except requests.RequestException as exc:
                failed += 1
                print(f'Profil nicht erreichbar: {url} ({type(exc).__name__})', flush=True)
                continue
            table = get_game_table(html)
            if table is None:
                missing_table += 1
                print(f'Keine passende Einzelspieltabelle: {url}', flush=True)
                continue
                        print(f'Profil: {url}', flush=True)

            print('--- PROFIL-INFORMATIONEN ---', flush=True)
            try:
                for raw in pd.read_html(
                    io.StringIO(html),
                    displayed_only=False
                ):
                    print(
                        raw.head(3).to_string(index=False)[:1200],
                        flush=True
                    )
            except (ValueError, ImportError) as exc:
                print(f'Tabellenfehler: {exc}', flush=True)

            print('--- ENDE ---', flush=True)
            print(f'Einzelspielzeilen: {len(table)}', flush=True)
            print(
                table[['Datum', 'Gegner', 'T', 'Schüsse']]
                .head(3).to_string(index=False),
                flush=True
            )
            valid += 1

        print(f'Ergebnis: {valid} gueltig, {failed} nicht erreichbar, '
              f'{missing_table} ohne passende Tabelle.', flush=True)
        if valid == 0:
            raise RuntimeError('Kein gueltiges Profil getestet. Kein Import.')
        print('Discovery-Test erfolgreich. Keine Daten in Supabase geschrieben.', flush=True)
        print('Die Vollstaendigkeit der Spielerliste ist NICHT geprueft.', flush=True)


if __name__ == '__main__':
    main()
