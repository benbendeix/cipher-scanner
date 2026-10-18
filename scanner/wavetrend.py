"""WaveTrend wie im VuManChu Cipher B (Standard-Parameter 9 / 12 / hlc3 / 3)."""
import pandas as pd

CHANNEL_LEN = 9
AVERAGE_LEN = 12
MA_LEN = 3
OB_LEVEL = 53    # überkauft (Level 1)
OB_LEVEL2 = 60
OS_LEVEL = -53   # überverkauft (Level 1)
OS_LEVEL2 = -60


def _ema(s: pd.Series, n: int) -> pd.Series:
    # Pine ta.ema: alpha = 2/(n+1), rekursiv
    return s.ewm(span=n, adjust=False).mean()


def wavetrend(df: pd.DataFrame) -> pd.DataFrame:
    """df braucht Spalten High, Low, Close. Gibt wt1, wt2 zurück."""
    src = (df["High"] + df["Low"] + df["Close"]) / 3.0
    esa = _ema(src, CHANNEL_LEN)
    de = _ema((src - esa).abs(), CHANNEL_LEN)
    ci = (src - esa) / (0.015 * de)
    wt1 = _ema(ci, AVERAGE_LEN)
    wt2 = wt1.rolling(MA_LEN).mean()
    return pd.DataFrame({"wt1": wt1, "wt2": wt2}, index=df.index)


def last_signal(df: pd.DataFrame):
    """Prüft, ob auf der LETZTEN Kerze von df ein Kreuz entstanden ist.

    df muss nur abgeschlossene Kerzen enthalten (das stellt scan.py sicher).
    Rückgabe: dict oder None.
      dot: 'green' (wt1 kreuzt wt2 nach oben) / 'red' (nach unten)
      strength: 'stark' wenn im überverkauften (grün) / überkauften (rot) Bereich
    """
    if len(df) < 60:
        return None
    wt = wavetrend(df).dropna()
    if len(wt) < 2:
        return None
    p, c = wt.iloc[-2], wt.iloc[-1]
    prev_diff = p.wt1 - p.wt2
    diff = c.wt1 - c.wt2
    if prev_diff <= 0 < diff:
        dot = "green"
        strong = c.wt2 <= OS_LEVEL
    elif prev_diff >= 0 > diff:
        dot = "red"
        strong = c.wt2 >= OB_LEVEL
    else:
        return None
    return {
        "dot": dot,
        "strength": "stark" if strong else "normal",
        "wt1": round(float(c.wt1), 2),
        "wt2": round(float(c.wt2), 2),
        "date": str(wt.index[-1].date()),
    }
