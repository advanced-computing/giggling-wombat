import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

start_time = time.time()

st.set_page_config(page_title="Gasoline Price", layout="wide")

# =========================
# Sidebar styling
# =========================
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {
        background-color: #0D2B5E !important;
    }

    [data-testid="stSidebar"] > div {
        background-color: #0D2B5E !important;
    }

    [data-testid="stSidebar"] * {
        color: white !important;
    }

    [data-testid="stSidebarNav"] {
        padding-top: 3.8rem;
        background-color: #0D2B5E !important;
    }

    [data-testid="stSidebarNav"]::before {
        content: "U.S. Petroleum & WTI Weekly Monitor";
        display: block;
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        padding: 1rem 1.2rem 0.3rem 1.2rem;
        font-size: 1.05rem;
        font-weight: 700;
        line-height: 1.3;
        color: white !important;
        background-color: #0D2B5E !important;
    }

    [data-testid="stSidebarNav"] a {
        color: rgba(255,255,255,0.85) !important;
        background-color: transparent !important;
    }

    [data-testid="stSidebarNav"] a:hover {
        color: white !important;
        background-color: rgba(255,255,255,0.12) !important;
        border-radius: 0.4rem;
    }

    [data-testid="stSidebarNav"] a[aria-current="page"] {
        color: white !important;
        background-color: rgba(255,255,255,0.16) !important;
        border-radius: 0.4rem;
        font-weight: 700;
    }

    [data-testid="stSidebar"] .stDateInput input {
        color: #1A1A1A !important;
        background-color: #E4EBF4 !important;
    }

    [data-testid="stSidebar"] input {
        color: #1A1A1A !important;
        background-color: #E4EBF4 !important;
    }

    [data-testid="stSidebar"] textarea {
        color: #1A1A1A !important;
        background-color: #E4EBF4 !important;
    }

    [data-testid="stSidebar"] div[data-baseweb="select"] * {
        color: #1A1A1A !important;
    }

    [data-testid="stSidebar"] div[data-baseweb="select"] > div {
        background-color: #E4EBF4 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================
# Helper
# =========================
def interpret(text: str):
    st.markdown(
        f"<p style='font-size:0.95rem; color:#444; margin-top:-0.5rem;'>{text}</p>",
        unsafe_allow_html=True,
    )


# =========================
# Page header
# =========================
st.title("U.S. Retail Gasoline Price")
st.caption(
    "Weekly U.S. Regular All Formulations Retail Gasoline Prices in Dollars per Gallon. "
    "This is the price consumers pay at the pump — directly impacted by "
    "WTI crude oil price movements."
)

# =========================
# Config
# =========================
PROJECT_ID = "sipa-adv-c-giggling-wombat"
CORR_VERY_STRONG = 0.85
CORR_STRONG = 0.7
GASOLINE_TABLE = f"{PROJECT_ID}.giggling_wombat.weekly_gasoline"
WTI_TABLE = f"{PROJECT_ID}.petroleum_supply.weekly_wti"


@st.cache_resource
def get_bq_client():
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"]
    )
    return bigquery.Client(credentials=credentials, project=credentials.project_id)


@st.cache_data(ttl=60 * 60)
def load_gasoline() -> pd.DataFrame:
    client = get_bq_client()
    query = f"SELECT week, gasoline_price FROM `{GASOLINE_TABLE}` ORDER BY week"
    df = client.query(query).to_dataframe(create_bqstorage_client=False)
    df["week"] = pd.to_datetime(df["week"])
    df["gasoline_price"] = pd.to_numeric(df["gasoline_price"], errors="coerce")
    return df.dropna().sort_values("week").reset_index(drop=True)


@st.cache_data(ttl=60 * 60)
def load_wti() -> pd.DataFrame:
    client = get_bq_client()
    query = f"SELECT week, wti_price FROM `{WTI_TABLE}` ORDER BY week"
    df = client.query(query).to_dataframe(create_bqstorage_client=False)
    df["week"] = pd.to_datetime(df["week"]).dt.to_period("W").dt.start_time
    df["wti_price"] = pd.to_numeric(df["wti_price"], errors="coerce")
    return df.dropna().sort_values("week").reset_index(drop=True)


# =========================
# Load data
# =========================
try:
    gasoline = load_gasoline()
except Exception as e:
    st.error(f"Failed to load gasoline data: {e}")
    st.stop()

try:
    wti = load_wti()
except Exception as e:
    st.error(f"Failed to load WTI data: {e}")
    st.stop()

# =========================
# Sidebar filters
# =========================
st.sidebar.header("Filters")
min_week = gasoline["week"].min().date()
max_week = gasoline["week"].max().date()

start_week = st.sidebar.date_input(
    "Start week", value=min_week, min_value=min_week, max_value=max_week
)
end_week = st.sidebar.date_input("End week", value=max_week, min_value=min_week, max_value=max_week)

# =========================
# Filter & derived columns
# =========================
filtered = gasoline[
    (gasoline["week"] >= pd.to_datetime(start_week))
    & (gasoline["week"] <= pd.to_datetime(end_week))
].copy()

