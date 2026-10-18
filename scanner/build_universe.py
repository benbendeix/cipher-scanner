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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sectors import CONTINENT, from_cluster, from_text, region_from_ticker  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNI_DIR = os.path.join(ROOT, "universe")
OUT = os.path.join(UNI_DIR, "universe.csv")
UA = {"User-Agent": "cipher-scanner/1.0 (personal research; github.com/benbendeix/cipher-scanner)"}

# name, url, suffix, region, mögliche Ticker-Spalten, mögliche Namens-Spalten
SOURCES = [
    ("S&P 500", "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", "", "USA", ["Symbol", "Ticker"], ["Security", "Company"]),
    ("S&P 400", "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies", "", "USA", ["Symbol", "Ticker symbol", "Ticker"], ["Security", "Company"]),
    ("DAX", "https://en.wikipedia.org/wiki/DAX", ".DE", "Deutschland", ["Ticker", "Symbol"], ["Company", "Name"]),
    ("MDAX", "https://en.wikipedia.org/wiki/MDAX", ".DE", "Deutschland", ["Ticker", "Symbol"], ["Company", "Name"]),
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
        if len(tb) < 10 or any(c.lower().startswith(("added", "removed")) for c in tb.columns):
            continue
        tcol = next((c for want in tcols for c in tb.columns if c.lower() == want.lower()), None)
        if tcol is None:
            tcol = next((c for want in tcols for c in tb.columns if want.lower() in c.lower()), None)
        if tcol is None:
            continue
        ncol = next((c for want in ncols for c in tb.columns if want.lower() in c.lower()), None)
        scol = next((c for c in tb.columns if "gics sector" in c.lower()), None) or \
            next((c for c in tb.columns if "sector" in c.lower() or "industry" in c.lower()), None)
        best = (tb, tcol, ncol, scol)
        break
    if best is None:
        cols = [list(_flatcols(t).columns)[:6] for t in tables if len(t) >= 10][:4]
        raise ValueError(f"keine passende Tabelle. Spalten: {cols}")
    tb, tcol, ncol, scol = best
    rows = []
    for _, r in tb.iterrows():
        t = _norm(r[tcol], suffix)
        if t:
            rows.append({"ticker": t, "name": str(r[ncol]) if ncol else "", "region": region, "source": name,
                         "sector_raw": str(r[scol]) if scol else ""})
    return rows


CACHE = os.path.join(UNI_DIR, "sector_cache.csv")


def _yf_sector(ticker):
    import yfinance as yf
    try:
        info = yf.Ticker(ticker).get_info()
    except Exception:
        return ""
    qt = str(info.get("quoteType", "")).upper()
    if qt in ("ETF", "INDEX", "MUTUALFUND", "FUTURE", "CURRENCY"):
        return "ETFs & Indizes" if qt != "FUTURE" else "Rohstoffe & Materialien"
    if qt == "CRYPTOCURRENCY":
        return "Krypto"
    return from_text(f"{info.get('sector', '')} {info.get('industry', '')}")


def add_sectors(df):
    """Reihenfolge: manuelle Zuordnung / Marktlandkarte-Cluster > Wikipedia > Cache > yfinance."""
    cache = pd.read_csv(CACHE).set_index("ticker")["sector"].to_dict() if os.path.exists(CACHE) else {}
    sectors, todo = [], []
    for _, r in df.iterrows():
        sec = from_cluster(r["ticker"], r.get("cluster", "")) or from_text(r.get("sector_raw", "")) \
            or cache.get(r["ticker"], "")
        if sec != sec:  # NaN aus Cache
            sec = ""
        if not sec:
            todo.append(r["ticker"])
        sectors.append(sec)
    df["sector"] = sectors
    print(f"\nBranchen: {len(df) - len(todo)} zugeordnet, {len(todo)} per yfinance nachschlagen ...")
    found = {}
    for i, t in enumerate(todo):
        found[t] = _yf_sector(t) or "Sonstige"
        if (i + 1) % 50 == 0:
            print(f"  {i + 1}/{len(todo)}")
    if found:
        df.loc[df["ticker"].isin(found), "sector"] = df["ticker"].map(found)
        cache.update(found)
        pd.DataFrame({"ticker": list(cache), "sector": list(cache.values())}).to_csv(CACHE, index=False)
    df.drop(columns=["sector_raw"], errors="ignore", inplace=True)


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
                             "region": r["region"] if "region" in d.columns else region_from_ticker(r["ticker"]),
                             "source": src, "cluster": r.get("cluster", ""), "sector_raw": ""})

    df = pd.DataFrame(rows)
    if "cluster" not in df:
        df["cluster"] = ""
    df["cluster"] = df["cluster"].fillna("")
    # Duplikate zusammenführen: Cluster-Info aus themes behalten
    clusters = df[df["cluster"] != ""].drop_duplicates("ticker").set_index("ticker")["cluster"]
    df = df.drop_duplicates("ticker", keep="first").copy()
    df["cluster"] = df["ticker"].map(clusters).fillna("")
    add_sectors(df)
    df["continent"] = df["region"].map(CONTINENT).fillna("Sonstige")
    df.to_csv(OUT, index=False)
    print(f"\nUniversum: {len(df)} eindeutige Ticker -> {OUT}")
    print(df.groupby("source").size().to_string())
    print("\nBranchen:\n" + df.groupby("sector").size().sort_values(ascending=False).to_string())


if __name__ == "__main__":
    sys.exit(main())
