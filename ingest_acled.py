import pandas as pd
import pandas_gbq
import requests

# ── Config ────────────────────────────────────────────────────────────────────
ACLED_EMAIL    = "ims2170@columbia.edu"
ACLED_PASSWORD = "Ms1994ms1994"

PROJECT_ID  = "sipa-adv-c-giggling-wombat"
DESTINATION = f"{PROJECT_ID}.giggling_wombat.acled_weekly"

HTTP_OK    = 200
PAGE_SIZE  = 5000
DATE_RANGE = "2012-01-01|2026-12-31"
ACLED_FIELDS = (
    "event_date|country|disorder_type|event_type"
    "|actor1|civilian_targeting|fatalities"
)

OIL_COUNTRIES = [
    "Russia", "Iran", "Iraq", "Saudi Arabia", "Libya",
    "Venezuela", "United Arab Emirates", "Kuwait", "Nigeria", "Algeria",
]


# ── Step 1: Get OAuth token ───────────────────────────────────────────────────
def get_access_token(username, password):
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "username":   username,
        "password":   password,
        "grant_type": "password",
        "client_id":  "acled",
        "scope":      "authenticated",
    }
    r = requests.post(
        "https://acleddata.com/oauth/token", headers=headers, data=data
    )
    if r.status_code == HTTP_OK:
        print("Token acquired!")
        return r.json()["access_token"]
    raise Exception(f"Auth failed: {r.status_code} {r.text}")


# ── Step 2: Fetch ACLED data with pagination ──────────────────────────────────
def fetch_acled(token):
    all_data = []

    for country in OIL_COUNTRIES:
        print(f"Fetching: {country}...")
        page = 1
        country_total = 0

        while True:
            params = {
                "country":          country,
                "event_date":       DATE_RANGE,
                "event_date_where": "BETWEEN",
                "fields":           ACLED_FIELDS,
                "limit":            PAGE_SIZE,
                "page":             page,
            }
            r = requests.get(
                "https://acleddata.com/api/acled/read?_format=json",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type":  "application/json",
                },
                params=params,
            )
            if r.json().get("status") == HTTP_OK:
                data = r.json()["data"]
                if not data:
                    break
                all_data.extend(data)
                country_total += len(data)
                print(f"  → page {page}: {len(data)} rows")
                if len(data) < PAGE_SIZE:
                    break
                page += 1
            else:
                print(f"  → Error: {r.json()}")
                break

        print(f"  → {country} total: {country_total} rows\n")

    return pd.DataFrame(all_data)


# ── Step 3: Aggregate to weekly ───────────────────────────────────────────────
def aggregate_weekly(df):
    df["event_date"] = pd.to_datetime(df["event_date"])
    df["fatalities"] = pd.to_numeric(df["fatalities"], errors="coerce").fillna(0)
    df["week"]       = df["event_date"].dt.to_period("W").apply(
        lambda r: r.start_time
    )

    weekly = df.groupby([
        "week",
        "country",
        "disorder_type",
        "event_type",
        "actor1",
        "civilian_targeting",
    ]).agg(
        event_count=("event_date", "count"),
        total_fatalities=("fatalities", "sum"),
    ).reset_index()

    return weekly


# ── Step 4: Upload to BigQuery ────────────────────────────────────────────────
def upload_to_bq(df):
    pandas_gbq.to_gbq(
        df,
        destination_table=DESTINATION,
        project_id=PROJECT_ID,
        if_exists="replace",
    )
    print(f"Done! Table {DESTINATION} updated.")


# ── Main ──────────────────────────────────────────────────────────────────────
def ingest():
    print("Getting ACLED access token...")
    token = get_access_token(ACLED_EMAIL, ACLED_PASSWORD)

    print("Fetching ACLED conflict data...\n")
    df = fetch_acled(token)
    print(f"Total rows fetched: {len(df)}")

    print("\nAggregating to weekly...")
    weekly = aggregate_weekly(df)
    print(f"Weekly rows: {len(weekly)}")
    print(weekly.head(10))

    print("\nUploading to BigQuery...")
    upload_to_bq(weekly)


if __name__ == "__main__":
    ingest()
