import logging
import sys
import time
from pathlib import Path

import pandas as pd

RAW = Path("data/raw/online_retail_II.xlsx")
BRONZE = Path("data/bronze")
DOCS = Path("docs")
for p in (BRONZE, DOCS, Path("logs")):
    p.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("logs/ingest.log")],
)
log = logging.getLogger("profile_raw")


def read_source() -> pd.DataFrame:
    if not RAW.exists():
        log.error("File not found: %s", RAW)
        sys.exit(1)
    log.info("Reading Excel (2 sheets, ~1M rows). This takes 2-4 minutes...")
    start = time.time()
    sheets = pd.read_excel(RAW, sheet_name=None, dtype={"Invoice": str, "StockCode": str})
    frames = []
    for name, df in sheets.items():
        df["source_sheet"] = name
        frames.append(df)
        log.info("Sheet %s: %s rows", name, f"{len(df):,}")
    df = pd.concat(frames, ignore_index=True)
    log.info("Read %s rows in %.0fs", f"{len(df):,}", time.time() - start)
    return df

def standardise(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={
        "Invoice": "invoice", "StockCode": "stock_code", "Description": "description",
        "Quantity": "quantity", "InvoiceDate": "invoice_ts", "Price": "unit_price",
        "Customer ID": "customer_id", "Country": "country",
    })
    df["customer_id"] = df["customer_id"].astype("Int64")
    df["invoice_ts"] = pd.to_datetime(df["invoice_ts"])
    df["description"] = df["description"].astype("string")
    df["country"] = df["country"].astype("string")
    return df

def profile(df: pd.DataFrame) -> dict:
    n = len(df)
    pct = lambda x: f"{x:,} ({x / n:.1%})"
    return {
        "Total rows": f"{n:,}",
        "Date range": f"{df.invoice_ts.min():%Y-%m-%d} to {df.invoice_ts.max():%Y-%m-%d}",
        "Unique invoices": f"{df.invoice.nunique():,}",
        "Unique customers": f"{df.customer_id.nunique():,}",
        "Unique products": f"{df.stock_code.nunique():,}",
        "Countries": f"{df.country.nunique():,}",
        "Missing customer_id": pct(int(df.customer_id.isna().sum())),
        "Cancellations (invoice starts with C)": pct(int(df.invoice.str.startswith("C").sum())),
        "Negative quantity": pct(int((df.quantity < 0).sum())),
        "Zero or negative price": pct(int((df.unit_price <= 0).sum())),
        "Numeric (non-text) descriptions": pct(int(pd.to_numeric(df.description, errors="coerce").notna().sum())),
        "Missing description": pct(int(df.description.isna().sum())),
        "Exact duplicate rows": pct(int(df.duplicated(subset=[c for c in df.columns if c != "source_sheet"]).sum())),
        "UK share of rows": f"{(df.country == 'United Kingdom').mean():.1%}",
    }


def main():
    df = standardise(read_source())
    results = profile(df)

    print("\nRAW DATA PROFILE")
    for k, v in results.items():
        print(f"  {k:<40} {v}")

    out = BRONZE / "transactions.parquet"
    df.to_parquet(out, index=False)
    log.info("Saved bronze file: %s (%s rows)", out, f"{len(df):,}")

    with open(DOCS / "data_profile.md", "w", encoding="utf-8") as f:
        f.write("# Raw Data Profile (Online Retail II)\n\n| Check | Result |\n|---|---|\n")
        for k, v in results.items():
            f.write(f"| {k} | {v} |\n")
    log.info("Saved docs/data_profile.md")


if __name__ == "__main__":
    main()