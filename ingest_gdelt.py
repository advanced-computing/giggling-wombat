import pandas_gbq

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_ID = "sipa-adv-c-giggling-wombat"
DESTINATION = f"{PROJECT_ID}.giggling_wombat.gdelt_weekly"

# GDELT EventRootCode descriptions for reference:
# 15 = Exhibit military posture
# 16 = Reduce relations
# 17 = Coerce
# 18 = Assault
# 19 = Fight
# 20 = Use unconventional mass violence

# ISO3 country codes for oil-producing countries
# ActionGeo_CountryCode uses ISO2 format in GDELT
OIL_COUNTRY_CODES = {
    "RS": "Russia",
    "IR": "Iran",
    "IZ": "Iraq",
    "SA": "Saudi Arabia",
    "LY": "Libya",
    "VE": "Venezuela",
    "AE": "United Arab Emirates",
    "KU": "Kuwait",
    "NI": "Nigeria",
    "AG": "Algeria",
}

# GDELT EventCode descriptions (subset of conflict codes)
EVENT_CODE_MAP = {
    "150": "Exhibit military posture",
    "151": "Demonstrate military posture",
    "152": "Mobilise/increase police power",
    "153": "Mobilise armed forces",
    "154": "Conduct military exercises",
    "155": "Conduct arms build-up",
    "160": "Reduce relations",
    "170": "Coerce",
    "171": "Seize/take possession",
    "172": "Conduct hunger strike",
    "173": "Conduct strike/boycott",
    "174": "Obstruct passage/access",
    "175": "Halt negotiations",
    "176": "Impose embargo/sanction",
    "180": "Assault",
    "181": "Physically assault",
    "182": "Sexually assault",
    "183": "Torture",
    "184": "Kill by physical assault",
    "185": "Attempt to assassinate",
    "186": "Assassinate",
    "190": "Use conventional military force",
    "191": "Impose blockade",
    "192": "Occupy territory",
    "193": "Fight with small arms",
    "194": "Fight with artillery",
    "195": "Employ aerial weapons",
    "196": "Violate ceasefire",
    "200": "Use unconventional mass violence",
    "201": "Engage in mass expulsion",
    "202": "Engage in mass killings",
    "203": "Engage in ethnic cleansing",
    "204": "Use weapons of mass destruction",
}

QUERY = f"""
SELECT
    DATE_TRUNC(PARSE_DATE('%Y%m%d', CAST(SQLDATE AS STRING)), WEEK) AS week,
    ActionGeo_CountryCode                                            AS country_code,
    EventRootCode                                                    AS event_root_code,
    EventCode                                                        AS event_code,
    COUNT(*)                                                         AS event_count,
    SUM(NumMentions)                                                 AS total_mentions,
    AVG(GoldsteinScale)                                              AS avg_goldstein,
    AVG(AvgTone)                                                     AS avg_tone
FROM `gdelt-bq.gdeltv2.events`
WHERE SQLDATE BETWEEN 20120101 AND 20261231
  AND EventRootCode IN ('15','16','17','18','19','20')
  AND ActionGeo_CountryCode IN ({", ".join(f"'{k}'" for k in OIL_COUNTRY_CODES)})
GROUP BY week, country_code, event_root_code, event_code
ORDER BY week
"""


def ingest():
    print("Querying GDELT public dataset...")
    df = pandas_gbq.read_gbq(QUERY, project_id=PROJECT_ID)
    print(f"Fetched {len(df)} rows.")

    # Map country code to country name
    df["country"] = df["country_code"].map(OIL_COUNTRY_CODES)

    # Map event code to description
    df["event_code_desc"] = df["event_code"].map(EVENT_CODE_MAP).fillna("Other")

    print(df.head(10))
    print(f"\nCountries: {df['country'].value_counts().to_dict()}")
    print(f"Event root codes: {df['event_root_code'].value_counts().to_dict()}")

    print(f"\nUploading to BigQuery: {DESTINATION}...")
    pandas_gbq.to_gbq(
        df,
        destination_table=DESTINATION,
        project_id=PROJECT_ID,
        if_exists="replace",
    )
    print(f"Done! Table {DESTINATION} updated.")


if __name__ == "__main__":
    ingest()
