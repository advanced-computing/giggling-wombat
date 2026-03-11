import matplotlib.pyplot as plt
import requests
import streamlit as st

from tests.eia_part3 import (
    build_df_from_eia_data,
    filter_since,
    latest_value,
    sum_by_week,
)
from validation import eia_schema

st.set_page_config(page_title="Weekly U.S. Petroleum Supply", layout="wide")
st.title("The Correlation between Weekly U.S. Petroleum Product Supplied and WTI Crude Oil Price")
st.subheader("Team Members: Irina, Indra")
st.caption("Source: U.S. Energy Information Administration (EIA)")

# =========================
# Project Proposal
# =========================
with st.expander("Project Proposal", expanded=False):

    st.subheader("Project Overview")
    st.write("""
    This project analyzes weekly U.S. petroleum product supplied data and
    WTI crude oil spot price data using the EIA API. Our goal is to explore
    how petroleum supply and crude oil prices evolve over time and whether
    they exhibit similar patterns during major economic or energy market events.
    """)

    st.subheader("Datasets")
    st.markdown("""
    - **Weekly U.S. Petroleum Product Supplied**
      https://www.eia.gov/opendata/browser/petroleum/cons/wpsup

    - **Weekly WTI Crude Oil Spot Price (RWTC)**
      https://www.eia.gov/opendata/browser/petroleum/pri/spt
    """)

    st.subheader("Research Questions")
    st.markdown("""
    1. How has U.S. petroleum product supplied changed since 2012?
    2. How has WTI crude oil price changed over the same period?
    3. Do petroleum supply and crude oil prices show similar patterns over time?
    4. Are there noticeable disruptions during major events such as COVID-19 period?
    """)
    st.subheader("Link to the notebook")
    st.markdown("[Project Notebook](https://github.com/advanced-computing/giggling-wombat/blob/main/project.ipynb)")

    st.subheader("Target Visualization")
    st.markdown("""
    - Weekly time-series line chart of U.S. petroleum product supplied
    - Weekly time-series line chart of WTI crude oil price
    - Visual comparison of trends between the two series
    """)

    st.subheader("Known Unknowns and Challenges")
    st.markdown("""
    - Petroleum product supplied is a proxy for demand rather than a direct measure
    - Weekly data can be noisy and may obscure long-term trends
    - Oil prices and supply may react to different economic forces
    - The project depends on API data retrieval instead of downloadable CSV files
    """)

st.divider()

API_KEY = st.secrets.get("EIA_API_KEY", None)
if not API_KEY:
    st.error("Missing EIA API key. Set it in Streamlit Secrets as EIA_API_KEY.")
    st.stop()

# --- API endpoint (supply) ---
SUPPLY_URL = (
    "https://api.eia.gov/v2/petroleum/cons/wpsup/data/"
    f"?api_key={API_KEY}"
    "&frequency=weekly"
    "&data[0]=value"
    "&sort[0][column]=period"
    "&sort[0][direction]=desc"
    "&offset=0&length=5000"
)


@st.cache_data(ttl=60 * 60)  # cache 1 hour
def fetch_supply_json(url: str) -> dict:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


try:
    payload = fetch_supply_json(SUPPLY_URL)
except Exception as e:
    st.error(f"Failed to fetch supply data: {e}")
    st.stop()

# IMPORTANT: build_df_from_eia_data expects list[dict], not the whole payload
data = payload.get("response", {}).get("data", [])
df = build_df_from_eia_data(
    data=data,
    period_col="period",
    value_col="value",
    new_date_col="week",
)

if df.empty:
    st.error("EIA returned no usable data for supply (empty after parsing).")
    st.stop()

# Filter (2012–present)
df = filter_since(df, date_col="week", start_date="2012-01-01")
df = eia_schema.validate(df)

weekly_total = sum_by_week(df, date_col="week", value_col="value")
if df.empty:
    st.error("No data after filtering to 2012–present. Check parsing or EIA response.")
    st.stop()

# Aggregate weekly (safe even if already weekly)
weekly_total = sum_by_week(df, date_col="week", value_col="value")

# Optional: rename for readability in plots/table
weekly_total = weekly_total.rename(columns={"value": "total_product_supplied"})

# Latest value
try:
    latest_total = latest_value(weekly_total, date_col="week", value_col="total_product_supplied")
except Exception:
    latest_total = None

# Metrics
c1, c2 = st.columns(2)
c1.metric("Weeks in dataset (2012–present)", f"{weekly_total.shape[0]:,}")
c2.metric(
    "Latest total (sum of products)",
    f"{latest_total:,.0f}" if latest_total is not None else "—",
)
st.divider()
st.subheader("Total Product Supplied (Weekly, All Products Summed)")

fig, ax = plt.subplots()
ax.plot(weekly_total["week"], weekly_total["total_product_supplied"])
ax.set_xlabel("Week")
ax.set_ylabel("Total Product Supplied (sum of EIA 'value')")
st.pyplot(fig)

with st.expander("Show data table"):
    st.dataframe(
        weekly_total.sort_values("week", ascending=False),
        use_container_width=True,
    )

st.caption(
    "Note: 'Product supplied' is often used as a proxy for consumption. "
    "This visualization is descriptive (not causal)."
)
