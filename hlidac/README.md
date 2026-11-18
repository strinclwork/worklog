# Hlídač: VW Golf VII 1.2 TSI

Kritéria: Golf VII (1. registrace od 10/2012), 1.2 TSI benzín, hatchback, max 190 000 km, max 230 000 Kč.
Zdroje: sauto.cz (API, přesné filtry) a auto.bazos.cz (text, km a rok se čtou z titulku a náhledu – orientačně).

- `golf_hlidac.py` – skript (konfigurace nahoře v souboru)
- `seen.json` – ID už nahlášených inzerátů
- `posledni.md` – výsledek posledního běhu
- `aktualni_nabidka.md` – kompletní nabídka v den založení hlídače

Spuštění na Windows: `py golf_hlidac.py --dry-run` (jen ukáže), `py golf_hlidac.py --vse` (vše vyhovující).
Běží automaticky v cloudu 2× denně jako naplánovaná úloha.
