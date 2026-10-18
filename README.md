# Cipher-B-Scanner

Scannt jede Woche rund 2.000 Aktien, ETFs, Rohstoffe und Coins weltweit auf neue, **bestätigte**
WaveTrend-Punkte (VuManChu Cipher B, Einstellungen 9 / 12 / hlc3 / 3) und prüft die Treffer danach täglich.

| Wann (Wiener Zeit) | Was | Ergebnis |
|---|---|---|
| Samstag ~07:30 | Weekly-Scan über das ganze Universum | `results/weekly_latest.md` |
| Di–Sa ~07:45 | Daily-Check der Weekly-Treffer (letzte 4 Wochen) + eigene Watchlist | `results/daily_latest.md` |

- **Grüner Punkt:** wt1 kreuzt wt2 nach oben. *Stark* = im überverkauften Bereich (wt2 ≤ −53).
- **Roter Punkt:** wt1 kreuzt wt2 nach unten. *Stark* = im überkauften Bereich (wt2 ≥ 53).
- Gewertet wird nur die zuletzt **abgeschlossene** Kerze – kein Repainting.

**Anpassen**
- Eigene Ticker immer prüfen: `universe/my_watchlist.txt` (Yahoo-Schreibweise, z.B. `RHM.DE`, `7203.T`, `BTC-USD`).
- Themen-Liste (aus der Marktlandkarte): `universe/themes.csv`.
- Manuell starten: Tab **Actions → Cipher-B-Scan → Run workflow**.

Daten: Yahoo Finance über `yfinance` (inoffiziell, nur für private Recherche). Keine Anlageberatung.
