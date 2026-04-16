import json
import os

import pandas as pd
import requests
from google.cloud import bigquery
from google.oauth2 import service_account

PROJECT_ID = "sipa-adv-c-giggling-wombat"
DATASET_ID = "petroleum_supply"
TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.weekly_wti"

WTI_SERIES = "RWTC"
REQUEST_TIMEOUT = 30


def get_bq_client():
    service_account_info = json.loads(os.environ["GCP_SERVICE_ACCOUNT"])
    credentials = service_account.Credentials.from_service_account_info(service_account_info)
    return bigquery.Client(
        credentials=credentials,
        project=credentials.project_id,
    )


def fetch_wti_data() -> pd.DataFrame:
    api_key = os.environ["EIA_API_KEY"]
    url = (
        "https://api.eia.gov/v2/petroleum/pri/spt/data/"
        f"?api_key={api_key}"
        "&frequency=weekly"
        "&data[0]=value"
        f"&facets[series][]={WTI_SERIES}"
        "&sort[0][column]=period"
        "&sort[0][direction]=desc"
        "&offset=0&length=5000"
    )

    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    records = response.json()["response"]["data"]

    df = pd.DataFrame(records)
    df["week"] = pd.to_datetime(df["period"])
    df["wti_price"] = pd.to_numeric(df["value"], errors="coerce")
    df["series"] = df["series"].astype(str)

    df = df[["week", "series", "wti_price"]].dropna()
    df = df.sort_values("week").reset_index(drop=True)
    return df


def load_to_bigquery(df: pd.DataFrame):
    client = get_bq_client()
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    job = client.load_table_from_dataframe(df, TABLE_ID, job_config=job_config)
    job.result()


def main():
    df = fetch_wti_data()
    load_to_bigquery(df)
    print(f"Loaded {len(df)} rows into {TABLE_ID}")


if __name__ == "__main__":
    main()
