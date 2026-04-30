import time

import numpy as np
import pandas as pd
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account
from scipy import stats

start_time = time.time()

st.set_page_config(page_title="Geopolitical Conflict & Oil Prices", layout="wide")

# =========================
# Sidebar styling
# =========================
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] { background-color: #0D2B5E !important; }
    [data-testid="stSidebar"] * { color: white !important; }
    [data-testid="stSidebar"] .stDateInput input {
        color: #1A1A1A !important;
        background-color: #E4EBF4 !important;
    }
    [data-testid="stSidebarNav"] a { color: rgba(255,255,255,0.8) !important; }
    [data-testid="stSidebarNav"] a:hover {
        color: white !important;
        background-color: rgba(255,255,255,0.1) !important;
    }
    [data-testid="stSidebarNav"] { padding-top: 3.5rem; }
    [data-testid="stSidebarNav"]::before {
        content: "U.S. Petroleum & WTI Weekly Monitor";
        display: block; position: absolute;
        top: 0; left: 0; right: 0;
        padding: 1rem 1.2rem 0.2rem 1.2rem;
        font-size: 1.05rem; font-weight: 600; line-height: 1.3;
        color: white !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================
# Config
# =========================
PROJECT_ID     = "sipa-adv-c-giggling-wombat"
GDELT_TABLE    = f"{PROJECT_ID}.giggling_wombat.gdelt_weekly"
WTI_TABLE      = f"{PROJECT_ID}.petroleum_supply.weekly_wti"
GASOLINE_TABLE = f"{PROJECT_ID}.giggling_wombat.weekly_gasoline"


@st.cache_resource
def get_bq_client():
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"]
    )
    return bigquery.Client(credentials=credentials, project=credentials.project_id)


@st.cache_data(ttl=60 * 60)
def load_all_data():
    client = get_bq_client()

    wti = client.query(f"""
        SELECT DATE(week) as week, wti_price
        FROM `{WTI_TABLE}` WHERE week IS NOT NULL ORDER BY week
    """).to_dataframe(create_bqstorage_client=False)

    gas = client.query(f"""
        SELECT DATE(week) as week, gasoline_price
        FROM `{GASOLINE_TABLE}` WHERE week IS NOT NULL ORDER BY week
    """).to_dataframe(create_bqstorage_client=False)

    gdelt = client.query(f"""
        SELECT DATE(week) as week, AVG(avg_goldstein) as avg_goldstein
        FROM `{GDELT_TABLE}` WHERE week IS NOT NULL
        GROUP BY DATE(week) ORDER BY week
    """).to_dataframe(create_bqstorage_client=False)

    for df in [wti, gas, gdelt]:
        df["week"] = pd.to_datetime(df["week"]).dt.to_period("W").dt.start_time

    wti["wti_price"]       = pd.to_numeric(wti["wti_price"],       errors="coerce")
    gas["gasoline_price"]  = pd.to_numeric(gas["gasoline_price"],  errors="coerce")
    gdelt["avg_goldstein"] = pd.to_numeric(gdelt["avg_goldstein"], errors="coerce")

    wti = (
        wti.groupby("week")
        .agg(wti_price=("wti_price", "mean"))
        .reset_index().dropna().sort_values("week")
    )
    gas = (
        gas.groupby("week")
        .agg(gasoline_price=("gasoline_price", "mean"))
        .reset_index().dropna().sort_values("week")
    )
    gdelt = (
        gdelt.groupby("week")
        .agg(avg_goldstein=("avg_goldstein", "mean"))
        .reset_index().dropna().sort_values("week")
    )

    return wti, gas, gdelt


# =========================
# Load data
# =========================
try:
    wti, gas, gdelt = load_all_data()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

# =========================
# Sidebar filters
# =========================
st.sidebar.markdown(
    """
    <h1 style="font-size: 1.5rem; line-height: 1.2; margin-bottom: 0.2rem;">
        U.S. Petroleum & WTI Weekly Monitor
    </h1>
    """,
    unsafe_allow_html=True,
)
st.sidebar.caption("Source: GDELT + EIA")
st.sidebar.divider()
st.sidebar.header("Filters")
st.sidebar.caption("Affects correlation statistics and key findings below.")

# Use merged min/max for date range
merged_all = gdelt.merge(wti, on="week", how="inner").merge(gas, on="week", how="inner").dropna()
min_week   = merged_all["week"].min().date()
max_week   = merged_all["week"].max().date()

start_week = st.sidebar.date_input(
    "Start week", value=min_week, min_value=min_week, max_value=max_week
)
end_week = st.sidebar.date_input(
    "End week", value=max_week, min_value=min_week, max_value=max_week
)

if start_week > end_week:
    st.sidebar.error("Start week must be before end week.")
    st.stop()

# =========================
# Filter merged data
# =========================
merged = merged_all[
    (merged_all["week"] >= pd.to_datetime(start_week)) &
    (merged_all["week"] <= pd.to_datetime(end_week))
].copy()

if merged.empty:
    st.warning("No overlapping data for selected date range.")
    st.stop()

# Current prices (always latest, unaffected by filter)
latest_wti      = wti.iloc[-1]["wti_price"]
latest_wti_date = wti.iloc[-1]["week"].strftime("%b %d, %Y")
wti_change      = latest_wti - (wti.iloc[-2]["wti_price"] if len(wti) > 1 else latest_wti)

latest_gas      = gas.iloc[-1]["gasoline_price"]
latest_gas_date = gas.iloc[-1]["week"].strftime("%b %d, %Y")
gas_change      = latest_gas - (gas.iloc[-2]["gasoline_price"] if len(gas) > 1 else latest_gas)

latest_gold      = gdelt.iloc[-1]["avg_goldstein"]
latest_gold_date = gdelt.iloc[-1]["week"].strftime("%b %d, %Y")
gold_change = latest_gold - (
    gdelt.iloc[-2]["avg_goldstein"] if len(gdelt) > 1 else latest_gold
)

# Stats computed on filtered period
r_conflict_wti, _ = stats.pearsonr(merged["avg_goldstein"], merged["wti_price"])
r_wti_gas, _      = stats.pearsonr(merged["wti_price"],     merged["gasoline_price"])
slope_wti_gas, _, _, _, _ = stats.linregress(merged["wti_price"], merged["gasoline_price"])
cents = slope_wti_gas * 100

avg_goldstein_period = merged["avg_goldstein"].mean()

lags     = list(range(1, 13))
corr_lag = []
for lag in lags:
    shifted = merged["avg_goldstein"].shift(lag)
    valid   = merged[["gasoline_price"]].join(shifted.rename("s")).dropna()
    r, _    = stats.pearsonr(valid["s"], valid["gasoline_price"]) if len(valid) > 1 else (0, 0)
    corr_lag.append(abs(r))
best_lag = lags[np.argmax(corr_lag)]

start_str = pd.to_datetime(start_week).strftime("%b %d, %Y")
end_str   = pd.to_datetime(end_week).strftime("%b %d, %Y")

# =========================
# Hero section
# =========================
st.markdown(
    """
    <h1 style='font-size:2.4rem; margin-bottom:0.2rem;'>
        Geopolitical Conflict & U.S. Energy Prices
    </h1>
    <p style='font-size:1.1rem; color:#555; margin-bottom:1rem;'>
        How does conflict in oil-producing countries ripple through
        to what Americans pay at the pump?
    </p>
    """,
    unsafe_allow_html=True,
)
st.caption(
    "Team Members: Irina, Indra · "
    "Source: GDELT, U.S. Energy Information Administration (EIA)"
)
st.markdown("<br>", unsafe_allow_html=True)

# =========================
# About this project
# =========================
st.markdown(
    """
    <div style='background-color:#F8F9FA; padding:1.2rem 1.4rem; border-radius:8px;
                margin-bottom:1rem; font-size:0.95rem; color:#333;'>
        <b style='font-size:1rem;'>About This Dashboard</b><br><br>
        When conflict breaks out in oil-producing regions, energy markets react — but by how much,
        and how quickly? This dashboard traces the full transmission chain from <b>geopolitical
        conflict events</b> in major oil-producing countries, through <b>WTI crude oil prices</b>,
        to the <b>retail gasoline prices</b> Americans pay at the pump every week.<br><br>
        Using weekly data from <b>2012 to present</b>, we apply statistical correlation and
        time-lag analysis to quantify these relationships with precision.<br><br>
        <b>Who can benefit from this dashboard:</b>
        <ul style='margin:0.5rem 0 0 1rem; padding:0;'>
            <li><b>Policymakers</b> monitoring energy price shocks
            and anticipating consumer impact</li>
            <li><b>Economists &amp; analysts</b> studying geopolitical risk
            transmission into commodity markets</li>
            <li><b>Energy security researchers</b> tracking conflict-driven supply disruptions</li>
            <li><b>Journalists &amp; the public</b> seeking data-driven
            context for gas price movements</li>
        </ul>
    </div>
    """,
    unsafe_allow_html=True,
)

# Research questions
st.markdown(
    """
    <div style='background-color:#EEF4FB; border-left:4px solid #1B4F8A;
                padding:1rem 1.2rem; border-radius:4px; margin-bottom:1rem;'>
        <b>Research Questions</b>
        <ol style='margin:0.5rem 0 0 1rem; padding:0;'>
            <li>How much does geopolitical conflict intensity in
            oil-producing countries affect WTI crude oil prices?</li>
            <li>How much does WTI price affect U.S. retail gasoline prices?</li>
            <li>How long does it take for a conflict spike to transmit to gasoline prices?</li>
        </ol>
    </div>
    """,
    unsafe_allow_html=True,
)

st.divider()

# =========================
# Key highlights
# =========================
st.subheader("Key Data Highlights")

col_info, _ = st.columns([3, 1])
with col_info:
    st.caption(
        f"Current prices as of {latest_wti_date}. "
        f"Correlation statistics for the selected period: **{start_str}** to **{end_str}** "
        f"({len(merged):,} weeks)."
    )

c1, c2, c3 = st.columns(3)
c1.metric(
    "WTI Crude Oil Price", f"${latest_wti:.2f}/bbl",
    delta=f"${wti_change:+.2f} from prev. week",
    help=f"Latest price as of {latest_wti_date}",
)
c2.metric(
    "U.S. Gasoline Price", f"${latest_gas:.3f}/gal",
    delta=f"${gas_change:+.3f} from prev. week",
    help=f"Latest price as of {latest_gas_date}",
)
c3.metric(
    "Conflict Intensity (Goldstein)", f"{latest_gold:.2f}",
    delta=f"{gold_change:+.2f} from prev. week",
    delta_color="inverse",
    help=f"Latest avg Goldstein score as of {latest_gold_date}. Lower = more conflict.",
)

st.markdown("<br>", unsafe_allow_html=True)

c4, c5, c6 = st.columns(3)
c4.metric(
    "Conflict → WTI Correlation", f"r = {r_conflict_wti:.3f}",
    help=f"Pearson r for selected period ({start_str} to {end_str})",
)
c5.metric(
    "WTI → Gasoline Correlation", f"r = {r_wti_gas:.3f}",
    help=f"Pearson r for selected period ({start_str} to {end_str})",
)
c6.metric(
    "Conflict → Pump Price Lag", f"{best_lag} weeks",
    help=f"Strongest lag for selected period ({start_str} to {end_str})",
)

st.markdown("<br>", unsafe_allow_html=True)

st.markdown(
    f"""
    <div style='background-color:#FFF3E0; border-left:4px solid #DC641E;
                padding:1rem 1.2rem; border-radius:4px;'>
        <b>Key Finding</b> <span style='color:#888; font-size:0.85rem;'>
        (based on {start_str} – {end_str})</span><br>
        Every <b>$1 increase in WTI crude oil price</b> is associated with approximately
        <b>{cents:.1f} cents more per gallon</b> at the pump.
        Conflict in oil-producing countries typically takes <b>{best_lag} weeks</b>
        to transmit to U.S. gasoline prices.
        The average conflict intensity (Goldstein) for this period
        was <b>{avg_goldstein_period:.2f}</b>.
    </div>
    """,
    unsafe_allow_html=True,
)

st.divider()

# =========================
# Data sources
# =========================
st.subheader("Data Sources")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(
        """
        <div style='background:#F0F4FB; padding:1rem; border-radius:8px; height:150px;'>
            <b>GDELT</b><br>
            <span style='color:#555; font-size:0.9rem;'>
            Real-time conflict event data from worldwide news media.
            Covers 10 major oil-producing countries from 2012 to present.
            </span>
        </div>
        """, unsafe_allow_html=True,
    )
with col2:
    st.markdown(
        """
        <div style='background:#F0F4FB; padding:1rem; border-radius:8px; height:150px;'>
            <b>EIA — WTI Crude Oil Price</b><br>
            <span style='color:#555; font-size:0.9rem;'>
            Weekly West Texas Intermediate spot price.
            The primary benchmark for U.S. crude oil pricing,
            updated weekly since 1986.
            </span>
        </div>
        """, unsafe_allow_html=True,
    )
with col3:
    st.markdown(
        """
        <div style='background:#F0F4FB; padding:1rem; border-radius:8px; height:150px;'>
            <b>EIA — U.S. Gasoline Retail Price</b><br>
            <span style='color:#555; font-size:0.9rem;'>
            Weekly U.S. Regular All Formulations Retail Gasoline Price.
            What consumers actually pay at the pump, in dollars per gallon.
            </span>
        </div>
        """, unsafe_allow_html=True,
    )

st.divider()

# =========================
# Navigation guide
# =========================
st.subheader("Navigation Guide")

pages = [
    (
        "Geopolitical Conflict Context",
        "Explore conflict intensity across oil-producing countries using GDELT — "
        "choropleth maps, event type breakdowns, and media attention heatmaps.",
    ),
    (
        "WTI Price",
        "Deep dive into WTI crude oil price trends, weekly changes, "
        "volatility, and real-time interpretation.",
    ),
    (
        "Gasoline Price",
        "Explore U.S. retail gasoline prices, their relationship with WTI, "
        "and what consumers are paying week by week.",
    ),
    (
        "Price Transmission Analysis",
        "Quantify the full transmission chain: Conflict → WTI → Gasoline, "
        "including time lag analysis (1-12 weeks) and statistical significance.",
    ),
]

for name, desc in pages:
    st.markdown(
        f"""
        <div style='background:#F8F9FA; border:1px solid #E0E0E0; padding:0.8rem 1rem;
                    border-radius:6px; margin-bottom:0.5rem;'>
            <b>{name}</b><br>
            <span style='color:#555; font-size:0.9rem;'>{desc}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.divider()

with st.expander("Project Proposal", expanded=False):
    st.markdown(
        """
        **Overview**

        This project analyzes the relationship between geopolitical conflict in major
        oil-producing countries and U.S. energy prices using three data sources:
        GDELT (conflict events), EIA WTI crude oil price, and EIA retail gasoline price.

        **Datasets**
        - GDELT via BigQuery public dataset (`gdelt-bq.gdeltv2.events`)
        - EIA Petroleum API — WTI Spot Price (RWTC)
        - EIA Petroleum API — U.S. Regular Gasoline Retail Price (EMM_EPM0_PTE_NUS_DPG)

        **Methodology**
        - Weekly aggregation of all datasets
        - Pearson correlation analysis
        - OLS linear regression
        - Cross-correlation time lag analysis (1–12 weeks)

        **GitHub**
        [advanced-computing/giggling-wombat](https://github.com/advanced-computing/giggling-wombat)
        """
    )

elapsed = time.time() - start_time
st.caption(f"Page loaded in {elapsed:.2f} seconds")
