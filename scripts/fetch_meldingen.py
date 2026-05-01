#!/usr/bin/env python3
"""
Haalt P2000 brandweermeldingen op via RSS, geocodeert de locaties,
en slaat alles op in data/meldingen.json inclusief lat/lon.
Bewaart de laatste 30 dagen aan meldingen.
"""

import json
import os
import time
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

# ── Instellingen ──────────────────────────────────────────────────────────────

RSS_URLS = [
    'https://112-nu.nl/brandweer/rss',
    'https://112-nu.nl/hulpdiensten/rss',
]

BRAND_TERMEN = [
    # Officiële P2000-codes voor échte natuurbranden
    'br bos',        # bosbrand
    'br heide',      # heidebrand
    'br duin',       # duinbrand
    'br veen',       # veenbrand
    # Uitgeschreven varianten
    'brand bos', 'brand heide', 'brand duin', 'brand veen',
    'bosbrand', 'heidebrand', 'veenbrand', 'duinbrand',
    'natuurbrand', 'nwbrrn',
]

UITSLUITINGEN = [
    # Geen berm/bosschage, gras, riet — dat zijn geen echte natuurbranden
    'berm', 'bosschage', 'br berm', 'br gras', 'br riet',
    'bermbrand', 'grasbrand', 'rietbrand',
    'brand buiten', 'brandmelding buiten',
    # Overige uitsluitingen
    'vrijhouden', 'testmelding', 'proefalarm',
    'brandmelding woning', 'woning (dak)', 'woning (brand)',
    'brandmelding wegvervoer', 'wegvervoer',
    'trioworld', 'liftopsluiting', 'gaslucht', 'stank/hind',
    'assistentie ambu', 'afhijsen', 'handmelder',
    'openbaar meldsysteem', 'intrekken alarm',
    'brandgerucht', 'nacontrole',
]

DATA_FILE    = 'data/meldingen.json'
GEO_CACHE    = 'data/geocache.json'
BEWAAR_DAGEN = 30   # bewaar 30 dagen geschiedenis

# ── Geocodering via Nominatim ─────────────────────────────────────────────────

