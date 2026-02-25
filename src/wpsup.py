import pandas as pd

def add_week_column(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["week"] = out["period"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
    return out

def compute_weekly_total(df: pd.DataFrame) -> pd.DataFrame:
    weekly_total = (
        df.groupby("week", as_index=False)["value"]
          .sum()
          .rename(columns={"value": "total_product_supplied"})
          .sort_values("week")
    )
    return weekly_total

def clean_wpsup(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["period"] = pd.to_datetime(out["period"], errors="coerce")
    out["value"] = pd.to_numeric(out["value"], errors="coerce")
    out = out.dropna(subset=["period", "value"])
    return out 