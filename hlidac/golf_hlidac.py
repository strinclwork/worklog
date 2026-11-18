#!/usr/bin/env python3
"""Hlídač inzerátů: VW Golf VII 1.2 TSI hatchback, max 190 000 km, max 230 000 Kč.

Zdroje: sauto.cz (JSON API) a auto.bazos.cz (HTML).
Nové inzeráty porovnává se souborem seen.json (ID už viděných inzerátů).

Použití:
  python golf_hlidac.py            # najde nové, vypíše je a uloží seen.json + posledni.md
  python golf_hlidac.py --dry-run  # jen ukáže, nic neuloží
  python golf_hlidac.py --vse      # vypíše všechny vyhovující (nejen nové), nic neuloží
"""
import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

# ---------------- KONFIGURACE ----------------
MAX_KM = 190_000
MAX_CENA = 230_000
MIN_CENA = 40_000      # Bazoš: odfiltruje díly a příslušenství
ROK_OD = 2013          # Golf VII 1.2 TSI: výroba cca 11/2012 až 2017
ROK_2012_POVOLIT = True  # 2012 projde jen se zmínkou VII/7 nebo s 1. registrací 10–12/2012
# ---------------------------------------------

DIR = Path(__file__).resolve().parent
SEEN_FILE = DIR / "seen.json"
REPORT_FILE = DIR / "posledni.md"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

KOMBI = re.compile(r"\b(combi|kombi|variant|sportsvan|sportsvan|plus|alltrack|cabrio)\b", re.I)
PRODANO = re.compile(r"\b(prodáno|prodano|rezervace|rezervováno)\b", re.I)
GOLF6 = re.compile(r"golf\W{0,3}(vi|6)\b|(?<![\w.,])VI(?![\wI])")  # "Golf VI", "Golf, VI", samostatné "VI"
GOLF7 = re.compile(r"golf\W{0,3}(vii|7)\b|\bVII\b|\bmk7\b", re.I)


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


def rok_ok(rok, text, mesic=None):
    """Vrátí (projde, poznámka). Golf VII se vyrábí od cca 09/2012."""
    if GOLF6.search(text) and not GOLF7.search(text):
        return False, ""
    if rok is None:
        return True, "rok neuveden"
    if rok >= ROK_OD:
        return True, ""
    if rok == 2012 and ROK_2012_POVOLIT:
        if GOLF7.search(text):
            return True, ""
        if mesic and mesic >= 10:  # VII na trhu od cca 10–11/2012
            return True, "r. 2012 – ověř, zda VII"
        return False, ""  # 2012 bez zmínky o VII = téměř jistě Golf VI
    return False, ""


# ---------------- SAUTO ----------------
def sauto():
    base = "https://www.sauto.cz/api/v1/items/search"
    params = {
        "category_id": 838,
        "manufacturer_model_seo": "volkswagen:golf",
        "tachometer_to": MAX_KM,
        "price_to": MAX_CENA,
        "fuel_seo": "benzin",
        "vehicle_body_seo": "hatchback",
        "engine_volume_from": 1100,
        "engine_volume_to": 1300,
        "limit": 100,
    }
    out, offset = [], 0
    while True:
        params["offset"] = offset
        d = json.loads(get(base + "?" + urllib.parse.urlencode(params)))
        res = d.get("results", [])
        for it in res:
            text = it.get("name") or f"Volkswagen Golf {it.get('additional_model_name','')}"
            mdate = it.get("in_operation_date") or it.get("manufacturing_date") or ""
            rok = int(mdate[:4]) if mdate[:4].isdigit() else None
            mesic = int(mdate[5:7]) if mdate[5:7].isdigit() else None
            ok, pozn = rok_ok(rok, text, mesic)
            if not ok or KOMBI.search(text):
                continue
            loc = it.get("locality") or {}
            out.append({
                "id": f"sauto-{it['id']}",
                "zdroj": "Sauto",
                "nazev": text.strip(),
                "cena": it.get("price"),
                "km": it.get("tachometer"),
                "rok": rok,
                "prevodovka": (it.get("gearbox_cb") or {}).get("name", ""),
                "misto": loc.get("district") or loc.get("municipality", ""),
                "url": f"https://www.sauto.cz/osobni/detail/volkswagen/golf/{it['id']}",
                "pozn": pozn,
            })
        offset += len(res)
        if not res or offset >= d["pagination"]["total"]:
            break
    return out


# ---------------- BAZOŠ ----------------
RE_ITEM = re.compile(
    r'<div class="inzeraty inzeratyflex">.*?<h2 class=nadpis><a href="(/inzerat/(\d+)/[^"]+)">(.*?)</a>'
    r'.*?<div class=popis>(.*?)</div>.*?<div class="inzeratycena">(.*?)</div>'
    r'.*?<div class="inzeratylok">(.*?)</div>', re.S)


def parse_km(text):
    t = text.lower().replace("\xa0", " ")
    cands = []
    for m in re.finditer(r"(\d{1,3}(?:[ .]\d{3})+|\d{4,6})\s*(?:km|kilometr)", t):
        cands.append(int(re.sub(r"\D", "", m.group(1))))
    for m in re.finditer(r"(\d{2,3})(?:[.,]\d)?\s*(?:tis\.?\s*km|tkm|tis\b|xxx)", t):
        cands.append(int(m.group(1)) * 1000)
    cands = [c for c in cands if 5_000 <= c <= 500_000]
    return max(cands) if cands else None


