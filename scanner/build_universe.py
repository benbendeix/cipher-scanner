"""Baut universe/universe.csv aus Index-Listen (Wikipedia) + themes.csv + static_asia.csv.

Fällt eine Quelle aus, werden die Ticker dieser Quelle aus der letzten
universe.csv übernommen, damit der Scan nie leer läuft.
"""
import io
import os
import re
import sys

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNI_DIR = os.path.join(ROOT, "universe")
OUT = os.path.join(UNI_DIR, "universe.csv")
UA = {"User-Agent": "cipher-scanner/1.0 (personal research; github.com/benbendeix/cipher-scanner)"}

# name, url, suffix, region, mögliche Ticker-Spalten, mögliche Namens-Spalten
SOURCES = [
    ("S&P 500", "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "", "USA", ["Symbol", "Ticker"], ["Security", "Company"]),
    ("S&P 400", "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "", "USA", ["Symbol", "Ticker symbol", "Ticker"], ["Security", "Company"]),
    ("Nasdaq-100", "https://en.wikipedia.org/wiki/Nasdaq-100", "", "USA", ["Ticker", "Symbol"], ["Company", "Security"]),
    ("DAX", "https://en.wikipedia.org/wiki/DAX", ".DE", "Deutschland", ["Ticker", "Symbol"], ["Company", "Name"]),
    ("MDAX", "https://en.wikipedia.org/wiki/MDAX", ".DE", "Deutschland", ["Ticker", "Symbol"], ["Company", "Name"]),
    ("SDAX", "https://en.wikipedia.org/wiki/SDAX", ".DE", "Deutschland", ["Ticker", "Symbol"], ["Company", "Name"]),
    ("ATX", "https://en.wikipedia.org/wiki/Austrian_Traded_Index", ".VI", "Österreich", ["Ticker", "Symbol"], ["Company", "Name"]),
    ("FTSE 100", "https://en.wikipedia.org/wiki/FTSE_100_Index", ".L", "UK", ["Ticker", "EPIC", "Symbol"], ["Company", "Name"]),
    ("CAC 40", "https://en.wikipedia.org/wiki/CAC_40", ".PA", "Frankreich", ["Ticker", "Symbol"], ["Company", "Name"]),
    ("SMI", "https://en.wikipedia.org/wiki/Swiss_Market_Index", ".SW", "Schweiz", ["Ticker", "Symbol"], ["Name", "Company"]),
    ("AEX", "https://en.wikipedia.org/wiki/AEX_index", ".AS", "Niederlande", ["Ticker symbol", "Ticker", "Symbol"], ["Company", "Name"]),
    ("IBEX 35", "https://en.wikipedia.org/wiki/IBEX_35", ".MC", "Spanien", ["Ticker", "Symbol"], ["Company", "Name"]),
    ("FTSE MIB", "https://en.wikipedia.org/wiki/FTSE_MIB", ".MI", "Italien", ["Ticker", "Symbol"], ["Company", "Name"]),
    ("OMXS30", "https://en.wikipedia.org/wiki/OMX_Stockholm_30", ".ST", "Schweden", ["Ticker", "Symbol"], ["Company", "Name"]),
    ("Hang Seng", "https://en.wikipedia.org/wiki/Hang_Seng_Index", ".HK", "Hongkong", ["Ticker", "Stock code", "Code", "SEHK"], ["Name", "Company"]),
    ("NIFTY 50", "https://en.wikipedia.org/wiki/NIFTY_50", ".NS", "Indien", ["Symbol", "Ticker"], ["Company name", "Company", "Name"]),
    ("S&P/TSX 60", "https://en.wikipedia.org/wiki/S%26P/TSX_60", ".TO", "Kanada", ["Symbol", "Ticker"], ["Company", "Name"]),
]


def _flatcols(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join(str(x) for x in c if "Unnamed" not in str(x)).strip() for c in df.columns]
    df.columns = [re.sub(r"\[.*?\]", "", str(c)).strip() for c in df.columns]
    return df


def _norm(raw, suffix):
    t = str(raw).strip().upper()
    t = re.sub(r"\[.*?\]", "", t).strip()
    if not t or t in ("NAN", "—", "-"):
        return None
    # Börsen-Präfixe wie "XETRA:" / "SEHK:" entfernen
    if ":" in t:
        t = t.split(":")[-1].strip()
    if suffix in ("", ".HK", ".NS", ".TO") and " " in t:
        t = t.split()[0]
    if suffix == "":  # USA: BRK.B -> BRK-B
        return t.replace(".", "-")
    if suffix == ".HK":
        digits = re.sub(r"\D", "", t)
        return f"{int(digits):04d}.HK" if digits else None
    if suffix == ".TO":
        t = t.replace(".TO", "").replace(".", "-")
        return t + ".TO"
    if suffix == ".L":  # London: "BA." -> BA.L, "BT.A" -> BT-A.L
        t = t.replace(".L", "") if t.endswith(".L") else t
        return t.rstrip(".").replace(".", "-") + ".L"
    if t.endswith(suffix):
        return t
    # schon mit anderer Börsen-Endung (z.B. .AS in CAC-Liste) -> übernehmen
    if re.search(r"\.[A-Z]{1,3}$", t) and not t.endswith("."):
        return t
    t = t.rstrip(".").replace(" ", "-").replace(".", "-")  # BT.A -> BT-A.L
    return t + suffix


def fetch_source(name, url, suffix, region, tcols, ncols):
    html = requests.get(url, headers=UA, timeout=30).text
    tables = pd.read_html(io.StringIO(html))
    best = None
    for tb in tables:  # erste passende Tabelle = aktuelle Mitglieder (spätere sind meist "Änderungen")
        tb = _flatcols(tb)
        if len(tb) < 10 or any("added" in c.lower() or "removed" in c.lower() for c in tb.columns):
            continue
        tcol = next((c for want in tcols for c in tb.columns if c.lower() == want.lower()), None)
        if tcol is None:
            tcol = next((c for want in tcols for c in tb.columns if want.lower() in c.lower()), None)
        if tcol is None:
            continue
        ncol = next((c for want in ncols for c in tb.columns if want.lower() in c.lower()), None)
        best = (tb, tcol, ncol)
        break
    if best is None:
        cols = [list(_flatcols(t).columns)[:6] for t in tables if len(t) >= 10][:4]
        raise ValueError(f"keine passende Tabelle. Spalten: {cols}")
    tb, tcol, ncol = best
    rows = []
    for _, r in tb.iterrows():
        t = _norm(r[tcol], suffix)
        if t:
            rows.append({"ticker": t, "name": str(r[ncol]) if ncol else "", "region": region, "source": name})
    return rows


def main():
    old = pd.read_csv(OUT) if os.path.exists(OUT) else pd.DataFrame(columns=["ticker", "name", "region", "source"])
    rows = []
    for name, url, suffix, region, tcols, ncols in SOURCES:
        try:
            got = fetch_source(name, url, suffix, region, tcols, ncols)
            print(f"[ok]   {name:<12} {len(got):>4} Ticker  z.B. {[g['ticker'] for g in got[:4]]}")
            rows += got
        except Exception as e:
            fallback = old[old["source"] == name].to_dict("records")
            print(f"[FAIL] {name:<12} {e!s:.80}  -> {len(fallback)} aus letzter Liste übernommen")
            rows += fallback

    for fname, src in (("static_asia.csv", "Asien statisch"), ("static_extra.csv", "ATX/Extra statisch"), ("themes.csv", "Marktlandkarte")):
        p = os.path.join(UNI_DIR, fname)
        if os.path.exists(p):
            d = pd.read_csv(p)
            for _, r in d.iterrows():
                rows.append({"ticker": r["ticker"], "name": r.get("name", ""),
                             "region": r.get("region", r.get("cluster", "")), "source": src,
                             "cluster": r.get("cluster", "")})

    df = pd.DataFrame(rows)
    if "cluster" not in df:
        df["cluster"] = ""
    df["cluster"] = df["cluster"].fillna("")
    # Duplikate zusammenführen: Cluster-Info aus themes behalten
    clusters = df[df["cluster"] != ""].drop_duplicates("ticker").set_index("ticker")["cluster"]
    df = df.drop_duplicates("ticker", keep="first").copy()
    df["cluster"] = df["ticker"].map(clusters).fillna("")
    df.to_csv(OUT, index=False)
    print(f"\nUniversum: {len(df)} eindeutige Ticker -> {OUT}")
    print(df.groupby("source").size().to_string())


if __name__ == "__main__":
    sys.exit(main())
