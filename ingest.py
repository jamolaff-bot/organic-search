"""
Download and ingest the USDA Organic Integrity monthly snapshot into SQLite.

Usage:
    python ingest.py              # downloads latest available month
    python ingest.py --file /path/to/INTEGRITY_Export_20260501.xlsx
    python ingest.py --date 20260401   # specific month (YYYYMMDD)
"""

import argparse
import re
import sys
import urllib.request
from datetime import datetime, date
from pathlib import Path

import openpyxl

import database as db

BASE_URL = "https://organic.ams.usda.gov/Integrity/MonthlyReports"

PRODUCT_COLS = [
    "CR_CertifiedProducts", "CR_CertifiedProducts_Add",
    "LS_CertifiedProducts", "LS_CertifiedProducts_Add",
    "WC_CertifiedProducts", "WC_CertifiedProducts_Add",
    "Han_CertifiedProducts", "Han_CertifiedProducts_Add",
]


def latest_month_url() -> tuple[str, str]:
    """Return (url, date_str) for the most recent available monthly export."""
    today = date.today()
    # Try current month back 6 months
    for months_back in range(1, 7):
        m = today.month - months_back
        y = today.year
        while m <= 0:
            m += 12
            y -= 1
        date_str = f"{y}{m:02d}01"
        url = f"{BASE_URL}/INTEGRITY_Export_{date_str}.xlsx"
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=10):
                return url, date_str
        except Exception:
            continue
    raise RuntimeError("Could not find a recent monthly export. Try --date YYYYMMDD.")


def download(url: str, dest: Path) -> None:
    print(f"Downloading {url} ...")
    urllib.request.urlretrieve(url, dest)
    size_mb = dest.stat().st_size / 1024 / 1024
    print(f"  Saved to {dest} ({size_mb:.1f} MB)")


def build_op_url(nop_id: str) -> str:
    """Build a direct operation profile URL using the NOP ID."""
    return (f"https://organic.ams.usda.gov/integrity/CP/OPP"
            f"?nopid={nop_id}&ret=Home&retName=Home")


def combine_products(row: dict) -> str:
    """Merge all product columns into a single searchable text blob."""
    parts = []
    for col in PRODUCT_COLS:
        val = row.get(col)
        if val:
            parts.append(str(val).replace("\n", ", "))
    return "; ".join(parts)


def parse_xlsx(path: Path) -> tuple[list[dict], str]:
    """Parse the INTEGRITY_Export xlsx into a list of operation dicts."""
    print(f"Parsing {path.name} …")
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)
    # Row 1: machine names (headers)
    headers = [str(c) if c else "" for c in next(rows_iter)]
    # Row 2: human-readable descriptions — skip
    next(rows_iter)

    col_idx = {h: i for i, h in enumerate(headers)}

    def get(row, col):
        i = col_idx.get(col)
        return row[i] if i is not None and i < len(row) else None

    ops = []
    data_date = ""
    for raw in rows_iter:
        nop_id = str(get(raw, "op_nopOpID") or "").strip()
        if not nop_id or nop_id == "None":
            continue

        cert_url = build_op_url(nop_id)

        # State: prefer physical, fall back to mailing
        state = (get(raw, "opPA_state") or get(raw, "opMA_state") or "").strip()
        country = (get(raw, "opPA_country") or get(raw, "opMA_country") or "").strip()

        row_dict = {h: get(raw, h) for h in headers}
        products_text = combine_products(row_dict)

        pub = get(raw, "Pub_Date") or ""
        if pub and not data_date:
            s = str(pub)
            # Skip the description row text
            if "/" in s and len(s) <= 12:
                data_date = s

        ops.append({
            "nop_id": nop_id,
            "name": str(get(raw, "op_name") or "").strip(),
            "status": str(get(raw, "op_status") or "").strip(),
            "state": state,
            "country": country,
            "certifier": str(get(raw, "Cert_name") or "").strip(),
            "cert_url": cert_url,
            "all_products": products_text,
            "data_date": str(get(raw, "Pub_Date") or ""),
        })

    wb.close()
    print(f"  Parsed {len(ops):,} operations.")
    return ops, data_date


def ingest(xlsx_path: Path, data_date: str):
    ops, detected_date = parse_xlsx(xlsx_path)
    effective_date = data_date or detected_date

    print("Loading into SQLite …")
    db.init_db()
    db.clear_and_rebuild_fts()

    CHUNK = 2000
    for i in range(0, len(ops), CHUNK):
        db.bulk_insert(ops[i : i + CHUNK])
        pct = min(100, int((i + CHUNK) / len(ops) * 100))
        print(f"  {pct}% ({min(i+CHUNK, len(ops)):,}/{len(ops):,})", end="\r")

    print()
    db.set_meta("data_date", effective_date)
    db.set_meta("loaded_at", datetime.utcnow().isoformat())
    print(f"Done. {len(ops):,} operations indexed (data as of {effective_date}).")


def main():
    parser = argparse.ArgumentParser(description="Ingest USDA Organic Integrity data")
    parser.add_argument("--file", help="Path to local INTEGRITY_Export_*.xlsx")
    parser.add_argument("--date", help="Specific month to download, e.g. 20260501")
    args = parser.parse_args()

    if args.file:
        xlsx_path = Path(args.file)
        date_str = ""
    else:
        if args.date:
            date_str = args.date
            url = f"{BASE_URL}/INTEGRITY_Export_{date_str}.xlsx"
        else:
            url, date_str = latest_month_url()

        xlsx_path = Path(f"/tmp/INTEGRITY_Export_{date_str}.xlsx")
        if not xlsx_path.exists():
            download(url, xlsx_path)
        else:
            print(f"Using cached {xlsx_path}")

    ingest(xlsx_path, date_str)


if __name__ == "__main__":
    main()
