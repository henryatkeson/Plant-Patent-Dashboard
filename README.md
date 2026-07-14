# Plant Patent Dashboard

This is a lightweight dashboard for fruit, tree nut, and vegetable plant-patent monitoring.

## What it tracks

- Seed data from the local workbook in `Patent Dashboard`.
- Public issued plant patents from the USPTO Official Gazette.
- CPVO Variety Finder export records for selected high-relevance crops.
- Published plant applications can be added later through the same JSON file once an Open Data Portal/API-key workflow is selected.

Important limitation: unpublished filings inside Patent Center are not public records. A USPTO account can help with Patent Center or Open Data Portal workflows, but it cannot make non-public filings broadly available for an automated public dashboard.

## Run locally

From this folder:

```powershell
python scripts/export_seed.py
python scripts/refresh_uspto_grants.py --issues 8
python scripts/import_cpvo_varieties.py
python scripts/serve.py
```

Then open:

```text
http://127.0.0.1:8787/
```

## Daily refresh

The refresh scripts write `data/plant_patents.json`. `data/cpvo_varieties.json` is rebuilt from local CPVO Variety Finder Excel exports when new exports are downloaded.

For an online deployment, schedule:

```powershell
python scripts/refresh_uspto_grants.py --issues 8
```

Run it once per day. The USPTO Official Gazette is weekly, but daily checks are harmless and make the dashboard pick up new issues as soon as they appear.

## CPVO Variety Finder

The dashboard imports CPVO Variety Finder workbook exports with `scripts/import_cpvo_varieties.py`. The importer reads every `*CPOV Varieties.xlsx` workbook saved in the parent `Patent Dashboard` folder, dedupes overlapping records, and writes the combined dataset to `data/cpvo_varieties.json`. Register types are grouped as protected IP (`PBR`, `PLP`), official listings (`NLI`, `FRU`), commercial listings (`COM`), and other/unclear (`ZZZ`).

## Crop filtering

Edit `config/crop_keywords.txt` to change what the Gazette updater treats as fruit, tree nut, or vegetable. The USPTO plant-patent feed includes ornamentals, so this filter keeps the dashboard focused.
