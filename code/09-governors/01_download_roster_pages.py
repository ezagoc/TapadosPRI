"""Download the Wikipedia pages that list each state's governors (1930s-2000), as raw HTML, for the governor roster.

For every state it tries, in order, the Spanish annex of the state's rulers, the Spanish list of governors, and the
English "Governor of <state>" page, and keeps every page that exists (they are cross-checked against each other, against
Camp's governor records and against Magar's elected incumbents in 02_*). Requests are sequential, 3 seconds apart, with
the project's User-Agent, and retried after the server's Retry-After on HTTP 429. Pages already on disk are not fetched.
Output: DATA_DIR/governors/wikipedia_raw/<lang>__<title>.html and MANIFEST.csv
Run: python code/09-governors/01_download_roster_pages.py
"""
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import DATA_DIR  # noqa: E402

OUT = DATA_DIR / "governors" / "wikipedia_raw"
OUT.mkdir(parents=True, exist_ok=True)
UA = "TapadosPRI-research/0.1 (https://github.com/ezagoc/TapadosPRI; academic research on Mexican political history)"
STATES = {  # name in Spanish titles, name in English titles
    "Aguascalientes": "Aguascalientes", "Baja California": "Baja California", "Baja California Sur": "Baja California Sur",
    "Campeche": "Campeche", "Coahuila": "Coahuila", "Colima": "Colima", "Chiapas": "Chiapas", "Chihuahua": "Chihuahua",
    "la Ciudad de México": "Mexico City", "Durango": "Durango", "Guanajuato": "Guanajuato", "Guerrero": "Guerrero",
    "Hidalgo": "Hidalgo", "Jalisco": "Jalisco", "el Estado de México": "the State of Mexico", "Michoacán": "Michoacán",
    "Morelos": "Morelos", "Nayarit": "Nayarit", "Nuevo León": "Nuevo León", "Oaxaca": "Oaxaca", "Puebla": "Puebla",
    "Querétaro": "Querétaro", "Quintana Roo": "Quintana Roo", "San Luis Potosí": "San Luis Potosí", "Sinaloa": "Sinaloa",
    "Sonora": "Sonora", "Tabasco": "Tabasco", "Tamaulipas": "Tamaulipas", "Tlaxcala": "Tlaxcala", "Veracruz": "Veracruz",
    "Yucatán": "Yucatán", "Zacatecas": "Zacatecas"}


def api(lang, params):
    url = f"https://{lang}.wikipedia.org/w/api.php?" + urllib.parse.urlencode({**params, "format": "json", "formatversion": 2})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60) as r:
                time.sleep(3)
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            wait = int(e.headers.get("Retry-After", 30 * (attempt + 1))) if e.code == 429 else 10 * (attempt + 1)
            print(f"  HTTP {e.code}; waiting {wait}s", flush=True)
            time.sleep(wait)
    raise RuntimeError(url)


rows = []
for es, en in STATES.items():
    for lang, title in [("es", f"Anexo:Gobernantes de {es}".replace("de el ", "del ")),
                        ("es", f"Anexo:Gobernadores de {es}".replace("de el ", "del ")),
                        ("en", f"Governor of {en}"), ("en", f"List of governors of {en}")]:
        path = OUT / f"{lang}__{title.replace('/', '_').replace(' ', '_')}.html"
        if path.exists():
            rows.append(dict(state=en, lang=lang, title=title, file=path.name, status="cached"))
            continue
        q = api(lang, {"action": "query", "titles": title, "redirects": 1})
        page = q["query"]["pages"][0]
        if page.get("missing"):
            rows.append(dict(state=en, lang=lang, title=title, file="", status="missing"))
            continue
        p = api(lang, {"action": "parse", "page": page["title"], "prop": "text|revid"})
        path.write_text(p["parse"]["text"], encoding="utf-8")
        rows.append(dict(state=en, lang=lang, title=page["title"], file=path.name, status=f"revid {p['parse'].get('revid')}"))
        print(f"{en:22s} {lang} {page['title']}", flush=True)
with open(OUT / "MANIFEST.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
print("states with at least one page:", len({r["state"] for r in rows if r["file"]}), "of", len(STATES))
