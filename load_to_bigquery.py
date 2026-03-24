import pandas as pd
import pandas_gbq
import pydata_google_auth
import requests

from tests.eia_part3 import (
    build_df_from_eia_data,
    filter_since,
    sum_by_week,
)
from validation import eia_schema

PROJECT_ID = "sipa-adv-c-giggling-wombat"
DATASET = "petroleum_supply"
TABLE = "wti_prices"
API_KEY = "qIgxlen05S7xFsozHUuJ4HXned44qT8RF3OewtSv"

SUPPLY_TABLE = "weekly_supply"
WTI_TABLE = "weekly_wti"

SUPPLY_URL = (
    "https://api.eia.gov/v2/petroleum/cons/wpsup/data/"
    f"?api_key={API_KEY}"
    "&frequency=weekly"
    "&data[0]=value"
    "&sort[0][column]=period"
    "&sort[0][direction]=desc"
    "&offset=0&length=5000"
)

WTI_URL = (
    "https://api.eia.gov/v2/petroleum/pri/spt/data/"
    f"?api_key={API_KEY}"
    "&frequency=weekly"
    "&data[0]=value"
    "&facets[series][]=RWTC"
    "&sort[0][column]=period"
    "&sort[0][direction]=desc"
    "&offset=0&length=5000"
)

SCOPES = [
    "https://www.googleapis.com/auth/cloud-platform",
]


def fetch_eia_json(url: str) -> dict:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def build_supply_df(payload: dict) -> pd.DataFrame:
    data = payload.get("response", {}).get("data", [])
    df = build_df_from_eia_data(
        data=data,
        period_col="period",
        value_col="value",
        new_date_col="week",
    )

    if df.empty:
        raise ValueError("No usable supply data returned from EIA.")

    df = filter_since(df, date_col="week", start_date="2012-01-01")
    df = eia_schema.validate(df)

    if df.empty:
        raise ValueError("Supply data empty after validation/filtering.")

    weekly_total = sum_by_week(df, date_col="week", value_col="value")
    weekly_total = weekly_total.rename(columns={"value": "total_product_supplied"})
    weekly_total["week"] = pd.to_datetime(weekly_total["week"])

    return weekly_total.sort_values("week").reset_index(drop=True)


def build_wti_df(payload: dict) -> pd.DataFrame:
    data = payload.get("response", {}).get("data", [])
    df = pd.DataFrame(data)

    if df.empty:
        raise ValueError("No usable WTI data returned from EIA.")

    df = df[["period", "series", "value"]].copy()
    df["week"] = pd.to_datetime(df["period"], errors="coerce")
    df["wti_price"] = pd.to_numeric(df["value"], errors="coerce")

    df = df.dropna(subset=["week", "wti_price"])
    df = df[df["week"] >= pd.Timestamp("2012-01-01")]
    df = df[["week", "series", "wti_price"]].sort_values("week").reset_index(drop=True)

    return df


def upload_df(df: pd.DataFrame, table_name: str, credentials) -> None:
    pandas_gbq.to_gbq(
        dataframe=df,
        destination_table=f"{DATASET}.{table_name}",
        project_id=PROJECT_ID,
        credentials=credentials,
        if_exists="replace",
    )


def main():
    credentials = pydata_google_auth.get_user_credentials(
        SCOPES,
        auth_local_webserver=True,
    )

    supply_payload = fetch_eia_json(SUPPLY_URL)
    supply_df = build_supply_df(supply_payload)
    upload_df(supply_df, SUPPLY_TABLE, credentials)
    print(f"Uploaded {len(supply_df)} rows to {DATASET}.{SUPPLY_TABLE}")

    wti_payload = fetch_eia_json(WTI_URL)
    wti_df = build_wti_df(wti_payload)
    upload_df(wti_df, WTI_TABLE, credentials)
    print(f"Uploaded {len(wti_df)} rows to {DATASET}.{WTI_TABLE}")


if __name__ == "__main__":
    main()
