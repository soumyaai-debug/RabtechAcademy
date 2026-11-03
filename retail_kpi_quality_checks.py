"""
Retail Orders – KPI and Data Quality Checks
Usage:
    pip install pandas
    python retail_kpi_quality_checks.py retail-orders-raw.csv

This script preserves the raw file, normalizes case/whitespace for analysis,
reports quality failures, and calculates provisional KPIs from rows that pass
the strict core transaction checks. Missing discounts are NOT assumed to be zero.
"""
import sys
import pandas as pd

INPUT = sys.argv[1] if len(sys.argv) > 1 else "retail-orders-raw.csv"
REQUIRED = [
    "order_id", "order_date", "customer_segment", "city", "category",
    "quantity", "unit_price", "discount_pct", "payment_status"
]
ALLOWED_SEGMENTS = {"Student", "Fresher", "Professional"}
ALLOWED_CATEGORIES = {"Learning Kit", "Course Access", "Mentor Session"}
ALLOWED_STATUSES = {"Paid", "Pending", "Failed", "Refunded"}

df = pd.read_csv(INPUT)
missing_columns = [c for c in REQUIRED if c not in df.columns]
if missing_columns:
    raise ValueError(f"Missing required columns: {missing_columns}")

work = df.copy()
for col in ["order_id", "customer_segment", "city", "category", "payment_status"]:
    work[col] = work[col].astype("string").str.strip()

work["customer_segment_norm"] = work["customer_segment"].str.title()
work["payment_status_norm"] = work["payment_status"].str.title()
work["order_date_parsed"] = pd.to_datetime(
    work["order_date"], format="mixed", dayfirst=True, errors="coerce"
)
work["quantity_num"] = pd.to_numeric(work["quantity"], errors="coerce")
work["unit_price_num"] = pd.to_numeric(work["unit_price"], errors="coerce")
work["discount_num"] = pd.to_numeric(work["discount_pct"], errors="coerce")

print("\\n=== DATA QUALITY PROFILE ===")
print(f"Rows: {len(work)}")
print(f"Exact duplicate rows: {work.duplicated().sum()}")
print(f"Rows with duplicate order_id: {work.duplicated('order_id', keep=False).sum()}")
print("\\nMissing values by column:")
print(work[REQUIRED].isna().sum())

checks = {
    "Invalid/missing order date": work["order_date_parsed"].isna(),
    "Invalid quantity (must be positive whole number)": (
        work["quantity_num"].isna() | (work["quantity_num"] <= 0) |
        ((work["quantity_num"] % 1) != 0)
    ),
    "Invalid unit price (must be numeric and >= 0)": (
        work["unit_price_num"].isna() | (work["unit_price_num"] < 0)
    ),
    "Missing/out-of-range discount": (
        work["discount_num"].isna() | ~work["discount_num"].between(0, 100)
    ),
    "Invalid customer segment": ~work["customer_segment_norm"].isin(ALLOWED_SEGMENTS),
    "Invalid product category": ~work["category"].isin(ALLOWED_CATEGORIES),
    "Invalid payment status": ~work["payment_status_norm"].isin(ALLOWED_STATUSES),
}
print("\\nRule failures:")
for name, mask in checks.items():
    print(f"{name}: {int(mask.sum())} row(s)")

# Strict records for provisional transaction KPIs.
valid = (
    work["order_id"].notna() &
    work["order_date_parsed"].notna() &
    work["customer_segment_norm"].isin(ALLOWED_SEGMENTS) &
    work["category"].isin(ALLOWED_CATEGORIES) &
    work["quantity_num"].notna() & (work["quantity_num"] > 0) &
    ((work["quantity_num"] % 1) == 0) &
    work["unit_price_num"].notna() & (work["unit_price_num"] >= 0) &
    work["discount_num"].notna() & work["discount_num"].between(0, 100) &
    work["payment_status_norm"].isin(ALLOWED_STATUSES)
)
clean = work.loc[valid].drop_duplicates("order_id").copy()
clean["gross_value"] = clean["quantity_num"] * clean["unit_price_num"]
clean["net_value"] = clean["gross_value"] * (1 - clean["discount_num"] / 100)
paid = clean[clean["payment_status_norm"] == "Paid"]
attempts = clean[clean["payment_status_norm"].isin(["Paid", "Failed"])]

paid_orders = paid["order_id"].nunique()
paid_revenue = paid["net_value"].sum()
success_denominator = len(attempts)
success_rate = (
    (len(attempts[attempts["payment_status_norm"] == "Paid"]) /
     success_denominator * 100) if success_denominator else 0
)

print("\\n=== PROVISIONAL KPIs (strict valid subset only) ===")
print(f"Valid order count: {clean['order_id'].nunique()}")
print(f"Paid order count: {paid_orders}")
print(f"Paid net revenue (INR): {paid_revenue:.2f}")
print(f"Average paid order value (INR): {(paid_revenue / paid_orders if paid_orders else 0):.2f}")
print(f"Paid units sold: {paid['quantity_num'].sum():.0f}")
print(f"Discount on paid orders (INR): {(paid['gross_value'] - paid['net_value']).sum():.2f}")
print(f"Payment success rate (Paid / (Paid + Failed), %): {success_rate:.2f}")
print("\\nPaid net revenue by category (INR):")
print(paid.groupby("category")["net_value"].sum().round(2))
print("\\nNOTE: These figures are provisional and based only on rows passing all core checks.")
print("Resolve quarantined rows and obtain business-owner approval before official reporting.")
