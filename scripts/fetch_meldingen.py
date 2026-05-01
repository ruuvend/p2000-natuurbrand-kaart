name: P2000 Meldingen Ophalen
on:
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch:
jobs:
  fetch:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - run: python3 scripts/fetch_meldingen.py
      - run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/meldingen.json data/geocache.json
          git diff --cached --quiet || git commit -m "Update meldingen $(date -u '+%Y-%m-%d %H:%M') UTC"
          git push
