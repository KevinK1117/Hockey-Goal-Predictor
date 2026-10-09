import io
import pandas as pd
import requests

URL = (
    "https://www.penny-del.org/statistik/"
    "spielerdetails/hauptrunde-2627/"
    "ty_ronning-2209/details"
)

response = requests.get(
    URL,
    timeout=30,
    headers={"User-Agent": "Mozilla/5.0"},
)
response.raise_for_status()

tables = pd.read_html(io.StringIO(response.text))

found = False

for table in tables:
    columns = [str(c).strip() for c in table.columns]

    if "Datum" in columns and "Schüsse" in columns:
        print("DEL-Einzelspielstatistiken gefunden!")
        print(table.head().to_string(index=False))
        found = True
        break

if not found:
    raise RuntimeError(
        "DEL-Statistiktabelle nicht gefunden. "
        "Es wurden keine Daten gespeichert."
    )