def parse_rok(text):
    roky = [int(y) for y in re.findall(r"\b(20[01]\d|202\d)\b", text)]
    roky = [y for y in roky if 2008 <= y <= date.today().year]
    return min(roky) if roky else None


def bazos():
    out, seen_ids, start = [], set(), 0
    q = {"hledat": "golf 1.2 tsi", "rubriky": "auto", "hlokalita": "", "humkreis": "25",
         "cenaod": "", "cenado": str(MAX_CENA), "order": ""}
    while start < 400:
        path = "volkswagen/" + (f"{start}/" if start else "")
        try:
            h = get(f"https://auto.bazos.cz/{path}?" + urllib.parse.urlencode(q))
        except urllib.error.HTTPError as e:
            if e.code == 404:  # za poslední stránkou
                break
            raise
        items = RE_ITEM.findall(h)
        if not items:
            break
        for href, iid, title, popis, cena, lok in items:
            if iid in seen_ids:
                continue
            seen_ids.add(iid)
            title = html.unescape(re.sub(r"<[^>]+>", "", title)).strip()
            popis = html.unescape(re.sub(r"<[^>]+>", "", popis)).strip()
            text = f"{title} {popis}"
            low = text.lower()
            if "golf" not in title.lower() or not re.search(r"1[.,]\s?2\s*tsi", low):
                continue
            if KOMBI.search(text) or PRODANO.search(title):
                continue
            km = parse_km(text)
            if km is not None and km > MAX_KM:
                continue
            m = re.search(r"\b(\d{1,2})\s*/\s*(20[12]\d)\b", title)
            rok = int(m.group(2)) if m else (parse_rok(title) or parse_rok(text))
            mesic = int(m.group(1)) if m else None
            ok, pozn = rok_ok(rok, text, mesic)
            if not ok:
                continue
            cena_n = re.sub(r"\D", "", html.unescape(re.sub(r"<[^>]+>", "", cena)))
            cena_n = int(cena_n) if cena_n else None
            if cena_n is not None and not (MIN_CENA <= cena_n <= MAX_CENA):
                continue
            if km is None:
                pozn = ", ".join(p for p in (pozn, "km neuvedeny v náhledu") if p)
            out.append({
                "id": f"bazos-{iid}",
                "zdroj": "Bazoš",
                "nazev": title,
                "cena": cena_n,
                "km": km,
                "rok": rok,
                "prevodovka": ("Manuální" if re.search(r"manuál|manual|6\s*kv|5\s*kv|m[56]\b", low)
                               else "DSG" if re.search(r"\bdsg\b|automat", low) else ""),
                "misto": html.unescape(re.sub(r"<br>.*", "", lok)).strip(),
                "url": "https://auto.bazos.cz" + href,
                "pozn": pozn,
            })
        start += 40
    return out


# ---------------- VÝSTUP ----------------
def fmt(n, unit):
    return f"{n:,}".replace(",", " ") + f" {unit}" if n else "?"


def tabulka(items):
    rows = ["| Zdroj | Inzerát | Rok | Najeto | Cena | Převodovka | Místo | Pozn. |",
            "|---|---|---|---|---|---|---|---|"]
    for i in sorted(items, key=lambda x: x["cena"] or 10**9):
        nazev = i["nazev"].replace("|", "/")[:70]
        rows.append(f"| {i['zdroj']} | [{nazev}]({i['url']}) | {i['rok'] or '?'} | {fmt(i['km'], 'km')} | "
                    f"{fmt(i['cena'], 'Kč')} | {i['prevodovka']} | {i['misto']} | {i['pozn']} |")
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="jen ukázat, nic neuložit")
    ap.add_argument("--vse", action="store_true", help="vypsat všechny vyhovující, nic neuložit")
    a = ap.parse_args()

    vse, chyby = [], []
    for nazev, fn in (("Sauto", sauto), ("Bazoš", bazos)):
        try:
            vse += fn()
        except Exception as e:  # zdroj nedostupný, druhý běží dál
            chyby.append(f"{nazev}: {e}")

    seen = set(json.loads(SEEN_FILE.read_text())) if SEEN_FILE.exists() else set()
    prvni_beh = not seen
    nove = vse if a.vse else [i for i in vse if i["id"] not in seen]

    hlav = (f"# Golf VII 1.2 TSI – {date.today():%d. %m. %Y}\n\n"
            f"Vyhovuje celkem: {len(vse)} | {'všechny' if a.vse else 'nové'}: {len(nove)}"
            + (" (první běh – vše je nové)" if prvni_beh and not a.vse else "") + "\n")
    if chyby:
        hlav += "\n**Chyby zdrojů:** " + "; ".join(chyby) + "\n"
    report = hlav + ("\n" + tabulka(nove) + "\n" if nove else "\nŽádné nové inzeráty.\n")
    print(report)

    if not a.dry_run and not a.vse:
        SEEN_FILE.write_text(json.dumps(sorted(seen | {i["id"] for i in vse}), indent=0))
        REPORT_FILE.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
