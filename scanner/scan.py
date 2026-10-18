"""Cipher-B-Scanner (WaveTrend-Punkte).

python scanner/scan.py weekly    -> scannt das ganze Universum auf Wochenbasis
python scanner/scan.py daily     -> prüft die Weekly-Treffer der letzten Wochen + my_watchlist.txt auf Tagesbasis
python scanner/scan.py validate CLSK  -> gibt die letzten WaveTrend-Werte aus (Abgleich mit TradingView)
"""
import datetime as dt
import glob
import os
import sys
import time

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wavetrend import last_signal, wavetrend  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")
UNIVERSE = os.path.join(ROOT, "universe", "universe.csv")
MY_WATCH = os.path.join(ROOT, "universe", "my_watchlist.txt")
CHUNK = 80
WATCH_WEEKS = 4  # wie viele Wochen ein Weekly-Treffer im Daily-Check bleibt

TODAY = dt.datetime.now(dt.timezone.utc).date()


def is_crypto(t):
    return t.endswith("-USD")


def download(tickers, interval, period):
    """Lädt OHLCV in Paketen. Gibt dict ticker -> DataFrame zurück."""
    out = {}
    for i in range(0, len(tickers), CHUNK):
        chunk = tickers[i:i + CHUNK]
        for attempt in range(3):
            try:
                data = yf.download(chunk, period=period, interval=interval, group_by="ticker",
                                   auto_adjust=False, threads=True, progress=False)
                break
            except Exception as e:  # Netz-Hänger -> kurz warten, nochmal
                print(f"  Paket {i // CHUNK + 1}: Fehler {e!s:.60}, Versuch {attempt + 1}/3")
                time.sleep(10)
        else:
            continue
        for t in chunk:
            try:
                df = data[t] if len(chunk) > 1 else data
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(-1)
                df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["High", "Low", "Close"])
                if len(df):
                    out[t] = df
            except Exception:
                pass
        print(f"  {min(i + CHUNK, len(tickers))}/{len(tickers)} geladen, {len(out)} mit Daten")
        time.sleep(1)
    return out


