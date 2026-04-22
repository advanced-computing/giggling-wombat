import json
import os

import pandas as pd
import requests
from google.cloud import bigquery
from google.oauth2 import service_account

PROJECT_ID = "sipa-adv-c-giggling-wombat"
DATASET_ID = "petroleum_supply"

WEEKLY_SUPPLY_TABLE = f"{PROJECT_ID}.{DATASET_ID}.weekly_supply"
WEEKLY_SUPPLY_BY_PRODUCT_TABLE = f"{PROJECT_ID}.{DATASET_ID}.weekly_supply_by_product"

REQUEST_TIMEOUT = 30


def get_bq_client():
    service_account_info = json.loads(os.environ["GCP_SERVICE_ACCOUNT"])
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    return bigquery.Client(
        credentials=credentials,
        project=credentials.project_id,
    )


def fetch_supply_data() -> pd.DataFrame:
    api_key = os.environ["EIA_API_KEY"]
    url = (
        "https://api.eia.gov/v2/petroleum/cons/wpsup/data/"
        f"?api_key={api_key}"
        "&frequency=weekly"
        "&data[0]=value"
        "&sort[0][column]=period"
        "&sort[0][direction]=desc"
        "&offset=0&length=5000"
    )

    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    records = response.json()["response"]["data"]

    df = pd.DataFrame(records)
    df["week"] = pd.to_datetime(df["period"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")

    for col in df.columns:
        if df[col].dtype == "object":
            df[col] = df[col].astype(str)

    df = df.dropna(subset=["week", "value"]).copy()
    df = df.sort_values("week").reset_index(drop=True)
    return df


def build_weekly_supply(df: pd.DataFrame) -> pd.DataFrame:
    weekly_supply = (
        df.groupby("week", as_index=False)["value"]
        .sum()
        .rename(columns={"value": "total_supply"})
        .sort_values("week")
        .reset_index(drop=True)
    )
    return weekly_supply


def find_first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def build_weekly_supply_by_product(df: pd.DataFrame) -> pd.DataFrame:
    product_code_col = find_first_existing_column(
        df,
        [
            "product",
            "product_code",
            "product-code",
            "process",
        ],
    )

    product_name_col = find_first_existing_column(
        df,
        [
            "product-name",
            "product_name",
            "name",
            "productName",
        ],
    )

    if product_code_col is None and product_name_col is None:
        raise KeyError("Could not find product code or product name columns.")

    working_df = df.copy()

    if product_code_col is None:
        working_df["product"] = working_df[product_name_col]
    else:
        working_df["product"] = working_df[product_code_col]

    if product_name_col is None:
        working_df["product_name"] = working_df["product"]
    else:
        working_df["product_name"] = working_df[product_name_col]

    weekly_supply_by_product = (
        working_df.groupby(
            ["week", "product", "product_name"],
            as_index=False,
        )["value"]
        .sum()
        .rename(columns={"value": "product_supplied"})
        .sort_values(["week", "product_name"])
        .reset_index(drop=True)
    )
    return weekly_supply_by_product


def load_table(df: pd.DataFrame, table_id: str):
    client = get_bq_client()
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    job = client.load_table_from_dataframe(df, table_id, job_config=job_config)
    job.result()


def main():
    raw_df = fetch_supply_data()

    weekly_supply = build_weekly_supply(raw_df)
    weekly_supply_by_product = build_weekly_supply_by_product(raw_df)

    load_table(weekly_supply, WEEKLY_SUPPLY_TABLE)
    print(f"Loaded {len(weekly_supply)} rows into {WEEKLY_SUPPLY_TABLE}")

    load_table(weekly_supply_by_product, WEEKLY_SUPPLY_BY_PRODUCT_TABLE)
    print(f"Loaded {len(weekly_supply_by_product)} rows into {WEEKLY_SUPPLY_BY_PRODUCT_TABLE}")


if __name__ == "__main__":
    main()
