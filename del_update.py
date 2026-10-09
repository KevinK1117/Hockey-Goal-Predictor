"""DEL 2026/27: geprüfte Einzelspielstatistiken als CSV vorbereiten.

Liest ausschließlich öffentliche PENNY-DEL-Seiten. Keine Supabase-Schreibzugriffe.
Namen/Teams werden nur übernommen, wenn sie anhand der HTML-Daten
plausibel identifiziert werden können; unklare Angaben bleiben leer.
"""
from __future__ import annotations

import io
import json
import re
import time
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://www.penny-del.org"
LIST_URL = BASE + "/statistik/saison-2026-27/hauptrunde/playerstats/basis"
PROFILE_PATH = "/statistik/spielerdetails/hauptrunde-2627/"
OUTPUT = Path("del_player_games_2026_27.csv")
REPORT = Path("del_import_report.csv")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; HockeyGoalPredictor/1.0)"}
SEASON = "2026/27"


class PlayerLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = set()

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        absolute = urljoin(BASE, dict(attrs).get("href") or "")
        parsed = urlparse(absolute)
        if (parsed.netloc == "www.penny-del.org"
                and parsed.path.startswith(PROFILE_PATH)
                and parsed.path.endswith("/details")):
            self.links.add(absolute)


class PageMetadata(HTMLParser):
    """Collect structured JSON-LD and visible headings, without guessing team."""
    def __init__(self):
        super().__init__()
        self.title = []
        self.headings = []
        self.jsonld = []
        self._capture = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type", "").lower() == "application/ld+json":
            self._capture, self._parts = "jsonld", []
        elif tag in {"h1", "title"}:
            self._capture, self._parts = tag, []

    def handle_data(self, data):
        if self._capture:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag != self._capture:
            return
        value = unescape("".join(self._parts)).strip()
        if value:
            if tag == "jsonld":
                try:
                    self.jsonld.append(json.loads(value))
                except ValueError:
                    pass
            elif tag == "h1":
                self.headings.append(value)
            elif tag == "title":
                self.title.append(value)
        self._capture, self._parts = None, []


def fetch(session, url):
    response = session.get(url, timeout=(10, 15))
    response.raise_for_status()
    return response.text


def find_table(html):
    try:
        tables = pd.read_html(io.StringIO(html), displayed_only=False)
    except (ValueError, ImportError):
        return None
    for table in tables:
        table.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in table.columns]
        if {"Datum", "Gegner", "T", "Schüsse"}.issubset(table.columns):
            return table
    return None


def slug_name(url):
    slug = urlparse(url).path.rstrip("/").split("/")[-2]
    return re.sub(r"-\d+$", "", slug).replace("_", " ").replace("-", " ").strip().title()


def _person_nodes(data):
    if isinstance(data, list):
        for item in data:
            yield from _person_nodes(item)
    elif isinstance(data, dict):
        types = data.get("@type", [])
        types = [types] if isinstance(types, str) else types
        if "Person" in types or "Athlete" in types:
            yield data
        for value in data.values():
            if isinstance(value, (dict, list)):
                yield from _person_nodes(value)


def metadata(html, url):
    parser = PageMetadata()
    parser.feed(html)
    expected = slug_name(url)
    names = set()
    teams = set()
    for obj in parser.jsonld:
        for person in _person_nodes(obj):
            name = person.get("name")
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
            affiliation = person.get("memberOf") or person.get("affiliation")
            if isinstance(affiliation, dict):
                team = affiliation.get("name")
                if isinstance(team, str) and team.strip():
                    teams.add(team.strip())
    # Heading only if its normalized text matches the profile's URL name.
    def normalized(value):
        return re.sub(r"[^a-z0-9]", "", value.lower())
    for heading in parser.headings:
        if normalized(heading) == normalized(expected):
            names.add(heading)
    return (next(iter(names)) if len(names) == 1 else "",
            next(iter(teams)) if len(teams) == 1 else "")


def number(value):
    value = str(value).strip()
    return int(value) if re.fullmatch(r"\d+", value) else None


def main():
    retry = Retry(total=2, connect=2, read=2, status=2, backoff_factor=1,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"], respect_retry_after_header=True)
    records, report = [], []
    with requests.Session() as session:
        session.headers.update(HEADERS)
        session.mount("https://", HTTPAdapter(max_retries=retry))
        listing = fetch(session, LIST_URL)
        parser = PlayerLinks()
        parser.feed(listing)
        links = sorted(parser.links)
        print(f"Gefundene Profil-Links: {len(links)}", flush=True)
        if not links:
            raise RuntimeError("Keine Profil-Links gefunden; kein Import.")

        for index, url in enumerate(links, 1):
            time.sleep(0.5)
            status, count, name, team = "ok", 0, "", ""
            try:
                html = fetch(session, url)
                name, team = metadata(html, url)
                table = find_table(html)
                if table is None:
                    status = "keine_tabelle"
                else:
                    for _, row in table.iterrows():
                        day = pd.to_datetime(str(row["Datum"]).strip(),
                                             format="%d.%m.%Y", errors="coerce")
                        goals, shots = number(row["T"]), number(row["Schüsse"])
                        opponent = str(row["Gegner"]).strip()
                        if (pd.isna(day) or not (pd.Timestamp("2026-09-01") <= day <= pd.Timestamp("2027-06-30"))
                                or goals is None or shots is None or goals > shots
                                or not opponent or opponent.lower() == "nan"):
                            continue
                        records.append({
                            "season": SEASON,
                            "game_date": day.strftime("%Y-%m-%d"),
                            "player_name": name,
                            "team": team,
                            "opponent": opponent,
                            "goals": goals,
                            "shots": shots,
                            "source_url": url,
                        })
                        count += 1
                    if count == 0:
                        status = "keine_gueltigen_spiele"
            except requests.RequestException as exc:
                status = type(exc).__name__
            report.append({"source_url": url, "status": status,
                           "valid_games": count, "verified_name": name,
                           "verified_team": team})
            if index % 25 == 0 or index == len(links):
                print(f"Geprüft: {index}/{len(links)} | Zeilen: {len(records)}", flush=True)

    pd.DataFrame(report).to_csv(REPORT, index=False)
    if not records:
        raise RuntimeError("Keine gültigen Spiele. Nur Prüfbericht erstellt.")
    df = pd.DataFrame(records).drop_duplicates(subset=["source_url", "game_date", "opponent"])
    df.sort_values(["game_date", "source_url"], inplace=True)
    df.to_csv(OUTPUT, index=False)
    print(f"CSV erstellt: {OUTPUT} ({len(df)} Spieler-Spiel-Zeilen)", flush=True)
    print(f"Prüfbericht: {REPORT}", flush=True)
    print(f"Profile mit eindeutigem Namen: {sum(bool(r['verified_name']) for r in report)}", flush=True)
    print(f"Profile mit eindeutigem Team: {sum(bool(r['verified_team']) for r in report)}", flush=True)
    print("Unklare Namen und Teams bleiben leer. Kein Supabase-Schreibzugriff.", flush=True)
    print("Vollständigkeit der Spielerprofile nicht bestätigt.", flush=True)


if __name__ == "__main__":
    main()