if filtered.empty:
    st.warning("No data available for selected date range.")
    st.stop()

merged = filtered.merge(wti, on="week", how="inner")

filtered["gas_smooth"] = filtered["gasoline_price"].rolling(4, center=True).mean()
filtered["weekly_change"] = filtered["gasoline_price"].diff()
filtered["pct_change"] = filtered["gasoline_price"].pct_change() * 100
filtered["year"] = filtered["week"].dt.year
filtered["rolling_std"] = filtered["gasoline_price"].rolling(12).std()
filtered["ma4"] = filtered["gasoline_price"].rolling(4).mean()
filtered["range12_high"] = filtered["gasoline_price"].rolling(12).max()
filtered["range12_low"] = filtered["gasoline_price"].rolling(12).min()

latest = filtered.iloc[-1]
prev = filtered.iloc[-2] if len(filtered) > 1 else None
latest_date = latest["week"].strftime("%B %d, %Y")
prev_date = prev["week"].strftime("%B %d, %Y") if prev is not None else ""
current_price = latest["gasoline_price"]
ma4_val = latest["ma4"]
range_high = latest["range12_high"]
range_low = latest["range12_low"]
volatility = latest["rolling_std"]
avg_vol = filtered["rolling_std"].mean()

# =========================
# Summary metrics
# =========================
c1, c2, c3, c4 = st.columns(4)
c1.metric("Current Gasoline Price", f"${current_price:.3f}/gal", help=f"As of {latest_date}")
c2.metric("Average Price", f"${filtered['gasoline_price'].mean():.3f}/gal")
c3.metric("All-time High", f"${filtered['gasoline_price'].max():.3f}/gal")
c4.metric("All-time Low", f"${filtered['gasoline_price'].min():.3f}/gal")

st.divider()

# =========================
# Chart 1: Gasoline price timeline
# =========================
st.subheader("① Gasoline Price Over Time")

fig1 = go.Figure()
fig1.add_trace(
    go.Scatter(
        x=filtered["week"],
        y=filtered["gasoline_price"],
        name="Weekly price",
        mode="lines",
        line=dict(color="rgba(220,100,30,0.3)", width=1),
    )
)
fig1.add_trace(
    go.Scatter(
        x=filtered["week"],
        y=filtered["gas_smooth"],
        name="4-week avg",
        mode="lines",
        line=dict(color="#DC641E", width=2.5),
    )
)
fig1.update_layout(
    yaxis_title="USD per gallon",
    xaxis_title="Week",
    hovermode="x unified",
    height=400,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig1, use_container_width=True)

if prev is not None:
    chg = current_price - prev["gasoline_price"]
    pct = (chg / prev["gasoline_price"]) * 100
    dir1 = "increased" if chg > 0 else "decreased"
    arr = "" if chg > 0 else ""
    interpret(
        f"{arr} Gasoline price <b>{dir1}</b> by <b>${abs(chg):.3f} ({abs(pct):.2f}%)</b> "
        f"from <b>{prev_date}</b> to <b>{latest_date}</b>, "
        f"suggesting short-term {'upward' if chg > 0 else 'downward'} pressure at the pump."
    )

if pd.notna(ma4_val):
    vs_ma = "above" if current_price > ma4_val else "below"
    impl = (
        "suggesting stronger short-term pricing."
        if current_price > ma4_val
        else "which may suggest weaker short-term pricing."
    )
    interpret(
        f"The latest price on <b>{latest_date}</b> (<b>${current_price:.3f}/gal</b>) is "
        f"<b>{vs_ma}</b> the 4-week moving average (<b>${ma4_val:.3f}/gal</b>), {impl}"
    )

st.divider()

# =========================
# Chart 2: Gasoline vs WTI overlay
# =========================
st.subheader("② Gasoline Price vs. WTI Price")

fig2 = go.Figure()
fig2.add_trace(
    go.Scatter(
        x=merged["week"],
        y=merged["gasoline_price"],
        name="Gasoline ($/gal)",
        mode="lines",
        line=dict(color="#DC641E", width=2),
        yaxis="y1",
    )
)
fig2.add_trace(
    go.Scatter(
        x=merged["week"],
        y=merged["wti_price"],
        name="WTI ($/bbl)",
        mode="lines",
        line=dict(color="#1B4F8A", width=2),
        yaxis="y2",
    )
)
fig2.update_layout(
    yaxis=dict(title="Gasoline Price ($/gal)", side="left"),
    yaxis2=dict(title="WTI Price ($/bbl)", overlaying="y", side="right"),
    hovermode="x unified",
    height=420,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig2, use_container_width=True)

