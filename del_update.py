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
