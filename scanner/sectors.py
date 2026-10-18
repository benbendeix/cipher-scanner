"""Branchen- und Regions-Zuordnung (einheitliche deutsche Namen)."""
import re

SECTORS = [
    "Technologie", "Kommunikation & Medien", "Gesundheit", "Finanzen", "Immobilien",
    "Energie", "Versorger", "Rohstoffe & Materialien", "Industrie & Defense",
    "Konsum zyklisch", "Konsum defensiv", "Krypto", "ETFs & Indizes", "Sonstige",
]

# Reihenfolge wichtig: spezifische Begriffe zuerst
_KEYWORDS = [
    ("Immobilien", ["real estate", "reit", "property", "properties", "immobil"]),
    ("Versorger", ["utilit", "electricity", "water", "multi-utilit", "power generation"]),
    ("Konsum defensiv", ["consumer staples", "consumer defensive", "food", "beverage", "household",
                         "personal care", "tobacco", "drug retail", "supermarket", "brewer"]),
    ("Konsum zyklisch", ["consumer discretionary", "consumer cyclical", "automobile", "auto ", "autos",
                         "retail", "luxury", "apparel", "travel", "leisure", "hotel", "restaurant",
                         "homebuild", "household durables", "textile", "gaming", "casino", "consumer goods",
                         "consumer services"]),
    ("Gesundheit", ["health", "pharma", "biotech", "medical", "life science"]),
    ("Kommunikation & Medien", ["communication", "telecom", "media", "entertainment", "interactive"]),
    ("Technologie", ["information technology", "technology", "software", "semiconductor", "electronic",
                     "it services", "computer", "tech"]),
    ("Finanzen", ["financ", "bank", "insurance", "insurer", "capital market", "investment", "asset management",
                  "exchange"]),
    ("Energie", ["energy", "oil", "petroleum", "gas producer", "coal"]),
    ("Rohstoffe & Materialien", ["materials", "basic resource", "mining", "chemical", "metal", "steel",
                                 "construction material", "paper", "packaging", "gold", "silver"]),
    ("Industrie & Defense", ["industrial", "aerospace", "defen", "construction", "machinery", "transport",
                             "engineering", "logistics", "airline", "capital goods", "electrical equipment",
                             "conglomerate", "business services", "commercial services"]),
]

# Marktlandkarte-Cluster -> Branche (Präfix-Match, längster zuerst)
_CLUSTER = {
    "A6": "Kommunikation & Medien", "A": "Technologie",
    "B2": "Energie", "B3": "Energie", "B1": "Versorger", "B4": "Versorger",
    "C": "Rohstoffe & Materialien", "D": "Industrie & Defense", "E": "Finanzen", "F": "Gesundheit",
    "G1": "Konsum zyklisch", "G2": "Konsum defensiv", "H": "Immobilien", "I1": "Krypto",
    "I2": "Finanzen", "J": "Kommunikation & Medien", "ETF": "ETFs & Indizes", "Kompass": "ETFs & Indizes",
    "K2": "ETFs & Indizes", "L1": "ETFs & Indizes",
}

# Einzelne Werte, deren Cluster-Zuordnung irreführend wäre
_OVERRIDE = {
    "AMZN": "Konsum zyklisch", "GOOGL": "Kommunikation & Medien", "META": "Kommunikation & Medien",
    "TSLA": "Konsum zyklisch", "ETN": "Industrie & Defense", "UBER": "Industrie & Defense",
    "HOOD": "Finanzen", "COIN": "Finanzen", "PLTR": "Technologie", "BABA": "Konsum zyklisch",
    "PDD": "Konsum zyklisch", "JD": "Konsum zyklisch", "BIDU": "Kommunikation & Medien",
    "TCEHY": "Kommunikation & Medien", "1810.HK": "Technologie", "SE": "Konsum zyklisch",
    "MELI": "Konsum zyklisch", "XBI": "ETFs & Indizes",
}

_SUFFIX_REGION = {
    ".DE": "Deutschland", ".VI": "Österreich", ".L": "UK", ".PA": "Frankreich", ".SW": "Schweiz",
    ".AS": "Niederlande", ".MC": "Spanien", ".MI": "Italien", ".ST": "Schweden", ".CO": "Dänemark",
    ".OL": "Norwegen", ".HE": "Finnland", ".BR": "Belgien", ".HK": "Hongkong", ".T": "Japan",
    ".KS": "Korea", ".TW": "Taiwan", ".AX": "Australien", ".SI": "Singapur", ".NS": "Indien",
    ".TO": "Kanada",
}

CONTINENT = {
    "USA": "Nordamerika", "Kanada": "Nordamerika",
    "Deutschland": "Europa", "Österreich": "Europa", "UK": "Europa", "Frankreich": "Europa",
    "Schweiz": "Europa", "Niederlande": "Europa", "Spanien": "Europa", "Italien": "Europa",
    "Schweden": "Europa", "Dänemark": "Europa", "Norwegen": "Europa", "Finnland": "Europa", "Belgien": "Europa",
    "Hongkong": "Asien-Pazifik", "Japan": "Asien-Pazifik", "Korea": "Asien-Pazifik", "Taiwan": "Asien-Pazifik",
    "Australien": "Asien-Pazifik", "Singapur": "Asien-Pazifik", "Indien": "Asien-Pazifik",
    "Krypto": "Krypto", "Global": "Global",
}


def region_from_ticker(t: str) -> str:
    t = str(t)
    if t.endswith("-USD"):
        return "Krypto"
    if t.startswith("^") or t.endswith("=F") or t.endswith("=X") or t.endswith(".NYB"):
        return "Global"
    m = re.search(r"\.[A-Z]{1,2}$", t)
    if m and m.group(0) in _SUFFIX_REGION:
        return _SUFFIX_REGION[m.group(0)]
    return "USA"


def from_text(text) -> str:
    s = str(text or "").lower()
    if not s or s == "nan":
        return ""
    for sector, words in _KEYWORDS:
        if any(w in s for w in words):
            return sector
    return ""


def from_cluster(ticker, cluster) -> str:
    if ticker in _OVERRIDE:
        return _OVERRIDE[ticker]
    c = str(cluster or "").strip()
    if not c:
        return ""
    code = c.split()[0]
    for key in sorted(_CLUSTER, key=len, reverse=True):
        if code.startswith(key):
            return _CLUSTER[key]
    return ""