# Interpretation — overlay
merged_clean = merged.dropna(subset=["gasoline_price", "wti_price"])
if not merged_clean.empty:
    corr_val = merged_clean["gasoline_price"].corr(merged_clean["wti_price"])
    latest_wti = merged_clean.iloc[-1]["wti_price"]
    latest_gas = merged_clean.iloc[-1]["gasoline_price"]
    latest_date_merged = merged_clean.iloc[-1]["week"].strftime("%B %d, %Y")
    if abs(corr_val) > CORR_VERY_STRONG:
        corr_strength = "very strong"
    elif abs(corr_val) > CORR_STRONG:
        corr_strength = "strong"
    else:
        corr_strength = "moderate"
    interpret(
        f"Gasoline and WTI prices have a <b>Pearson correlation of {corr_val:.3f}</b> "
        f"over the selected period, indicating a {corr_strength} "
        f"positive relationship. "
        f"As of <b>{latest_date_merged}</b>, WTI was at <b>${latest_wti:.2f}/bbl</b> "
        f"while gasoline was at <b>${latest_gas:.3f}/gal</b>."
    )

st.divider()

# =========================
# Chart 3: Weekly price change
# =========================
st.subheader("③ Weekly Price Change")

fig3 = go.Figure()
fig3.add_trace(
    go.Bar(
        x=filtered["week"],
        y=filtered["weekly_change"],
        marker_color=filtered["weekly_change"].apply(lambda x: "#DC641E" if x >= 0 else "crimson"),
        name="Weekly change",
    )
)
fig3.update_layout(
    yaxis_title="USD change per gallon", xaxis_title="Week", hovermode="x unified", height=360
)
st.plotly_chart(fig3, use_container_width=True)

if prev is not None:
    chg = current_price - prev["gasoline_price"]
    dir2 = "gain" if chg > 0 else "loss"
    max_chg = filtered["weekly_change"].abs().max()
    max_chg_week = filtered.loc[filtered["weekly_change"].abs() == max_chg, "week"].iloc[0]
    max_chg_date = max_chg_week.strftime("%B %d, %Y")
    cents = abs(chg) * 100
    interpret(
        f"The most recent week ending <b>{latest_date}</b> saw a price {dir2} of "
        f"<b>{cents:.1f} cents/gal</b>. "
        f"The largest single-week swing in this period was "
        f"<b>${max_chg:.3f}/gal</b> on <b>{max_chg_date}</b>."
    )

st.divider()

# =========================
# Chart 4: Annual average
# =========================
st.subheader("④ Annual Average Gasoline Price")

annual = filtered.groupby("year")["gasoline_price"].mean().reset_index()
annual.columns = ["year", "avg_price"]

fig4 = px.bar(
    annual,
    x="year",
    y="avg_price",
    color="avg_price",
    color_continuous_scale="Oranges",
    labels={"year": "Year", "avg_price": "Avg Gasoline Price ($/gal)"},
    text=annual["avg_price"].apply(lambda x: f"${x:.2f}"),
)
fig4.update_traces(textposition="outside")
fig4.update_layout(height=380, showlegend=False, coloraxis_showscale=False)
st.plotly_chart(fig4, use_container_width=True)

best_year = annual.loc[annual["avg_price"].idxmax(), "year"]
worst_year = annual.loc[annual["avg_price"].idxmin(), "year"]
latest_yr = annual[annual["year"] == latest["week"].year]["avg_price"].to_numpy()
latest_yr_str = f"${latest_yr[0]:.3f}/gal" if len(latest_yr) > 0 else "N/A"

interpret(
    f"The most expensive year for gasoline was <b>{best_year}</b> "
    f"(avg: ${annual['avg_price'].max():.3f}/gal) and the cheapest was <b>{worst_year}</b> "
    f"(avg: ${annual['avg_price'].min():.3f}/gal). "
    f"The average so far in <b>{latest['week'].year}</b> is <b>{latest_yr_str}</b>."
)

st.divider()

# =========================
# Chart 5: Price distribution
# =========================
st.subheader("⑤ Gasoline Price Distribution")

fig5 = px.histogram(
    filtered,
    x="gasoline_price",
    nbins=50,
    color_discrete_sequence=["#DC641E"],
    labels={"gasoline_price": "Gasoline Price ($/gal)", "count": "Weeks"},
)
fig5.update_layout(height=360, bargap=0.05)
st.plotly_chart(fig5, use_container_width=True)

median_price = filtered["gasoline_price"].median()
pos = "above" if current_price > median_price else "below"
half = "upper" if current_price > median_price else "lower"
interpret(
    f"Over the selected period, the median gasoline price was <b>${median_price:.3f}/gal</b>. "
    f"The current price of <b>${current_price:.3f}/gal</b> (as of <b>{latest_date}</b>) is "
    f"<b>{pos}</b> the historical median, placing it in the "
    f"<b>{half} half</b> of the price distribution."
)

st.divider()

with st.expander("Show raw gasoline price data"):
    display = filtered[["week", "gasoline_price", "weekly_change", "pct_change"]].copy()
    display["week"] = display["week"].dt.strftime("%Y-%m-%d")
    display.columns = ["Week", "Gasoline Price ($/gal)", "Weekly Change", "% Change"]
    st.dataframe(display.sort_values("Week", ascending=False), use_container_width=True)

elapsed = time.time() - start_time
st.caption(f"Page loaded in {elapsed:.2f} seconds")
