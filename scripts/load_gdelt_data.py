import json
import os

import pandas as pd
from google.cloud import bigquery
from google.oauth2 import service_account

PROJECT_ID = "sipa-adv-c-giggling-wombat"
DATASET_ID = "petroleum_supply"
TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.weekly_gdelt_events"

# Key oil-producing countries (FIPS country codes used by GDELT)
OIL_PRODUCING_COUNTRIES = ("RS", "IR", "IZ", "SA", "LY", "VE", "AE", "KU", "NI", "AG")

# CAMEO event root codes for conflict events
# 15: Exhibit force
# 16: Reduce relations (sanctions, expulsions)
# 17: Coerce
# 18: Assault
# 19: Use of force / military
# 20: Fight
CONFLICT_EVENT_CODES = ("15", "16", "17", "18", "19", "20")


def get_bq_client():
    # Support both JSON string and file path
    key_path = os.environ.get("GCP_KEY_PATH")
    if key_path:
        credentials = service_account.Credentials.from_service_account_file(key_path)
    else:
        service_account_info = json.loads(os.environ["GCP_SERVICE_ACCOUNT"])
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
    return bigquery.Client(
        credentials=credentials,
        project=credentials.project_id,
    )


def fetch_gdelt_data() -> pd.DataFrame:
    client = get_bq_client()

    country_list = ", ".join(f"'{c}'" for c in OIL_PRODUCING_COUNTRIES)
    event_code_list = ", ".join(f"'{c}'" for c in CONFLICT_EVENT_CODES)

    query = f"""
        SELECT
            DATE_TRUNC(
                PARSE_DATE('%Y%m%d', CAST(SQLDATE AS STRING)),
                WEEK(MONDAY)
            ) AS week,
            COUNT(*) AS event_count,
            AVG(GoldsteinScale) AS avg_goldstein,
            AVG(AvgTone) AS avg_tone,
            COUNTIF(QuadClass = 3) AS verbal_conflict_count,
            COUNTIF(QuadClass = 4) AS material_conflict_count,
            COUNTIF(EventRootCode IN ({event_code_list})) AS geopolitical_conflict_count
        FROM
            `gdelt-bq.gdeltv2.events`
        WHERE
            SQLDATE BETWEEN 20120101 AND 20261231
            AND EventRootCode IN ({event_code_list})
            AND (
                Actor1CountryCode IN ({country_list})
                OR Actor2CountryCode IN ({country_list})
            )
            AND GoldsteinScale IS NOT NULL
        GROUP BY
            week
        HAVING
            week IS NOT NULL
        ORDER BY
            week
    """

    df = client.query(query).to_dataframe(create_bqstorage_client=False)
    df["week"] = pd.to_datetime(df["week"])

    numeric_cols = [
        "event_count",
        "avg_goldstein",
        "avg_tone",
        "verbal_conflict_count",
        "material_conflict_count",
        "geopolitical_conflict_count",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["week", "event_count"])
    df = df.sort_values("week").reset_index(drop=True)
    return df


def load_to_bigquery(df: pd.DataFrame):
    client = get_bq_client()
    job_config = bigquery.LoadJobConfig(write_disposition="WRITE_TRUNCATE")
    job = client.load_table_from_dataframe(df, TABLE_ID, job_config=job_config)
    job.result()


def main():
    print("Fetching GDELT geopolitical conflict data from BigQuery...")
    df = fetch_gdelt_data()
    print(f"Fetched {len(df)} weekly rows.")

    load_to_bigquery(df)
    print(f"Loaded {len(df)} rows into {TABLE_ID}")


if __name__ == "__main__":
    main()
