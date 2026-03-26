import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

from tests.eia_part3 import latest_value

st.set_page_config(page_title="WTI Price", layout="wide")
st.title("WTI Crude Oil Price")
st.caption("Source: U.S. Energy Information Administration (EIA)")

PROJECT_ID = "sipa-adv-c-giggling-wombat"
TABLE_ID = f"{PROJECT_ID}.petroleum_supply.weekly_wti"


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

start_week = st.sidebar.date_input(
    "Start week",
    value=min_week,
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

latest_change = filtered_wti["weekly_change"].iloc[-1]
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
st.subheader("WTI Price Over Time (Weekly)")

fig, ax = plt.subplots(figsize=(8, 4))
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

st.divider()
st.subheader("Weekly Change in WTI Price")

fig2, ax2 = plt.subplots(figsize=(8, 4))
ax2.plot(filtered_wti["week"], filtered_wti["weekly_change"])
ax2.axhline(0)
ax2.set_xlabel("Week")
ax2.set_ylabel("Weekly change ($/barrel)")
st.pyplot(fig2)

st.divider()
st.subheader("Average WTI Price by Year")

yearly_avg = (
    filtered_wti.groupby("year", as_index=False)["wti_price"]
    .mean()
    .rename(columns={"wti_price": "avg_wti_price"})
)

fig3, ax3 = plt.subplots(figsize=(8, 4))
ax3.bar(yearly_avg["year"], yearly_avg["avg_wti_price"])
ax3.set_xlabel("Year")
ax3.set_ylabel("Average WTI price ($/barrel)")
st.pyplot(fig3)

with st.expander("Show data table"):
    st.dataframe(
        filtered_wti.sort_values("week", ascending=False),
        use_container_width=True,
    )
