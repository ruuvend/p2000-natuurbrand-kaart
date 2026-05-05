# 🔥 P2000 Natuurbranden — Live Kaart

Een live interactieve kaart die P2000 meldingen van natuurbranden in Nederland toont van het **afgelopen uur**.

## Functies

- **Live meldingen** — haalt automatisch de meest recente P2000 meldingen op via AI websearch
- **Slim samenvoegen** — meldingen binnen een straal van 10 km worden samengevoegd tot één marker
- **Automatisch vernieuwen** — elke 5 minuten worden nieuwe meldingen opgehaald
- **Interactieve kaart** — klik op een marker of kaartje voor details
- **Kleurintensiteit** — markers worden groter en donkerder naarmate er meer meldingen zijn

## Gebruik

1. Open `index.html` in een webbrowser
2. De kaart laadt automatisch de meest recente meldingen
3. Klik op een rode cirkel op de kaart voor meer informatie
4. Gebruik de zijbalk rechts voor een overzicht van alle meldingen

## Techniek

- [Leaflet.js](https://leafletjs.com/) — interactieve kaart
- [OpenStreetMap](https://openstreetmap.org/) — kaartlagen
- websearch voor P2000 meldingen
- Haversine-formule voor afstandsberekening tussen meldingen

