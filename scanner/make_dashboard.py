"""Bündelt Universum, Weekly-/Daily-Ergebnisse und Marktbreite zu results/dashboard.json."""
import datetime as dt
import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")


def _load_json(name):
    p = os.path.join(RES, name)
    return pd.read_json(p, orient="records") if os.path.exists(p) and os.path.getsize(p) > 2 else pd.DataFrame()


def _load_csv(name):
    p = os.path.join(RES, name)
    try:
        return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _clean(v):
    if isinstance(v, float) and v != v:
        return None
    if hasattr(v, "item"):
        return v.item()
    return v


def records(df, cols):
    cols = [c for c in cols if c in df.columns]
    return [{c: _clean(r[c]) for c in cols} for _, r in df[cols].iterrows()]


def breadth(state, sig, key):
    out = []
    if state.empty:
        return out
    for k, g in state.groupby(key):
        s = sig[sig[key] == k] if not sig.empty and key in sig else pd.DataFrame()
        cnt = lambda d, st: int(((s["dot"] == d) & (s["strength"] == st)).sum()) if not s.empty else 0  # noqa: E731
        out.append({
            "name": k, "n": int(len(g)),
            "oversold": int((g["zone"] == "überverkauft").sum()),
            "overbought": int((g["zone"] == "überkauft").sum()),
            "rising_pct": round(float((g["momentum"] == "steigend").mean() * 100), 0),
            "above_ma200_pct": round(float(g["above_ma200"].dropna().astype(bool).mean() * 100), 0)
            if g["above_ma200"].notna().any() else None,
            "avg_wt2": round(float(g["wt2"].mean()), 1),
            "green_strong": cnt("green", "stark"), "green": cnt("green", "normal"),
            "red_strong": cnt("red", "stark"), "red": cnt("red", "normal"),
        })
    return sorted(out, key=lambda x: x["avg_wt2"])


def setups(sig, daily, state):
    """Regelbasierter Score – Konfluenz statt Einzelsignal."""
    if sig.empty:
        return [], []
    d = daily.set_index("ticker") if not daily.empty else pd.DataFrame()
    st = state.set_index("ticker") if not state.empty else pd.DataFrame()
    longs, warns = [], []
    for _, r in sig.iterrows():
        if r.get("sector") == "ETFs & Indizes":
            continue
        reasons, score = [], 0
        green = r["dot"] == "green"
        if r["strength"] == "stark":
            score += 3
            reasons.append("Weekly-Kreuz " + ("tief überverkauft" if green else "hoch überkauft"))
        else:
            score += 1
            reasons.append("Weekly-Kreuz " + ("grün" if green else "rot"))
        if r["ticker"] in d.index:
            dd = d.loc[r["ticker"]]
            if dd["dot"] == r["dot"]:
                score += 3
                reasons.append("Daily bestätigt")
        if (green and r["wt2"] <= -70) or (not green and r["wt2"] >= 70):
            score += 1
            reasons.append(f"Extrem (wt2 {r['wt2']})")
        ma = r.get("above_ma200")
        if ma == ma and ma is not None:
            if green and bool(ma):
                score += 1
                reasons.append("über MA200 (Trend intakt)")
            if not green and not bool(ma):
                score += 1
                reasons.append("unter MA200")
        vr = r.get("vol_ratio")
        if vr == vr and vr and vr >= 1.5:
            score += 1
            reasons.append(f"Volumen {vr}×")
        item = {"ticker": r["ticker"], "name": r["name"], "sector": r.get("sector", ""),
                "region": r.get("region", ""), "cluster": _clean(r.get("cluster", "")), "dot": r["dot"],
                "strength": r["strength"], "wt2": r["wt2"], "close": r["close"], "chg_pct": r["chg_pct"],
                "vs_52hi_pct": r["vs_52hi_pct"], "score": score, "reasons": reasons}
        (longs if green else warns).append(item)
    key = lambda x: (-x["score"], x["wt2"])  # noqa: E731
    return sorted(longs, key=key)[:15], sorted(warns, key=lambda x: (-x["score"], -x["wt2"]))[:15]


def main():
    uni = pd.read_csv(os.path.join(ROOT, "universe", "universe.csv")).fillna("")
    sig = _load_csv("weekly_latest.csv")
    daily = _load_csv("daily_latest.csv")
    state = _load_json("state_weekly.json")
    meta = uni.set_index("ticker")
    for df in (sig, daily, state):
        if not df.empty:
            for col in ("sector", "continent", "region", "cluster"):
                if col in meta:
                    df[col] = df["ticker"].map(meta[col]).fillna("")
    asof = ""
    md = os.path.join(RES, "weekly_latest.md")
    if os.path.exists(md):
        for line in open(md):
            if line.startswith("Stand:"):
                asof = line.split("·")[0].replace("Stand:", "").strip()
    sig_cols = ["ticker", "name", "sector", "region", "continent", "cluster", "dot", "strength", "wt1", "wt2",
                "close", "chg_pct", "vol_ratio", "vs_52hi_pct", "above_ma50", "above_ma200"]
    longs, warns = setups(sig, daily, state)
    spark_for = set(sig["ticker"]) if not sig.empty else set()
    spark = {}
    if not state.empty:
        for _, r in state[state["ticker"].isin(spark_for)].iterrows():
            spark[r["ticker"]] = {"c": r["spark"], "w": r["spark_wt"]}
    data = {
        "asof": asof or str(dt.date.today()),
        "generated": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "universe": int(len(uni)),
        "scanned": int(len(state)),
        "overall": breadth(state.assign(all="Gesamt"), sig.assign(all="Gesamt") if not sig.empty else sig, "all"),
        "by_sector": breadth(state, sig, "sector"),
        "by_continent": breadth(state, sig, "continent"),
        "weekly": records(sig, sig_cols),
        "daily": records(daily, sig_cols + ["weekly_dot", "weekly_strength", "weekly_date", "passt_zu_weekly"]),
        "setups_long": longs,
        "setups_warn": warns,
        "spark": spark,
    }
    with open(os.path.join(RES, "dashboard.json"), "w") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"dashboard.json: {len(data['weekly'])} Weekly, {len(data['daily'])} Daily, "
          f"{len(data['by_sector'])} Branchen, {os.path.getsize(os.path.join(RES, 'dashboard.json')) // 1024} KB")


if __name__ == "__main__":
    main()
