import pandas as pd
from src.wpsup import add_week_column, compute_weekly_total, clean_wpsup

def test_add_week_column_week_ending_friday():
    df = pd.DataFrame({
        "period": pd.to_datetime(["2026-02-17"])
    })
    out = add_week_column(df)
    assert out.loc[0, "week"] == pd.Timestamp("2026-02-20")

def test_add_week_column_normalized_midnight():
    df = pd.DataFrame({"period": pd.to_datetime(["2026-02-20 15:30:00"])})
    out = add_week_column(df)
    w = out.loc[0, "week"]
    assert w.hour == 0 and w.minute == 0 and w.second == 0

    from src.wpsup import compute_weekly_total

def test_compute_weekly_total_sums_values():
    df = pd.DataFrame({
        "week": pd.to_datetime(["2026-02-20", "2026-02-20", "2026-02-27"]),
        "value": [10, 5, 7]
    })
    out = compute_weekly_total(df)

    v1 = out.loc[out["week"] == pd.Timestamp("2026-02-20"), "total_product_supplied"].iloc[0]
    v2 = out.loc[out["week"] == pd.Timestamp("2026-02-27"), "total_product_supplied"].iloc[0]
    assert v1 == 15
    assert v2 == 7

    from src.wpsup import clean_wpsup

def test_clean_wpsup_drops_invalid_rows():
    df = pd.DataFrame({
        "period": ["2026-02-01", "not-a-date"],
        "value": ["10", "abc"]
    })
    out = clean_wpsup(df)
    assert out.shape[0] == 1
    assert pd.api.types.is_datetime64_any_dtype(out["period"])
    assert pd.api.types.is_numeric_dtype(out["value"])