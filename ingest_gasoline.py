import pandas as pd
import pandas_gbq
import requests

# ── Config ────────────────────────────────────────────────────────────────────
API_KEY = "qIgxlen05S7xFsozHUuJ4HXned44qT8RF3OewtSv"
PROJECT_ID = "sipa-adv-c-giggling-wombat"
DESTINATION = f"{PROJECT_ID}.giggling_wombat.weekly_gasoline"

# Weekly U.S. Regular All Formulations Retail Gasoline Prices ($/gallon)
GASOLINE_URL = (
    "https://api.eia.gov/v2/petroleum/pri/gnd/data/"
    f"?api_key={API_KEY}"
    "&frequency=weekly"
    "&data[0]=value"
    "&facets[series][]=EMM_EPM0_PTE_NUS_DPG"
    "&sort[0][column]=period"
    "&sort[0][direction]=asc"
    "&offset=0&length=5000"
)


def fetch_gasoline() -> pd.DataFrame:
    print("Fetching gasoline price data from EIA...")
    r = requests.get(GASOLINE_URL, timeout=30)
    r.raise_for_status()

    data = r.json().get("response", {}).get("data", [])
    df = pd.DataFrame(data)

    if df.empty:
        raise ValueError("No gasoline data returned from EIA.")

    df["week"] = pd.to_datetime(df["period"], errors="coerce")
    df["gasoline_price"] = pd.to_numeric(df["value"], errors="coerce")

    df = df.dropna(subset=["week", "gasoline_price"])
    df = df[df["week"] >= pd.Timestamp("2012-01-01")]
    df = df[["week", "gasoline_price"]].sort_values("week").reset_index(drop=True)

    print(f"Fetched {len(df)} rows.")
    print(df.tail(5))
    return df


def upload_to_bq(df: pd.DataFrame):
    print(f"\nUploading to BigQuery: {DESTINATION}...")
    pandas_gbq.to_gbq(
        df,
        destination_table=DESTINATION,
        project_id=PROJECT_ID,
        if_exists="replace",
    )
    print("Done!")


def ingest():
    df = fetch_gasoline()
    upload_to_bq(df)


if __name__ == "__main__":
    ingest()
