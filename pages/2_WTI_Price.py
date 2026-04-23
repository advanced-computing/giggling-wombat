import time

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

from tests.eia_part3 import latest_value

start_time = time.time()

st.set_page_config(page_title="WTI Price", layout="wide")

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
st.sidebar.caption("Source: EIA")
st.sidebar.divider()

# =========================
# Main page header
# =========================
st.title("WTI Crude Oil Price")
st.caption("Source: U.S. Energy Information Administration (EIA)")

PROJECT_ID = "sipa-adv-c-giggling-wombat"
TABLE_ID = f"{PROJECT_ID}.petroleum_supply.weekly_wti"

MIN_INTERPRETATION_POINTS = 4
PRICE_MOVE_THRESHOLD = 1
RECENT_RANGE_WEEKS = 12
HIGH_NEAR_THRESHOLD = 0.98
LOW_NEAR_THRESHOLD = 1.02
VOLATILITY_STD_THRESHOLD = 5
TOP_HIGHLIGHT_YEARS = 5

YEAR_BAR_DEFAULT_COLOR = "steelblue"
YEAR_BAR_HIGHLIGHT_COLOR = "darkorange"

DEFAULT_START_WEEK = pd.to_datetime("2012-08-10").date()


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
        SELECT week, series, wti_price
        FROM `{TABLE_ID}`
        ORDER BY week
    """
    df = client.query(query).to_dataframe()
    df["week"] = pd.to_datetime(df["week"])
    df["wti_price"] = pd.to_numeric(df["wti_price"], errors="coerce")
    df = df.dropna(subset=["week", "wti_price"])
    return df


def generate_wti_interpretation(df: pd.DataFrame, ma_window: int) -> str:
    if df.empty or len(df) < MIN_INTERPRETATION_POINTS:
        return "Not enough data to generate interpretation."

    df = df.sort_values("week").reset_index(drop=True)

    latest_price = df["wti_price"].iloc[-1]
    prev_price = df["wti_price"].iloc[-2]
    latest_change = latest_price - prev_price
    latest_pct_change = (latest_change / prev_price * 100) if prev_price != 0 else 0

    recent_avg = df["wti_price"].tail(ma_window).mean()

    recent_window = df["wti_price"].tail(min(RECENT_RANGE_WEEKS, len(df)))
    high_recent = recent_window.max()
    low_recent = recent_window.min()
    recent_std = recent_window.std()

    if latest_change > PRICE_MOVE_THRESHOLD:
        trend_text = (
            f"WTI increased by ${latest_change:.2f} "
            f"({latest_pct_change:.2f}%) from the previous week, "
            "suggesting short-term upward momentum."
        )
    elif latest_change < -PRICE_MOVE_THRESHOLD:
        trend_text = (
            f"WTI decreased by ${abs(latest_change):.2f} "
            f"({abs(latest_pct_change):.2f}%) from the previous week, "
            "suggesting short-term downward pressure."
        )
    else:
        trend_text = (
            f"WTI changed only slightly by ${latest_change:.2f} "
            f"({latest_pct_change:.2f}%) from the previous week, "
            "indicating relatively stable short-term movement."
        )

    if latest_price > recent_avg:
        avg_text = (
            f"The latest price (${latest_price:.2f}) is above the "
            f"{ma_window}-week moving average (${recent_avg:.2f}), "
            "which may indicate stronger recent market conditions."
        )
    elif latest_price < recent_avg:
        avg_text = (
            f"The latest price (${latest_price:.2f}) is below the "
            f"{ma_window}-week moving average (${recent_avg:.2f}), "
            "which may suggest weaker short-term pricing."
        )
    else:
        avg_text = (
            f"The latest price is in line with the {ma_window}-week "
            f"moving average (${recent_avg:.2f})."
        )

    if latest_price >= high_recent * HIGH_NEAR_THRESHOLD:
        range_text = (
            f"WTI is near its recent {RECENT_RANGE_WEEKS}-week high "
            f"(${high_recent:.2f}), indicating that prices remain elevated "
            "relative to recent history."
        )
    elif latest_price <= low_recent * LOW_NEAR_THRESHOLD:
        range_text = (
            f"WTI is near its recent {RECENT_RANGE_WEEKS}-week low "
            f"(${low_recent:.2f}), suggesting relatively weak pricing "
            "compared with recent weeks."
        )
    else:
        range_text = (
            f"WTI remains within its recent {RECENT_RANGE_WEEKS}-week range "
            f"of ${low_recent:.2f} to ${high_recent:.2f}, indicating a more "
            "moderate position in the recent trend."
        )

    if pd.notna(recent_std) and recent_std > VOLATILITY_STD_THRESHOLD:
        vol_text = "Recent price movements have been relatively volatile."
    else:
        vol_text = "Recent price movements have been relatively stable."

    return f"{trend_text} {avg_text} {range_text} {vol_text}"


def find_top_highest_years(yearly_avg: pd.DataFrame, top_n: int) -> set[int]:
    if yearly_avg.empty:
        return set()

    top_years = (
        yearly_avg.sort_values("avg_wti_price", ascending=False).head(top_n)["year"].tolist()
    )
    return set(top_years)


try:
    weekly_wti = load_wti_data()
except Exception as e:
    st.error(f"Failed to load WTI data from BigQuery: {e}")
    st.stop()

if weekly_wti.empty:
    st.error("No WTI data found in BigQuery.")
    st.stop()

# =========================
# Sidebar Filters
# =========================
st.sidebar.header("Filters")

min_week = weekly_wti["week"].min().date()
max_week = weekly_wti["week"].max().date()

default_start_week = DEFAULT_START_WEEK if min_week <= DEFAULT_START_WEEK <= max_week else min_week

start_week = st.sidebar.date_input(
    "Start week",
    value=default_start_week,
    min_value=min_week,
    max_value=max_week,
    key="wti_start_week",
)

end_week = st.sidebar.date_input(
    "End week",
    value=max_week,
    min_value=min_week,
    max_value=max_week,
    key="wti_end_week",
)

ma_window = st.sidebar.selectbox(
    "Moving average window",
    options=[4, 8, 12],
    index=0,
    key="wti_ma_window",
)

if start_week > end_week:
    st.error("Start week must be earlier than or equal to end week.")
    st.stop()

filtered_wti = weekly_wti[
    (weekly_wti["week"] >= pd.to_datetime(start_week))
    & (weekly_wti["week"] <= pd.to_datetime(end_week))
].copy()

if filtered_wti.empty:
    st.warning("No WTI data available for the selected date range.")
    st.stop()

filtered_wti = filtered_wti.sort_values("week").copy()
filtered_wti["wti_ma"] = filtered_wti["wti_price"].rolling(ma_window).mean()
filtered_wti["weekly_change"] = filtered_wti["wti_price"].diff()
filtered_wti["year"] = filtered_wti["week"].dt.year

try:
    latest_price = latest_value(
        filtered_wti,
        date_col="week",
        value_col="wti_price",
    )
except Exception:
    latest_price = None

avg_price = filtered_wti["wti_price"].mean()

c1, c2, c3 = st.columns(3)
c1.metric("Weeks in selected range", f"{filtered_wti.shape[0]:,}")
c2.metric(
    "Latest WTI ($/barrel)",
    f"{latest_price:,.2f}" if latest_price is not None else "—",
)
c3.metric(
    "Average WTI ($/barrel)",
    f"{avg_price:,.2f}" if pd.notna(avg_price) else "—",
)

st.divider()

# =========================
# Two charts side by side
# =========================
left_col, right_col = st.columns(2)

with left_col:
    st.subheader("WTI Price Over Time (Weekly)")

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(filtered_wti["week"], filtered_wti["wti_price"], label="WTI price")
    ax.plot(
        filtered_wti["week"],
        filtered_wti["wti_ma"],
        label=f"{ma_window}-week moving average",
    )
    ax.set_xlabel("Week")
    ax.set_ylabel("WTI price ($/barrel)")
    ax.legend()
    st.pyplot(fig)

with right_col:
    st.subheader("Weekly Change in WTI Price")

    fig2, ax2 = plt.subplots(figsize=(7, 4))
    ax2.plot(filtered_wti["week"], filtered_wti["weekly_change"])
    ax2.axhline(0, color="gray", linewidth=1)
    ax2.set_xlabel("Week")
    ax2.set_ylabel("Weekly change ($/barrel)")
    st.pyplot(fig2)

st.divider()
st.subheader("Real-Time Interpretation")
interpretation = generate_wti_interpretation(filtered_wti, ma_window)
st.markdown(interpretation.replace("$", r"\$"))

st.divider()
st.subheader("Average WTI Price by Year")

yearly_avg = (
    filtered_wti.groupby("year", as_index=False)["wti_price"]
    .mean()
    .rename(columns={"wti_price": "avg_wti_price"})
    .sort_values("year")
    .reset_index(drop=True)
)

highlight_years = find_top_highest_years(yearly_avg, TOP_HIGHLIGHT_YEARS)

bar_colors = [
    YEAR_BAR_HIGHLIGHT_COLOR if year in highlight_years else YEAR_BAR_DEFAULT_COLOR
    for year in yearly_avg["year"]
]

fig3, ax3 = plt.subplots(figsize=(8, 5))
ax3.barh(
    yearly_avg["year"].astype(str),
    yearly_avg["avg_wti_price"],
    color=bar_colors,
)
ax3.set_xlabel("Average WTI price ($/barrel)")
ax3.set_ylabel("Year")
st.pyplot(fig3)

if highlight_years:
    top_year_text = ", ".join(
        str(year)
        for year in yearly_avg.sort_values("avg_wti_price", ascending=False)
        .head(TOP_HIGHLIGHT_YEARS)["year"]
        .tolist()
    )
    st.caption(
        f"Top {TOP_HIGHLIGHT_YEARS} highest average-price years highlighted in orange: "
        f"{top_year_text}"
    )

with st.expander("Show data table"):
    st.dataframe(
        filtered_wti.sort_values("week", ascending=False),
        use_container_width=True,
    )

elapsed = time.time() - start_time
st.caption(f"Page loaded in {elapsed:.2f} seconds")
