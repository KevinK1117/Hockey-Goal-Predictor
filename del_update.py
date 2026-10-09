"""DEL 2026/27: Spieler-Einzelspielstatistiken sicher als CSV vorbereiten.

Nur offizielle PENNY-DEL-Webseiten. Kein Supabase-Schreibzugriff.
Die gefundene Linkliste ist nicht garantiert vollständig.
"""
from __future__ import annotations

import io
import re
import time
from datetime import datetime
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
        self.links: set[str] = set()

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        href = dict(attrs).get("href") or ""
        absolute = urljoin(BASE, href)
        parsed = urlparse(absolute)
        if (parsed.netloc == "www.penny-del.org"
                and parsed.path.startswith(PROFILE_PATH)
                and parsed.path.endswith("/details")):
            self.links.add(absolute)


def fetch(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=(10, 15))
    response.raise_for_status()
    return response.text


def find_table(html: str) -> pd.DataFrame | None:
    try:
        tables = pd.read_html(io.StringIO(html), displayed_only=False)
    except (ValueError, ImportError):
        return None
    for table in tables:
        table.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in table.columns]
        if {"Datum", "Gegner", "T", "Schüsse"}.issubset(table.columns):
            return table
    return None


def parse_name(url: str) -> str:
    slug = urlparse(url).path.rstrip("/").split("/")[-2]
    slug = re.sub(r"-\d+$", "", slug)
    return slug.replace("_", " ").replace("-", " ").strip().title()


def number(value) -> int | None:
    s = str(value).strip()
    if not re.fullmatch(r"\d+", s):
        return None
    return int(s)


def main():
    retry = Retry(total=2, connect=2, read=2, status=2, backoff_factor=1,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"], respect_retry_after_header=True)
    records: list[dict] = []
    report: list[dict] = []
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
            status = "ok"
            count = 0
            try:
                html = fetch(session, url)
                table = find_table(html)
                if table is None:
                    status = "keine_tabelle"
                else:
                    for _, row in table.iterrows():
                        raw_date = str(row["Datum"]).strip()
                        parsed_date = pd.to_datetime(raw_date, format="%d.%m.%Y", errors="coerce")
                        goals, shots = number(row["T"]), number(row["Schüsse"])
                        opponent = str(row["Gegner"]).strip()
                        if (pd.isna(parsed_date) or not (datetime(2026, 9, 1) <= parsed_date.to_pydatetime() <= datetime(2027, 6, 30))
                                or goals is None or shots is None or goals > shots
                                or not opponent or opponent.lower() == "nan"):
                            continue
                        records.append({
                            "season": SEASON,
                            "game_date": parsed_date.strftime("%Y-%m-%d"),
                            "player_name": parse_name(url),
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
            report.append({"source_url": url, "status": status, "valid_games": count})
            if index % 25 == 0 or index == len(links):
                print(f"Geprüft: {index}/{len(links)} | Zeilen: {len(records)}", flush=True)

    pd.DataFrame(report).to_csv(REPORT, index=False)
    if not records:
        raise RuntimeError("Keine gültigen Spiele. Nur Prüfbericht erstellt.")
    df = pd.DataFrame(records).drop_duplicates(subset=["source_url", "game_date", "opponent"])
    df.sort_values(["game_date", "player_name"], inplace=True)
    df.to_csv(OUTPUT, index=False)
    print(f"CSV erstellt: {OUTPUT} ({len(df)} Spieler-Spiel-Zeilen)", flush=True)
    print(f"Prüfbericht: {REPORT}", flush=True)
    print("ACHTUNG: Spielernamen sind aus URL-Slugs abgeleitet; Teamzuordnung fehlt.", flush=True)
    print("Spielerliste möglicherweise unvollständig. Kein Supabase-Schreibzugriff.", flush=True)


if __name__ == "__main__":
    main()