def completed_only(df, t, interval):
    """Entfernt die noch laufende Kerze -> nur bestätigte Signale."""
    idx = pd.to_datetime(df.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    df = df.copy()
    df.index = idx
    if interval == "1wk":
        # Wochenkerze beginnt Montag. Aktien: fertig nach Freitag. Krypto: fertig nach Sonntag.
        days = 7 if is_crypto(t) else 5
        keep = [(d.date() + dt.timedelta(days=days)) <= TODAY for d in df.index]
    else:
        keep = [d.date() < TODAY for d in df.index]
    return df[keep]


def metrics(df):
    c = df["Close"]
    last = float(c.iloc[-1])
    chg = (last / float(c.iloc[-2]) - 1) * 100 if len(c) > 1 else 0.0
    vol = df["Volume"]
    vol_ratio = float(vol.iloc[-1] / vol.iloc[-21:-1].mean()) if vol.iloc[-21:-1].mean() > 0 else None
    hi = float(df["High"].iloc[-52:].max())
    ma200 = c.rolling(200).mean().iloc[-1] if len(c) >= 200 else None
    ma50 = c.rolling(50).mean().iloc[-1] if len(c) >= 50 else None
    return {
        "close": round(last, 2),
        "chg_pct": round(chg, 1),
        "vol_ratio": round(vol_ratio, 1) if vol_ratio else None,
        "vs_52hi_pct": round((last / hi - 1) * 100, 1),
        "above_ma50": None if ma50 is None else bool(last > ma50),
        "above_ma200": None if ma200 is None else bool(last > ma200),
    }


def run_scan(universe, interval, period):
    tickers = universe["ticker"].tolist()
    print(f"Lade {len(tickers)} Ticker ({interval}) ...")
    data = download(tickers, interval, period)
    info = universe.set_index("ticker")
    rows, states, missing = [], [], [t for t in tickers if t not in data]
    for t, df in data.items():
        df = completed_only(df, t, interval)
        if len(df) < 60:
            missing.append(t)
            continue
        r = info.loc[t]
        base = {"ticker": t, "name": r.get("name", ""), "region": r.get("region", ""),
                "cluster": r.get("cluster", ""), "sector": r.get("sector", ""), "continent": r.get("continent", "")}
        wt = wavetrend(df).dropna()
        if len(wt) >= 2:  # Zustand JEDES Werts -> Marktbreite
            w1, w2 = float(wt.wt1.iloc[-1]), float(wt.wt2.iloc[-1])
            states.append({**base, "wt1": round(w1, 2), "wt2": round(w2, 2),
                           "zone": "überverkauft" if w2 <= -53 else ("überkauft" if w2 >= 53 else "neutral"),
                           "momentum": "steigend" if w1 > w2 else "fallend",
                           "spark": [round(float(x), 2) for x in df["Close"].iloc[-30:]],
                           "spark_wt": [round(float(x), 1) for x in wt.wt2.iloc[-30:]], **metrics(df)})
        sig = last_signal(df)
        if sig:
            rows.append({**base, **sig, **metrics(df)})
    print(f"Fertig: {len(data)} mit Daten, {len(missing)} ohne Daten, {len(rows)} Signale")
    return pd.DataFrame(rows), missing, pd.DataFrame(states)


def sort_signals(df):
    if df.empty:
        return df
    df = df.copy()
    df["_s"] = (df["strength"] == "stark").astype(int)
    # grün: je tiefer überverkauft, desto weiter oben; rot: je höher überkauft, desto weiter oben
    df["_w"] = df.apply(lambda r: -r["wt2"] if r["dot"] == "green" else r["wt2"], axis=1)
    return df.sort_values(["dot", "_s", "_w"], ascending=[True, False, False]).drop(columns=["_s", "_w"])


def _table(g):
    out = ["| Ticker | Name | Region/Cluster | wt2 | Kurs | Δ% | Vol× | vs 52W-Hoch | >MA200 |",
           "|---|---|---|---|---|---|---|---|---|"]
    for _, r in g.iterrows():
        where = r["cluster"] if isinstance(r["cluster"], str) and r["cluster"] else r["region"]
        ma = "–" if r["above_ma200"] is None or pd.isna(r["above_ma200"]) else ("ja" if r["above_ma200"] else "nein")
        out.append(f"| {r['ticker']} | {str(r['name'])[:28]} | {where} | {r['wt2']} | {r['close']} | "
                   f"{r['chg_pct']} | {r['vol_ratio'] if pd.notna(r['vol_ratio']) and r['vol_ratio'] else '–'} | {r['vs_52hi_pct']}% | {ma} |")
    return out + [""]


def to_markdown(df, title, missing, cap=20):
    lines = [f"# {title}", "", f"Stand: {TODAY} · {len(df)} bestätigte Signale (vollständig in der CSV)", ""]
    if df.empty:
        return "\n".join(lines + ["_keine Signale_"]) + "\n"
    has_cluster = df["cluster"].fillna("").astype(str) != ""
    sections = [
        ("🟢 Stark grün – Kreuz im überverkauften Bereich (wt2 ≤ −53)", (df["dot"] == "green") & (df["strength"] == "stark"), None),
        ("🔴 Stark rot – Kreuz im überkauften Bereich (wt2 ≥ 53)", (df["dot"] == "red") & (df["strength"] == "stark"), None),
        ("⭐ Marktlandkarte – normale grüne Punkte", (df["dot"] == "green") & (df["strength"] == "normal") & has_cluster, None),
        ("⭐ Marktlandkarte – normale rote Punkte", (df["dot"] == "red") & (df["strength"] == "normal") & has_cluster, None),
        (f"🟢 Grün normal – Top {cap} (tiefster wt2)", (df["dot"] == "green") & (df["strength"] == "normal") & ~has_cluster, cap),
        (f"🔴 Rot normal – Top {cap} (höchster wt2)", (df["dot"] == "red") & (df["strength"] == "normal") & ~has_cluster, cap),
    ]
    for head, mask, limit in sections:
        g = df[mask]
        total = len(g)
        if limit:
            g = g.head(limit)
        lines.append(f"## {head} ({total})")
        lines += _table(g) if not g.empty else ["_keine_", ""]
    if missing:
        lines += [f"<details><summary>{len(missing)} Ticker ohne Daten</summary>", "", ", ".join(missing), "", "</details>"]
    return "\n".join(lines) + "\n"


def weekly():
    uni = pd.read_csv(UNIVERSE).fillna("")
    sig, missing, state = run_scan(uni, "1wk", "5y")
    sig = sort_signals(sig)
    state.to_json(os.path.join(RES, "state_weekly.json"), orient="records", force_ascii=False)
    os.makedirs(os.path.join(RES, "weekly"), exist_ok=True)
    sig.to_csv(os.path.join(RES, "weekly", f"{TODAY}.csv"), index=False)
    sig.to_csv(os.path.join(RES, "weekly_latest.csv"), index=False)
    with open(os.path.join(RES, "weekly_latest.md"), "w") as f:
        f.write(to_markdown(sig, "Cipher B · Weekly-Scan", missing))
    with open(os.path.join(RES, "missing_tickers.txt"), "w") as f:
        f.write("\n".join(missing))


def daily_watchlist(uni):
    files = sorted(glob.glob(os.path.join(RES, "weekly", "*.csv")))[-WATCH_WEEKS:]
    frames = [pd.read_csv(f).assign(weekly_date=os.path.basename(f)[:-4]) for f in files]
    frames = [f for f in frames if not f.empty]
    wk = pd.concat(frames) if frames else pd.DataFrame(columns=["ticker", "dot", "strength", "weekly_date"])
    if not wk.empty:  # nur starke Weekly-Signale + Marktlandkarte-Namen beobachten
        wk = wk[(wk["strength"] == "stark") | (wk["cluster"].fillna("").astype(str) != "")]
    wk = wk.sort_values("weekly_date").drop_duplicates("ticker", keep="last")
    wk = wk.rename(columns={"dot": "weekly_dot", "strength": "weekly_strength"})[
        ["ticker", "weekly_dot", "weekly_strength", "weekly_date"]]
    mine = []
    if os.path.exists(MY_WATCH):
        mine = [ln.split("#")[0].strip().upper() for ln in open(MY_WATCH)]
        mine = [m for m in mine if m]
    extra = pd.DataFrame({"ticker": [m for m in mine if m not in set(wk["ticker"])]})
    extra["weekly_dot"] = "manuell"
    wl = pd.concat([wk, extra], ignore_index=True)
    meta = uni.set_index("ticker")
    for col in ("name", "region", "cluster", "sector", "continent"):
        wl[col] = wl["ticker"].map(meta[col]) if col in meta else ""
    return wl.fillna("")


def daily():
    uni = pd.read_csv(UNIVERSE).fillna("")
    wl = daily_watchlist(uni)
    os.makedirs(RES, exist_ok=True)
    wl.to_csv(os.path.join(RES, "daily_watchlist.csv"), index=False)
    if wl.empty:
        print("Watchlist leer – erst einen Weekly-Scan laufen lassen.")
        return
    cols = [c for c in ("ticker", "name", "region", "cluster", "sector", "continent") if c in wl.columns]
    sig, missing, state = run_scan(wl[cols], "1d", "2y")
    state.to_json(os.path.join(RES, "state_daily.json"), orient="records", force_ascii=False)
    if not sig.empty:
        sig = sig.merge(wl[["ticker", "weekly_dot", "weekly_strength", "weekly_date"]], on="ticker", how="left")
        # Bestätigung: Daily-Punkt in dieselbe Richtung wie der Weekly-Punkt
        sig["passt_zu_weekly"] = sig["dot"] == sig["weekly_dot"]
    sig = sort_signals(sig)
    os.makedirs(os.path.join(RES, "daily"), exist_ok=True)
    sig.to_csv(os.path.join(RES, "daily", f"{TODAY}.csv"), index=False)
    sig.to_csv(os.path.join(RES, "daily_latest.csv"), index=False)
    md = to_markdown(sig, f"Cipher B · Daily-Check ({len(wl)} Werte auf der Watchlist)", missing)
    if not sig.empty:
        ok = sig[sig["passt_zu_weekly"] == True]  # noqa: E712
        head = ["## ✅ Bestätigt: Daily-Punkt in Richtung des Weekly-Punkts (" + str(len(ok)) + ")"]
        if ok.empty:
            head += ["_keine_", ""]
        else:
            head += ["| Ticker | Name | Daily | wt2 daily | Weekly (Datum) | Kurs |", "|---|---|---|---|---|---|"]
            for _, r in ok.iterrows():
                d = ("🟢" if r["dot"] == "green" else "🔴") + (" stark" if r["strength"] == "stark" else "")
                w = ("🟢" if r["weekly_dot"] == "green" else "🔴") + (" stark" if r["weekly_strength"] == "stark" else "") + f" ({r['weekly_date']})"
                head.append(f"| {r['ticker']} | {str(r['name'])[:28]} | {d} | {r['wt2']} | {w} | {r['close']} |")
            head.append("")
        parts = md.split("\n## ", 1)
        md = parts[0] + "\n" + "\n".join(head) + "\n## " + parts[1] if len(parts) == 2 else md + "\n".join(head)
    with open(os.path.join(RES, "daily_latest.md"), "w") as f:
        f.write(md)


def validate(ticker):
    for interval, period in (("1d", "2y"), ("1wk", "5y")):
        data = download([ticker], interval, period)
        if ticker not in data:
            print(f"{ticker}: keine Daten ({interval})")
            continue
        df = completed_only(data[ticker], ticker, interval)
        wt = wavetrend(df).round(2)
        print(f"\n== {ticker} {interval}: letzte 8 Kerzen ==")
        print(pd.concat([df[["High", "Low", "Close"]].round(2), wt], axis=1).tail(8).to_string())
        print("Signal letzte Kerze:", last_signal(df))


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "weekly"
    if mode == "weekly":
        weekly()
    elif mode == "daily":
        daily()
    elif mode == "validate":
        for t in sys.argv[2:] or ["CLSK"]:
            validate(t)
    else:
        sys.exit(f"Unbekannter Modus: {mode}")
