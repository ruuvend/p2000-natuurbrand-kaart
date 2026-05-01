#!/usr/bin/env python3
"""
Haalt P2000 brandweermeldingen op via RSS en slaat natuurbranden op in data/meldingen.json.
Bewaart de laatste 12 uur aan meldingen.
"""

import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

# ── Instellingen ──────────────────────────────────────────────────────────────

RSS_URLS = [
    'https://112-nu.nl/brandweer/rss',
    'https://112-nu.nl/hulpdiensten/rss',
]

BRAND_TERMEN = [
    'berm/bosschage', 'bosschage',
    'br bos', 'br heide', 'br duin', 'br berm', 'br veen', 'br gras', 'br riet',
    'brand bos', 'brand heide', 'brand duin', 'brand berm',
    'brand veen', 'brand gras', 'brand riet',
    'brandmelding buiten', 'brand buiten',
    'nwbrrn', 'natuurbrand', 'bermbrand', 'heidebrand',
    'veenbrand', 'bosbrand', 'grasbrand', 'rietbrand', 'duinbrand',
]

UITSLUITINGEN = [
    'vrijhouden', 'testmelding', 'proefalarm',
    'brandmelding woning', 'woning (dak)', 'woning (brand)',
    'brandmelding wegvervoer', 'wegvervoer',
    'trioworld', 'liftopsluiting', 'gaslucht', 'stank/hind',
    'assistentie ambu', 'afhijsen', 'handmelder',
    'openbaar meldsysteem', 'intrekken alarm',
    'brandgerucht', 'nacontrole',
]

DATA_FILE = 'data/meldingen.json'
BEWAAR_UREN = 12

# ── Hulpfuncties ──────────────────────────────────────────────────────────────

def is_natuurbrand(tekst: str) -> bool:
    t = tekst.lower()
    heeft_term = any(term in t for term in BRAND_TERMEN)
    heeft_uitsluiting = any(u in t for u in UITSLUITINGEN)
    return heeft_term and not heeft_uitsluiting


def parse_rss(url: str) -> list[dict]:
    """Haalt RSS feed op en geeft lijst van items terug."""
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
            # Zorg voor timezone-aware datetime in UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            iso = dt.astimezone(timezone.utc).isoformat()
        except Exception:
            iso = datetime.now(timezone.utc).isoformat()

        items.append({
            'title': title,
            'description': desc,
            'link': link,
            'pubDate': iso,
        })

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
    nu = datetime.now(timezone.utc)
    grens = nu - timedelta(hours=BEWAAR_UREN)

    # Laad bestaande meldingen
    bestaande = laad_bestaande(DATA_FILE)
    print(f'Bestaande meldingen: {len(bestaande)}')

    # Maak een set van bestaande links om duplicaten te voorkomen
    bestaande_links = {m['link'] for m in bestaande}

    # Haal nieuwe meldingen op uit alle feeds
    nieuw = 0
    for url in RSS_URLS:
        items = parse_rss(url)
        print(f'{url}: {len(items)} items opgehaald')
        for item in items:
            tekst = item['title'] + ' ' + item['description']
            if item['link'] in bestaande_links:
                continue  # al bekend
            if not is_natuurbrand(tekst):
                continue  # geen natuurbrand
            print(f'  ✅ Nieuwe melding: {item["title"][:80]}')
            bestaande.append(item)
            bestaande_links.add(item['link'])
            nieuw += 1

    # Verwijder meldingen ouder dan 12 uur
    voor_opschonen = len(bestaande)
    bestaande = [
        m for m in bestaande
        if datetime.fromisoformat(m['pubDate']) >= grens
    ]
    opgeschoond = voor_opschonen - len(bestaande)

    # Sorteer op tijd (nieuwste eerst)
    bestaande.sort(key=lambda m: m['pubDate'], reverse=True)

    print(f'Nieuw: {nieuw} | Opgeschoond: {opgeschoond} | Totaal: {len(bestaande)}')
    sla_op(DATA_FILE, bestaande)
    print(f'Opgeslagen in {DATA_FILE}')


if __name__ == '__main__':
    main()
