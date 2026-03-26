import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

from tests.eia_part3 import latest_value

st.set_page_config(page_title="Weekly U.S. Petroleum Supply", layout="wide")
st.title("The Correlation between Weekly U.S. Petroleum Product Supplied and WTI Crude Oil Price")
st.subheader("Team Members: Irina, Indra")
st.caption("Source: U.S. Energy Information Administration (EIA)")

# =========================
# Project Proposal
# =========================
with st.expander("Project Proposal", expanded=False):
    st.subheader("Project Overview")
    st.write(
        """
        This project analyzes weekly U.S. petroleum product supplied data and
        WTI crude oil spot price data using the EIA API. Our goal is to explore
        how petroleum supply and crude oil prices evolve over time and whether
        they exhibit similar patterns during major economic or energy market events.
        """
    )

    st.subheader("Datasets")
    st.markdown(
        """
        - **Weekly U.S. Petroleum Product Supplied**
          https://www.eia.gov/opendata/browser/petroleum/cons/wpsup

        - **Weekly WTI Crude Oil Spot Price (RWTC)**
          https://www.eia.gov/opendata/browser/petroleum/pri/spt
        """
    )

    st.subheader("Research Questions")
    st.markdown(
        """
        1. How has U.S. petroleum product supplied changed since 2012?
        2. How has WTI crude oil price changed over the same period?
        3. Do petroleum supply and crude oil prices show similar patterns over time?
        4. Are there noticeable disruptions during major events such as the COVID-19 period?
        """
    )

    st.subheader("Link to the notebook")
    st.markdown(
        "[Project Notebook](https://github.com/advanced-computing/giggling-wombat/blob/main/project.ipynb)"
    )

    st.subheader("Target Visualization")
    st.markdown(
        """
        - Weekly time-series line chart of U.S. petroleum product supplied
        - Weekly time-series line chart of WTI crude oil price
        - Visual comparison of trends between the two series
        """
    )

    st.subheader("Known Unknowns and Challenges")
    st.markdown(
        """
        - Petroleum product supplied is a proxy for demand rather than a direct measure
        - Weekly data can be noisy and may obscure long-term trends
        - Oil prices and supply may react to different economic forces
        - The project depends on API data retrieval instead of downloadable CSV files
        """
    )

st.divider()

PROJECT_ID = "sipa-adv-c-giggling-wombat"
TABLE_ID = f"{PROJECT_ID}.petroleum_supply.weekly_supply"


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
def load_supply_data() -> pd.DataFrame:
    client = get_bq_client()
    query = f"""
        SELECT week, total_product_supplied
        FROM `{TABLE_ID}`
        ORDER BY week
    """
    df = client.query(query).to_dataframe()
    df["week"] = pd.to_datetime(df["week"])
    df["total_product_supplied"] = pd.to_numeric(df["total_product_supplied"], errors="coerce")
    df = df.dropna(subset=["week", "total_product_supplied"])
    return df


@st.cache_data(ttl=60 * 60)
def load_supply_product_data() -> pd.DataFrame:
    client = get_bq_client()
    query = """
        SELECT week, product_name, product_supplied
        FROM `sipa-adv-c-giggling-wombat.petroleum_supply.weekly_supply_by_product`
        ORDER BY week
    """
    df = client.query(query).to_dataframe()
    df["week"] = pd.to_datetime(df["week"])
    df["product_supplied"] = pd.to_numeric(df["product_supplied"], errors="coerce")
    df = df.dropna(subset=["week", "product_name", "product_supplied"])
    return df


try:
    weekly_total = load_supply_data()
except Exception as e:
    st.error(f"Failed to load supply data from BigQuery: {e}")
    st.stop()

if weekly_total.empty:
    st.error("No supply data found in BigQuery.")
    st.stop()

# =========================
# Interactive Filters
# =========================
st.sidebar.header("Filters")

min_week = weekly_total["week"].min().date()
max_week = weekly_total["week"].max().date()

start_week = st.sidebar.date_input(
    "Start week",
    value=min_week,
    min_value=min_week,
    max_value=max_week,
    key="supply_start_week",
)

end_week = st.sidebar.date_input(
    "End week",
    value=max_week,
    min_value=min_week,
    max_value=max_week,
    key="supply_end_week",
)

if start_week > end_week:
    st.error("Start week must be earlier than or equal to end week.")
    st.stop()

filtered_total = weekly_total[
    (weekly_total["week"] >= pd.to_datetime(start_week))
    & (weekly_total["week"] <= pd.to_datetime(end_week))
].copy()

if filtered_total.empty:
    st.warning("No data available for the selected date range.")
    st.stop()

weekly_by_product = load_supply_product_data()

filtered_product = weekly_by_product[
    (weekly_by_product["week"] >= pd.to_datetime(start_week))
    & (weekly_by_product["week"] <= pd.to_datetime(end_week))
].copy()

product_options = sorted(filtered_product["product_name"].dropna().unique().tolist())

selected_products = st.sidebar.multiselect(
    "Select product(s)",
    options=product_options,
    default=product_options[:3] if len(product_options) >= 3 else product_options,  # noqa: PLR2004
    key="product_filter",
)

try:
    latest_total = latest_value(
        filtered_total,
        date_col="week",
        value_col="total_product_supplied",
    )
except Exception:
    latest_total = None

c1, c2 = st.columns(2)
c1.metric("Weeks in selected range", f"{filtered_total.shape[0]:,}")
c2.metric(
    "Latest total (sum of products)",
    f"{latest_total:,.0f}" if latest_total is not None else "—",
)

st.divider()
st.subheader("Total Product Supplied (Weekly, All Products Summed)")

fig, ax = plt.subplots()
ax.plot(filtered_total["week"], filtered_total["total_product_supplied"])
ax.set_xlabel("Week")
ax.set_ylabel("Total Product Supplied")
st.pyplot(fig)

with st.expander("Show total supply data table"):
    st.dataframe(
        filtered_total.sort_values("week", ascending=False),
        use_container_width=True,
    )

st.caption(
    "Note: 'Product supplied' is often used as a proxy for consumption. "
    "This visualization is descriptive (not causal)."
)

st.divider()
st.subheader("Product-Level Weekly Supply")

if not selected_products:
    st.warning("Please select at least one product from the sidebar.")
else:
    product_plot_df = filtered_product[
        filtered_product["product_name"].isin(selected_products)
    ].copy()

    fig2, ax2 = plt.subplots()
    for product in selected_products:
        temp = product_plot_df[product_plot_df["product_name"] == product]
        ax2.plot(temp["week"], temp["product_supplied"], label=product)

    ax2.set_xlabel("Week")
    ax2.set_ylabel("Product Supplied")
    ax2.legend()
    st.pyplot(fig2)

    with st.expander("Show product-level data table"):
        st.dataframe(
            product_plot_df.sort_values(["product_name", "week"], ascending=[True, False]),
            use_container_width=True,
        )
