# Plant Patent Dashboard

This is a lightweight dashboard for fruit, tree nut, and vegetable plant-patent monitoring.

## What it tracks

- Seed data from the local workbook in `Patent Dashboard`.
- Public issued plant patents from the USPTO Official Gazette.
- Published plant applications can be added later through the same JSON file once an Open Data Portal/API-key workflow is selected.

Important limitation: unpublished filings inside Patent Center are not public records. A USPTO account can help with Patent Center or Open Data Portal workflows, but it cannot make non-public filings broadly available for an automated public dashboard.

## Run locally

From this folder:

```powershell
python scripts/export_seed.py
python scripts/refresh_uspto_grants.py --issues 8
python scripts/serve.py
```

Then open:

```text
http://127.0.0.1:8787/
```

## Daily refresh

The refresh script writes `data/plant_patents.json`. For an online deployment, schedule:

```powershell
python scripts/refresh_uspto_grants.py --issues 8
```

Run it once per day. The USPTO Official Gazette is weekly, but daily checks are harmless and make the dashboard pick up new issues as soon as they appear.

## Crop filtering

Edit `config/crop_keywords.txt` to change what the Gazette updater treats as fruit, tree nut, or vegetable. The USPTO plant-patent feed includes ornamentals, so this filter keeps the dashboard focused.