def laad_geocache() -> dict:
    if not os.path.exists(GEO_CACHE):
        return {}
    try:
        with open(GEO_CACHE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

def sla_geocache_op(cache: dict):
    os.makedirs(os.path.dirname(GEO_CACHE), exist_ok=True)
    with open(GEO_CACHE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

def geocodeer(plaatsnaam: str) -> dict | None:
    """Zoek lat/lon op via Nominatim (OpenStreetMap). Geeft None terug bij mislukking."""
    query = urllib.parse.quote(plaatsnaam + ', Nederland')
    url = f'https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1&countrycodes=nl'
    headers = {
        'User-Agent': 'p2000-natuurbrand-kaart/1.0',
        'Accept-Language': 'nl',
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            resultaten = json.loads(resp.read())
        if resultaten:
            return {'lat': float(resultaten[0]['lat']), 'lon': float(resultaten[0]['lon'])}
    except Exception as e:
        print(f'  Geocodeer fout voor "{plaatsnaam}": {e}')
    return None

def extract_locatie(description: str) -> tuple[str, str]:
    """Haal straatnaam en plaatsnaam uit description. Geeft (straat, plaats) terug.
    Voorbeelden:
    'P 2 BLB-02 BR berm/bosschage N266 Rijksweg Noord 64,0 Nederweert 234131'
        → ('Rijksweg Noord', 'Nederweert')
    'P 1 BDH-03 BR berm/bosschage Jean Monnetpad s-Gravenhage 157730'
        → ('Jean Monnetpad', 's-Gravenhage')
    'P 1 BON-08 (Pel. GW NBB 1) BR bos (Uitbr.: hoog) Paasloerweg Paasloo'
        → ('Paasloerweg', 'Paasloo')
    """
    import re
    schoon = re.sub(r'<[^>]+>', '', description).strip()

    # Verwijder incidentnummers aan het einde
    schoon = re.sub(r'(\s+\d+)+\s*$', '', schoon).strip()
    # Verwijder 2-letter provincie-afkorting aan het einde (GE, NB, ZH etc.)
    schoon = re.sub(r'\s+[A-Z]{2}$', '', schoon).strip()
    # Verwijder het P2000-prefix inclusief eenheidscode: "P 1 BON-08 (Pel. GW NBB 1) BR bos"
    schoon = re.sub(r'^P\s+\d+\s+[\w/-]+(\s+\([^)]+\))?\s+BR\s+[\w/]+(\s+\([^)]+\))?\s*', '', schoon, flags=re.IGNORECASE).strip()
    # Fallback: verwijder alles t/m het eerste BR-trefwoord (inclusief haakjes erna)
    for term in ['br bos','br heide','br duin','br berm','br veen','br gras','br riet','nwbrrn','natuurbrand','bos (uitbr','heide (uitbr']:
        idx = schoon.lower().find(term)
        if idx != -1:
            schoon = schoon[idx + len(term):].strip()
            # Verwijder ook resterende haakjes-inhoud aan het begin zoals "(Uitbr.: hoog)"
            schoon = re.sub(r'^\([^)]*\)\s*', '', schoon).strip()
            break

    straat_suffixes = ['straat','weg','laan','pad','dijk','kade','plein',
                       'singel','gracht','dreef','baan','steeg','allee']

    delen = schoon.split()
    plaats_idx = None
    plaats = ''
    for i in range(len(delen) - 1, -1, -1):
        woord = delen[i].lower().rstrip('.,)')
        if not woord or woord[0].isdigit() or woord.startswith('('):
            continue
        if any(woord.endswith(s) for s in straat_suffixes):
            continue
        # Samengestelde plaatsnaam met 's- prefix
        if i > 0 and delen[i-1] in ["'s-", "'s"]:
            plaats = delen[i-1] + delen[i]
            plaats_idx = i - 1
        else:
            plaats = delen[i]
            plaats_idx = i
        break

    if plaats_idx is None:
        return ('', delen[-1] if delen else '')

    # Straatnaam = alles voor de plaatsnaam
    straat_delen = list(delen[:plaats_idx])
    # Verwijder rijkswegen (A6, N266), richtingen (Li, Re) en hectometerpalen aan het begin
    while straat_delen and (
        re.match(r'^[AN]\d+$', straat_delen[0]) or
        straat_delen[0] in ['Li', 'Re', '-'] or
        re.match(r'^\d+[,.]\d+$', straat_delen[0]) or
        straat_delen[0][0].isdigit() or
        straat_delen[0].startswith('(')
    ):
        straat_delen.pop(0)
    # Verwijder losse hectometerpalen en haakjes-stukken
    straat_delen = [d for d in straat_delen if not re.match(r'^\d+[,.]\d+$', d) and not d.startswith('(')]

    straat = ' '.join(straat_delen).strip(' ,.-')
    return (straat, plaats)


# Wrapper voor achterwaartse compatibiliteit
def extract_plaats(description: str) -> str:
    _, plaats = extract_locatie(description)
    return plaats

# ── RSS ophalen ───────────────────────────────────────────────────────────────

def is_natuurbrand(tekst: str) -> bool:
    t = tekst.lower()
    heeft_term = any(term in t for term in BRAND_TERMEN)
    heeft_uitsluiting = any(u in t for u in UITSLUITINGEN)
    return heeft_term and not heeft_uitsluiting

def parse_rss(url: str) -> list[dict]:
    headers = {'User-Agent': 'p2000-natuurbrand-kaart/1.0'}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
    except Exception as e:
        print(f'Fout bij ophalen {url}: {e}')
        return []

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        print(f'XML parse fout: {e}')
        return []

    items = []
    for item in root.findall('.//item'):
        title = (item.findtext('title') or '').strip()
        desc  = (item.findtext('description') or '').strip()
        link  = (item.findtext('link') or '').strip()
        pub   = (item.findtext('pubDate') or '').strip()

        try:
            dt = parsedate_to_datetime(pub)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            # Bewaar originele tijd — niet omzetten naar UTC
            iso = dt.isoformat()
        except Exception:
            iso = datetime.now(timezone.utc).isoformat()

        items.append({'title': title, 'description': desc, 'link': link, 'pubDate': iso})

    return items

def laad_bestaande(pad: str) -> list[dict]:
    if not os.path.exists(pad):
        return []
    try:
        with open(pad, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def sla_op(pad: str, meldingen: list[dict]):
    os.makedirs(os.path.dirname(pad), exist_ok=True)
    with open(pad, 'w', encoding='utf-8') as f:
        json.dump(meldingen, f, ensure_ascii=False, indent=2)

# ── Hoofdprogramma ────────────────────────────────────────────────────────────

def main():
    nu    = datetime.now(timezone.utc)
    grens = nu - timedelta(days=BEWAAR_DAGEN)

    bestaande      = laad_bestaande(DATA_FILE)
    geocache       = laad_geocache()
    bestaande_links = {m['link'] for m in bestaande}

    print(f'Bestaande meldingen: {len(bestaande)} | Geocache: {len(geocache)} plaatsen')

    # Haal nieuwe meldingen op
    nieuw = 0
    for url in RSS_URLS:
        items = parse_rss(url)
        print(f'{url}: {len(items)} items')
        for item in items:
            tekst = item['title'] + ' ' + item['description']
            if item['link'] in bestaande_links:
                continue
            if not is_natuurbrand(tekst):
                continue

            # Geocodeer de locatie (straat + plaats voor nauwkeurigheid)
            straat, plaats = extract_locatie(item['description'])
            print(f'  ✅ Nieuw: {item["title"][:70]}')
            print(f'     Straat: "{straat}" | Plaats: "{plaats}"')

            # Probeer eerst straat + plaats, dan alleen plaats als fallback
            cache_key = f'{straat}, {plaats}' if straat else plaats
            if cache_key and cache_key not in geocache:
                coords = geocodeer(cache_key)
                if coords:
                    geocache[cache_key] = coords
                    print(f'     📍 Geocodeerd: {cache_key} → {coords}')
                elif straat:
                    # Fallback: alleen plaatsnaam
                    coords = geocodeer(plaats)
                    if coords:
                        geocache[cache_key] = coords
                        print(f'     📍 Fallback geocodeerd: {plaats} → {coords}')
                    else:
                        print(f'     ⚠️  Geocodering mislukt voor: {cache_key}')
                time.sleep(1)  # Nominatim fair-use: max 1 req/sec

            coords = geocache.get(cache_key)
            item['plaats'] = plaats
            item['straat'] = straat
            item['lat']    = coords['lat'] if coords else None
            item['lon']    = coords['lon'] if coords else None

            bestaande.append(item)
            bestaande_links.add(item['link'])
            nieuw += 1

    # Opschonen: ouder dan 30 dagen verwijderen
    voor = len(bestaande)
    bestaande = [
        m for m in bestaande
        if datetime.fromisoformat(m['pubDate']).astimezone(timezone.utc) >= grens
    ]
    print(f'Nieuw: {nieuw} | Opgeschoond: {voor - len(bestaande)} | Totaal: {len(bestaande)}')

    # Sorteer nieuwste eerst
    bestaande.sort(key=lambda m: m['pubDate'], reverse=True)

    sla_op(DATA_FILE, bestaande)
    sla_geocache_op(geocache)
    print(f'✅ Klaar — {DATA_FILE} bijgewerkt')

if __name__ == '__main__':
    main()
