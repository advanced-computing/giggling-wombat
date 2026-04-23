import time

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

from tests.eia_part3 import latest_value

start_time = time.time()

st.set_page_config(page_title="Weekly U.S. Petroleum Supply", layout="wide")

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
st.title("Weekly U.S. Petroleum Supply")
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
TOTAL_SUPPLY_TABLE_ID = f"{PROJECT_ID}.petroleum_supply.weekly_supply"
PRODUCT_SUPPLY_TABLE_ID = f"{PROJECT_ID}.petroleum_supply.weekly_supply_by_product"
WTI_TABLE_ID = f"{PROJECT_ID}.petroleum_supply.weekly_wti"

DEFAULT_PRODUCT_COUNT = 3
MIN_CORRELATION_POINTS = 12
TOP_ANALYSIS_COUNT = 10
TWO_COLUMN_LAYOUT = 2
THREE_COLUMN_LAYOUT = 3


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
        SELECT week, total_supply
        FROM `{TOTAL_SUPPLY_TABLE_ID}`
        ORDER BY week
    """
    df = client.query(query).to_dataframe(create_bqstorage_client=False)
    df["week"] = pd.to_datetime(df["week"])
    df["total_supply"] = pd.to_numeric(df["total_supply"], errors="coerce")
    df = df.dropna(subset=["week", "total_supply"])
    return df


@st.cache_data(ttl=60 * 60)
def load_supply_product_data() -> pd.DataFrame:
    client = get_bq_client()
    query = f"""
        SELECT week, product, product_name, product_supplied
        FROM `{PRODUCT_SUPPLY_TABLE_ID}`
        ORDER BY week
    """
    df = client.query(query).to_dataframe(create_bqstorage_client=False)
    df["week"] = pd.to_datetime(df["week"])
    df["product_supplied"] = pd.to_numeric(df["product_supplied"], errors="coerce")
    df = df.dropna(subset=["week", "product", "product_name", "product_supplied"])
    return df


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


def compute_product_price_sensitivity(
    product_df: pd.DataFrame,
    wti_df: pd.DataFrame,
) -> pd.DataFrame:
    merged = product_df.merge(wti_df, on="week", how="inner")

    if merged.empty:
        return pd.DataFrame()

    results = []

    grouped = merged.groupby(["product", "product_name"], dropna=False)

    for (product_code, product_name), group in grouped:
        group = group.dropna(subset=["product_supplied", "wti_price"]).copy()

        if len(group) < MIN_CORRELATION_POINTS:
            continue

        if group["product_supplied"].nunique() < TWO_COLUMN_LAYOUT:
            continue

        if group["wti_price"].nunique() < TWO_COLUMN_LAYOUT:
            continue

        correlation = group["product_supplied"].corr(group["wti_price"])

        if pd.isna(correlation):
            continue

        direction = "Positive" if correlation >= 0 else "Negative"

        results.append(
            {
                "product": product_code,
                "product_name": product_name,
                "correlation_with_wti": correlation,
                "abs_correlation": abs(correlation),
                "direction": direction,
                "weeks_used": len(group),
            }
        )

    if not results:
        return pd.DataFrame()

    result_df = (
        pd.DataFrame(results).sort_values("abs_correlation", ascending=False).reset_index(drop=True)
    )

    return result_df


# =========================
# Load data
# =========================
try:
    weekly_total = load_supply_data()
except Exception as e:
    st.error(f"Failed to load supply data from BigQuery: {e}")
    st.stop()

if weekly_total.empty:
    st.error("No supply data found in BigQuery.")
    st.stop()

try:
    weekly_by_product = load_supply_product_data()
except Exception as e:
    st.error(f"Failed to load product-level supply data from BigQuery: {e}")
    st.stop()

try:
    weekly_wti = load_wti_data()
except Exception as e:
    st.error(f"Failed to load WTI data from BigQuery: {e}")
    st.stop()

if weekly_by_product.empty:
    st.error("No product-level supply data found in BigQuery.")
    st.stop()

if weekly_wti.empty:
    st.error("No WTI data found in BigQuery.")
    st.stop()

# =========================
# Sidebar Filters
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

filtered_product = weekly_by_product[
    (weekly_by_product["week"] >= pd.to_datetime(start_week))
    & (weekly_by_product["week"] <= pd.to_datetime(end_week))
].copy()

filtered_wti = weekly_wti[
    (weekly_wti["week"] >= pd.to_datetime(start_week))
    & (weekly_wti["week"] <= pd.to_datetime(end_week))
].copy()

product_options = sorted(filtered_product["product_name"].dropna().unique().tolist())

selected_products = st.sidebar.multiselect(
    "Select product(s)",
    options=product_options,
    default=(
        product_options[:DEFAULT_PRODUCT_COUNT]
        if len(product_options) >= DEFAULT_PRODUCT_COUNT
        else product_options
    ),
    key="product_filter",
)

try:
    latest_total = latest_value(
        filtered_total,
        date_col="week",
        value_col="total_supply",
    )
except Exception:
    latest_total = None

c1, c2 = st.columns(TWO_COLUMN_LAYOUT)
c1.metric("Weeks in selected range", f"{filtered_total.shape[0]:,}")
c2.metric(
    "Latest total (sum of products)",
    f"{latest_total:,.0f}" if latest_total is not None else "—",
)

st.caption(
    "Note: 'Product supplied' is often used as a proxy for consumption. "
    "This dashboard is descriptive rather than causal."
)

st.divider()

# =========================
# Two side-by-side charts
# =========================
left_col, right_col = st.columns(TWO_COLUMN_LAYOUT)

with left_col:
    st.subheader("Total Product Supplied")

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(filtered_total["week"], filtered_total["total_supply"])
    ax.set_xlabel("Week")
    ax.set_ylabel("Total Product Supplied")
    st.pyplot(fig)

    with st.expander("Show total supply data table"):
        total_display = filtered_total.sort_values("week", ascending=False).copy()
        total_display["week"] = total_display["week"].dt.strftime("%Y-%m-%d")
        st.dataframe(total_display, width="stretch")

with right_col:
    st.subheader("Product-Level Weekly Supply")

    if not selected_products:
        st.warning("Please select at least one product from the sidebar.")
    else:
        product_plot_df = filtered_product[
            filtered_product["product_name"].isin(selected_products)
        ].copy()

        fig2, ax2 = plt.subplots(figsize=(7, 4))
        for product_name in selected_products:
            temp = product_plot_df[product_plot_df["product_name"] == product_name]
            ax2.plot(temp["week"], temp["product_supplied"], label=product_name)

        ax2.set_xlabel("Week")
        ax2.set_ylabel("Product Supplied")
        ax2.legend()
        st.pyplot(fig2)

        with st.expander("Show product-level data table"):
            product_display = product_plot_df.sort_values(
                ["product_name", "week"], ascending=[True, False]
            ).copy()
            product_display["week"] = product_display["week"].dt.strftime("%Y-%m-%d")
            st.dataframe(product_display, width="stretch")

st.divider()

# =========================
# Product sensitivity section
# =========================
st.subheader("Product Sensitivity to WTI Price")

sensitivity_df = compute_product_price_sensitivity(filtered_product, filtered_wti)

if sensitivity_df.empty:
    st.warning("Not enough overlapping weekly data to evaluate product sensitivity to WTI price.")
else:
    top_product = sensitivity_df.iloc[0]

    m1, m2, m3 = st.columns(THREE_COLUMN_LAYOUT)
    m1.metric("Most price-sensitive product", top_product["product_name"])
    m2.metric(
        "Correlation with WTI",
        f"{top_product['correlation_with_wti']:.2f}",
    )
    m3.metric("Weeks used", f"{int(top_product['weeks_used'])}")

    st.caption(
        "Products are ranked by the absolute correlation between weekly product "
        "supplied and weekly WTI price over the selected date range. This is a "
        "descriptive measure, not a causal estimate."
    )

    chart_df = sensitivity_df.head(TOP_ANALYSIS_COUNT).sort_values(
        "abs_correlation", ascending=True
    )

    fig3, ax3 = plt.subplots(figsize=(6, 3.5))
    ax3.barh(
        chart_df["product_name"],
        chart_df["abs_correlation"],
        color="darkorange",
    )
    ax3.set_xlabel("Absolute correlation with WTI price")
    ax3.set_ylabel("Product")
    st.pyplot(fig3)

    with st.expander("Show product sensitivity table"):
        st.dataframe(
            sensitivity_df[
                [
                    "product",
                    "product_name",
                    "correlation_with_wti",
                    "abs_correlation",
                    "direction",
                    "weeks_used",
                ]
            ],
            width="stretch",
        )

elapsed = time.time() - start_time
st.caption(f"Page loaded in {elapsed:.2f} seconds")
