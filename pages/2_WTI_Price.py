import matplotlib.pyplot as plt
import pandas as pd
import requests
import streamlit as st

from tests.eia_part3 import (
    build_df_from_eia_data,
    filter_since,
    latest_value,
    sum_by_week,
)

st.set_page_config(page_title="WTI Price", layout="wide")
st.title("WTI Crude Oil Price")
st.caption("Source: U.S. Energy Information Administration (EIA)")

API_KEY = st.secrets.get("EIA_API_KEY", None)
if not API_KEY:
    st.error("Missing EIA API key. Set it in Streamlit Secrets as EIA_API_KEY.")
    st.stop()

URL = (
    "https://api.eia.gov/v2/petroleum/pri/spt/data/"
    f"?api_key={API_KEY}"
    "&frequency=weekly"
    "&data[0]=value"
    "&facets[series][]=RWTC"
    "&sort[0][column]=period"
    "&sort[0][direction]=desc"
    "&offset=0&length=5000"
)


@st.cache_data(ttl=60 * 60)
def fetch_wti_json(url: str) -> dict:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


try:
    payload = fetch_wti_json(URL)
except Exception as e:
    st.error(f"Failed to fetch WTI data: {e}")
    st.stop()

# IMPORTANT: build_df_from_eia_data expects list[dict]
data = payload.get("response", {}).get("data", [])
df = build_df_from_eia_data(
    data=data,
    period_col="period",
    value_col="value",
    new_date_col="week",
)

if df.empty:
    st.error("EIA returned no usable data for WTI (empty after parsing).")
    st.stop()

# Filter to 2012–present
df = filter_since(df, date_col="week", start_date="2012-01-01")
if df.empty:
    st.error("No WTI data after filtering to 2012–present. Check parsing or EIA response.")
    st.stop()

# Aggregate weekly (safe even if already weekly)
weekly_wti = sum_by_week(df, date_col="week", value_col="value").rename(
    columns={"value": "wti_price"}
)

# =========================
# Interactive Week Filter
# =========================
st.subheader("Filter by Week")

min_week = weekly_wti["week"].min().date()
max_week = weekly_wti["week"].max().date()

col1, col2 = st.columns(2)

with col1:
    start_week = st.date_input(
        "Start week",
        value=min_week,
        min_value=min_week,
        max_value=max_week,
        key="wti_start_week",
    )

with col2:
    end_week = st.date_input(
        "End week",
        value=max_week,
        min_value=min_week,
        max_value=max_week,
        key="wti_end_week",
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

# Latest price
try:
    latest_price = latest_value(
        filtered_wti,
        date_col="week",
        value_col="wti_price",
    )
except Exception:
    latest_price = None

c1, c2 = st.columns(2)
c1.metric("Weeks in selected range", f"{filtered_wti.shape[0]:,}")
c2.metric(
    "Latest WTI ($/barrel)",
    f"{latest_price:,.2f}" if latest_price is not None else "—",
)

st.divider()
st.subheader("WTI Price Over Time (Weekly)")

fig, ax = plt.subplots()
ax.plot(filtered_wti["week"], filtered_wti["wti_price"])
ax.set_xlabel("Week")
ax.set_ylabel("WTI price ($/barrel)")
st.pyplot(fig)

with st.expander("Show data table"):
    st.dataframe(
        filtered_wti.sort_values("week", ascending=False),
        use_container_width=True,
    )
