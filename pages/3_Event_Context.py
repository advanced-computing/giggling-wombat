import time

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

start_time = time.time()

st.set_page_config(page_title="Event Context", layout="wide")

# =========================
# Sidebar title
# =========================
st.sidebar.markdown(
    """
    <h1 style="font-size: 1.5rem; line-height: 1.2; margin-bottom: 0.2rem;">
        U.S. Petroleum & WTI Weekly Monitor
    </h1>
    """,
    unsafe_allow_html=True,
)
st.sidebar.caption("Source: EIA + GDELT")
st.sidebar.divider()

# =========================
# Main page header
# =========================
st.title("Event Context and External Shocks")
st.caption(
    "This page identifies weeks with unusually large movements in WTI price "
    "and petroleum supply, then compares them with a general event dataset "
    "aggregated from GDELT to assess whether those anomaly weeks coincide "
    "with intense or negative external event conditions."
)

PROJECT_ID = "sipa-adv-c-giggling-wombat"
DATASET_ID = "petroleum_supply"

WTI_TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.weekly_wti"
SUPPLY_TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.weekly_supply"
GDELT_TABLE_ID = f"{PROJECT_ID}.{DATASET_ID}.weekly_gdelt_events"

DEFAULT_START_WEEK = pd.to_datetime("2015-02-20").date()
TWO_COLUMN_LAYOUT = 2
THREE_COLUMN_LAYOUT = 3
TOP_ANOMALY_WEEKS = 10
ANOMALY_BAR_COLOR = "darkorange"


@st.cache_resource
def get_bq_client():
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"]
    )
    return bigquery.Client(
        credentials=credentials,
        project=credentials.project_id,
    )


@st.cache_data(ttl=60 * 60)
def load_wti_data() -> pd.DataFrame:
    client = get_bq_client()
    query = f"""
        SELECT week, wti_price
        FROM `{WTI_TABLE_ID}`
        ORDER BY week
    """
    df = client.query(query).to_dataframe(create_bqstorage_client=False)
    df["week"] = pd.to_datetime(df["week"])
    df["wti_price"] = pd.to_numeric(df["wti_price"], errors="coerce")
    df = df.dropna(subset=["week", "wti_price"])
    return df


@st.cache_data(ttl=60 * 60)
def load_supply_data() -> pd.DataFrame:
    client = get_bq_client()
    query = f"""
        SELECT week, total_supply
        FROM `{SUPPLY_TABLE_ID}`
        ORDER BY week
    """
    df = client.query(query).to_dataframe(create_bqstorage_client=False)
    df["week"] = pd.to_datetime(df["week"])
    df["total_supply"] = pd.to_numeric(df["total_supply"], errors="coerce")
    df = df.dropna(subset=["week", "total_supply"])
    return df


@st.cache_data(ttl=60 * 60)
def load_gdelt_data() -> pd.DataFrame:
    client = get_bq_client()
    query = f"""
        SELECT
            week,
            event_count,
            avg_goldstein,
            avg_tone,
            verbal_cooperation_count,
            material_cooperation_count,
            verbal_conflict_count,
            material_conflict_count
        FROM `{GDELT_TABLE_ID}`
        ORDER BY week
    """
    df = client.query(query).to_dataframe(create_bqstorage_client=False)
    df["week"] = pd.to_datetime(df["week"])

    numeric_cols = [
        "event_count",
        "avg_goldstein",
        "avg_tone",
        "verbal_cooperation_count",
        "material_cooperation_count",
        "verbal_conflict_count",
        "material_conflict_count",
    ]

    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["week", "event_count"])
    return df


