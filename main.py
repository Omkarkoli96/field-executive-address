"""
Address Verification Tool (simplified, single-page)
=====================================================
Upload two files on one page:

  1. Customer Data  -> Loan_ID, Customer_Address (Customer_Name optional).
                        Optional: Customer_Latitude, Customer_Longitude —
                        if given, used directly instead of geocoding the
                        address text.
  2. Visited Data    -> Loan_ID, Visited_Address (Executive_Name and
                         Visit_Date optional).
                        Optional: Visited_Latitude, Visited_Longitude —
                        if given (e.g. from a phone GPS pin), used
                        directly instead of geocoding the address text.

For every row in the Visited Data file, this looks up the matching
Loan_ID in Customer Data, resolves both locations (GPS coordinates when
provided — precise; otherwise falls back to geocoding the address text,
which is approximate and can be thrown off by landmark names), and
computes the distance between them:

  - Distance <= 1 km  -> VERIFIED
  - Distance >  1 km  -> NOT_VERIFIED
  - Either location couldn't be resolved -> COULD_NOT_GEOCODE
  - Loan_ID in the Visited file has no match in the Customer file
    -> LOAN_ID_NOT_FOUND

Each result row also shows Customer_Location_Source and
Visited_Location_Source ("GPS" or "Address (approx)") so you know which
results to trust and which borderline ones deserve a manual check.

Submitting the form triggers an immediate Excel download of the result.
No login, no persistent customer/visit database — this is a one-shot
batch comparison tool.
"""

import io
import os

import pandas as pd
from fastapi import FastAPI, Request, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from geopy.distance import geodesic
from sqlalchemy.orm import Session

from database import init_db, get_db
from geocode import geocode_address

VERIFICATION_RADIUS_KM = 1.0

app = FastAPI(title="Address Verification Tool")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

init_db()


def _read_table(file: UploadFile) -> pd.DataFrame:
    content = file.file.read()
    if file.filename.lower().endswith(".csv"):
        return pd.read_csv(io.BytesIO(content), dtype=str).fillna("")
    return pd.read_excel(io.BytesIO(content), dtype=str).fillna("")


def _error_page(messages):
    items = "".join(f"<li>{m}</li>" for m in messages)
    return HTMLResponse(
        f"""<!DOCTYPE html><html><head><link rel="stylesheet" href="/static/style.css"></head>
        <body><div class="wrap">
        <div class="eyebrow">Address Verification Tool</div>
        <h1>Couldn't process that</h1>
        <ul style="line-height:1.8; font-size:13px;">{items}</ul>
        <a class="btn" href="/" style="display:inline-block; margin-top:16px;">Go back</a>
        </div></body></html>""",
        status_code=400,
    )


def _resolve_location(db: Session, row, lat_col: str, lon_col: str, address: str):
    """Returns ((lat, lon) or None, source_label). Prefers real GPS
    coordinates when both columns are present and parse as valid numbers;
    otherwise falls back to geocoding the address text (approximate)."""
    lat_raw = str(row.get(lat_col, "")).strip() if lat_col in row else ""
    lon_raw = str(row.get(lon_col, "")).strip() if lon_col in row else ""

    if lat_raw and lon_raw:
        try:
            lat, lon = float(lat_raw), float(lon_raw)
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return (lat, lon), "GPS"
        except ValueError:
            pass  # fall through to address geocoding

    coords = geocode_address(db, address)
    if coords:
        return coords, "Address (approx)"
    return None, "Not found"


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/compare")
def compare(
    customer_file: UploadFile = File(...),
    visited_file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    try:
        customers_df = _read_table(customer_file)
    except Exception:
        return _error_page(["Could not read the Customer Data file. Make sure it's a valid .csv or .xlsx."])

    try:
        visited_df = _read_table(visited_file)
    except Exception:
        return _error_page(["Could not read the Visited Data file. Make sure it's a valid .csv or .xlsx."])

    cust_required = ["Loan_ID", "Customer_Address"]
    missing_cust = [c for c in cust_required if c not in customers_df.columns]
    visited_required = ["Loan_ID", "Visited_Address"]
    missing_visited = [c for c in visited_required if c not in visited_df.columns]

    if missing_cust or missing_visited:
        errors = []
        if missing_cust:
            errors.append(f"Customer Data file is missing column(s): {', '.join(missing_cust)}")
        if missing_visited:
            errors.append(f"Visited Data file is missing column(s): {', '.join(missing_visited)}")
        return _error_page(errors)

    customers_df["Loan_ID"] = customers_df["Loan_ID"].str.strip()
    visited_df["Loan_ID"] = visited_df["Loan_ID"].str.strip()
    customers_by_id = {row["Loan_ID"]: row for _, row in customers_df.iterrows()}

    has_name_col = "Customer_Name" in customers_df.columns
    has_exec_col = "Executive_Name" in visited_df.columns
    has_date_col = "Visit_Date" in visited_df.columns

    results = []
    for _, vrow in visited_df.iterrows():
        loan_id = vrow["Loan_ID"].strip()
        visited_address = vrow["Visited_Address"].strip()
        exec_name = vrow["Executive_Name"].strip() if has_exec_col else ""
        visit_date = vrow["Visit_Date"].strip() if has_date_col else ""

        cust = customers_by_id.get(loan_id)
        if cust is None:
            results.append({
                "Loan_ID": loan_id,
                "Executive_Name": exec_name,
                "Visit_Date": visit_date,
                "Customer_Name": "",
                "Customer_Address": "",
                "Visited_Address": visited_address,
                "Distance_KM": None,
                "Customer_Location_Source": "",
                "Visited_Location_Source": "",
                "Status": "LOAN_ID_NOT_FOUND",
            })
            continue

        customer_address = cust["Customer_Address"].strip()
        customer_name = cust["Customer_Name"].strip() if has_name_col else ""

        cust_coords, cust_source = _resolve_location(db, cust, "Customer_Latitude", "Customer_Longitude", customer_address)
        visited_coords, visited_source = _resolve_location(db, vrow, "Visited_Latitude", "Visited_Longitude", visited_address)

        if not cust_coords or not visited_coords:
            distance_km = None
            status = "COULD_NOT_GEOCODE"
        else:
            distance_km = round(geodesic(cust_coords, visited_coords).km, 2)
            status = "VERIFIED" if distance_km <= VERIFICATION_RADIUS_KM else "NOT_VERIFIED"

        results.append({
            "Loan_ID": loan_id,
            "Executive_Name": exec_name,
            "Visit_Date": visit_date,
            "Customer_Name": customer_name,
            "Customer_Address": customer_address,
            "Visited_Address": visited_address,
            "Distance_KM": distance_km,
            "Customer_Location_Source": cust_source,
            "Visited_Location_Source": visited_source,
            "Status": status,
        })

    result_df = pd.DataFrame(results)
    buf = io.BytesIO()
    result_df.to_excel(buf, index=False, sheet_name="Verification_Result")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=Verification_Result.xlsx"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
