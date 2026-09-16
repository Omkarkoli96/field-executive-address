# Address Verification Tool — Simplified

A single-page batch tool: upload a Customer Data file and a Visited Data
file, and it geocodes + compares addresses automatically, then downloads
the result as one Excel file. No login, no admin/field-executive split,
no persistent database of customers or visits.

## How it works
1. Open the app — one page, two file inputs.
2. Upload **Customer Data** (who should have been visited) and **Visited
   Data** (what was actually recorded on each visit).
3. Click **Compare & download result** — the app matches rows by
   `Loan_ID`, geocodes both addresses, computes the distance between
   them, and your browser downloads `Verification_Result.xlsx`
   immediately.

## File formats

**Customer Data** (`.csv` or `.xlsx`)
| Column | Required | Notes |
|---|---|---|
| `Loan_ID` | Yes | |
| `Customer_Address` | Yes | |
| `Customer_Name` | No | included in the result if present |

**Visited Data** (`.csv` or `.xlsx`)
| Column | Required | Notes |
|---|---|---|
| `Loan_ID` | Yes | must match a row in Customer Data |
| `Visited_Address` | Yes | the address recorded at the time of visit |
| `Executive_Name` | No | included in the result if present |
| `Visit_Date` | No | included in the result if present |

## Result file columns
`Loan_ID, Executive_Name, Visit_Date, Customer_Name, Customer_Address, Visited_Address, Distance_KM, Status`

`Status` is one of:
- **VERIFIED** — distance ≤ 1 km
- **NOT_VERIFIED** — distance > 1 km
- **COULD_NOT_GEOCODE** — one or both addresses couldn't be located
- **LOAN_ID_NOT_FOUND** — the Loan_ID in Visited Data has no match in Customer Data

## Run it locally
```
pip install -r requirements.txt
python main.py
```
Open **http://127.0.0.1:8000**, upload both files, and the result downloads automatically.

## Deploying
Push to GitHub (`main.py`, `models.py`, `database.py`, `geocode.py`,
`requirements.txt`, `runtime.txt`, `render.yaml`, and the `templates/`
and `static/` folders — as real folders, not flat files) → connect the
repo on Render as a Blueprint. No database service is needed this time;
`render.yaml` defines a single web service.

## Known limitations, honestly stated
- No login/password on this page — anyone with the link can run
  comparisons. There's no data to protect since nothing is stored
  persistently, but if you want a shared password gate, that can be
  added.
- No persistent history — each upload is a one-shot comparison. If you
  want every past comparison logged somewhere, that needs a database
  brought back in (like the previous version had).
- Address geocoding depends on OpenStreetMap's free Nominatim service —
  vague or malformed addresses may fail to geocode, showing up as
  `COULD_NOT_GEOCODE`.
- Free Render tier sleeps after 15 minutes idle — first request after
  that will be slow to wake up.