def build_anomaly_table(merged_df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    anomaly_candidates = merged_df.copy()
    anomaly_candidates["abs_wti_change"] = anomaly_candidates["wti_weekly_change"].abs()
    anomaly_candidates["abs_supply_change"] = anomaly_candidates["supply_weekly_change"].abs()
    anomaly_candidates["combined_shock_score"] = anomaly_candidates["abs_wti_change"].fillna(
        0
    ) + anomaly_candidates["abs_supply_change"].fillna(0)

    anomaly_table = (
        anomaly_candidates.sort_values("combined_shock_score", ascending=False)
        .head(top_n)
        .loc[
            :,
            [
                "week",
                "combined_shock_score",
                "wti_weekly_change",
                "supply_weekly_change",
                "event_count",
                "avg_goldstein",
                "avg_tone",
                "verbal_cooperation_count",
                "material_cooperation_count",
                "verbal_conflict_count",
                "material_conflict_count",
            ],
        ]
        .sort_values("week", ascending=False)
        .reset_index(drop=True)
    )

    return anomaly_table


try:
    weekly_wti = load_wti_data()
except Exception as e:
    st.error(f"Failed to load WTI data from BigQuery: {e}")
    st.stop()

try:
    weekly_supply = load_supply_data()
except Exception as e:
    st.error(f"Failed to load supply data from BigQuery: {e}")
    st.stop()

try:
    weekly_gdelt = load_gdelt_data()
except Exception as e:
    st.error(f"Failed to load GDELT event data from BigQuery: {e}")
    st.stop()

if weekly_wti.empty:
    st.error("No WTI data found in BigQuery.")
    st.stop()

if weekly_supply.empty:
    st.error("No supply data found in BigQuery.")
    st.stop()

if weekly_gdelt.empty:
    st.error("No GDELT event data found in BigQuery.")
    st.stop()

weekly_wti = weekly_wti.sort_values("week").copy()
weekly_supply = weekly_supply.sort_values("week").copy()
weekly_gdelt = weekly_gdelt.sort_values("week").copy()

weekly_wti["wti_weekly_change"] = weekly_wti["wti_price"].diff()
weekly_supply["supply_weekly_change"] = weekly_supply["total_supply"].diff()

merged = (
    weekly_wti.merge(weekly_supply, on="week", how="inner")
    .merge(weekly_gdelt, on="week", how="inner")
    .sort_values("week")
    .reset_index(drop=True)
)

if merged.empty:
    st.error("No overlapping weekly data found across WTI, supply, and GDELT.")
    st.stop()

# =========================
# Sidebar filters
# =========================
st.sidebar.header("Filters")

min_week = merged["week"].min().date()
max_week = merged["week"].max().date()

default_start_week = DEFAULT_START_WEEK if min_week <= DEFAULT_START_WEEK <= max_week else min_week

start_week = st.sidebar.date_input(
    "Start week",
    value=default_start_week,
    min_value=min_week,
    max_value=max_week,
    key="event_start_week",
)

end_week = st.sidebar.date_input(
    "End week",
    value=max_week,
    min_value=min_week,
    max_value=max_week,
    key="event_end_week",
)

if start_week > end_week:
    st.error("Start week must be earlier than or equal to end week.")
    st.stop()

filtered = merged[
    (merged["week"] >= pd.to_datetime(start_week)) & (merged["week"] <= pd.to_datetime(end_week))
].copy()

if filtered.empty:
    st.warning("No overlapping data available for the selected date range.")
    st.stop()

# =========================
# Summary metrics
# =========================
c1, c2, c3 = st.columns(THREE_COLUMN_LAYOUT)
c1.metric("Weeks in selected range", f"{filtered.shape[0]:,}")
c2.metric("Average weekly event count", f"{filtered['event_count'].mean():,.0f}")
c3.metric("Average event tone", f"{filtered['avg_tone'].mean():.2f}")

st.caption(
    "This page uses a general event dataset to compare broad event activity with "
    "weekly changes in WTI and petroleum supply. It is descriptive rather than causal."
)

st.divider()

# =========================
# Two side-by-side charts
# =========================
left_col, right_col = st.columns(TWO_COLUMN_LAYOUT)

with left_col:
    st.subheader("Weekly Event Count")

    fig1, ax1 = plt.subplots(figsize=(7, 4))
    ax1.plot(filtered["week"], filtered["event_count"])
    ax1.set_xlabel("Week")
    ax1.set_ylabel("Event count")
    st.pyplot(fig1)

    st.caption(
        "This chart shows how many GDELT-recorded events occurred each week. "
        "Use it to see whether broader event activity rises during weeks when "
        "WTI or petroleum supply experiences unusual movement."
    )

with right_col:
    st.subheader("Average Event Tone")

    fig2, ax2 = plt.subplots(figsize=(7, 4))
    ax2.plot(filtered["week"], filtered["avg_tone"])
    ax2.axhline(0, color="gray", linewidth=1)
    ax2.set_xlabel("Week")
    ax2.set_ylabel("Average tone")
    st.pyplot(fig2)

    st.caption(
        "This chart tracks the average tone of events in each week. "
        "More negative values suggest a more adverse event environment, which may "
        "help contextualize stress periods in the energy data."
    )

st.divider()
st.subheader("Weekly Event Composition")

fig3, ax3 = plt.subplots(figsize=(10, 4.5))
ax3.stackplot(
    filtered["week"],
    filtered["verbal_cooperation_count"],
    filtered["material_cooperation_count"],
    filtered["verbal_conflict_count"],
    filtered["material_conflict_count"],
    labels=[
        "Verbal cooperation",
        "Material cooperation",
        "Verbal conflict",
        "Material conflict",
    ],
)
ax3.set_xlabel("Week")
ax3.set_ylabel("Event count")
ax3.legend(loc="upper left")
st.pyplot(fig3)

st.caption(
    "This stacked chart breaks weekly events into the four broad GDELT classes. "
    "It helps identify whether spikes in total event activity are driven more by "
    "cooperation or by conflict-oriented events."
)

st.divider()
st.subheader("Top Anomaly Weeks and Their Event Conditions")

st.write(
    """
    **How to read this table:**
    This table first identifies the weeks with the largest combined movement in
    **WTI price** and **petroleum supply**. It then reports the broader event
    environment in those same weeks using GDELT, including total event count,
    average Goldstein score, average tone, and the four broad GDELT event classes.
    The goal is to assess whether major energy anomalies tend to coincide with
    unusually intense or negative external conditions.
    """
)

anomaly_table = build_anomaly_table(filtered, TOP_ANOMALY_WEEKS)

if anomaly_table.empty:
    st.warning("No anomaly weeks available in the selected date range.")
else:
    st.subheader("Anomaly Shock Score by Week")

    chart_df = anomaly_table.copy()
    chart_df["week_label"] = chart_df["week"].dt.strftime("%Y-%m-%d")
    chart_df = chart_df.sort_values("combined_shock_score", ascending=True)

    fig4, ax4 = plt.subplots(figsize=(5, 3))
    ax4.barh(
        chart_df["week_label"],
        chart_df["combined_shock_score"],
        color=ANOMALY_BAR_COLOR,
    )
    ax4.set_xlabel("Combined shock score")
    ax4.set_ylabel("Week")
    st.pyplot(fig4)

    st.caption(
        "This chart visualizes the anomaly ranking used to build the table below. "
        "Higher values indicate larger combined weekly movement in WTI price and "
        "petroleum supply."
    )

    display_table = anomaly_table.copy()
    display_table["week"] = display_table["week"].dt.strftime("%Y-%m-%d")

    st.dataframe(display_table, width="stretch")

with st.expander("Show merged weekly data"):
    merged_display = filtered.sort_values("week", ascending=False).copy()
    merged_display["week"] = merged_display["week"].dt.strftime("%Y-%m-%d")
    st.dataframe(merged_display, width="stretch")

elapsed = time.time() - start_time
st.caption(f"Page loaded in {elapsed:.2f} seconds")
