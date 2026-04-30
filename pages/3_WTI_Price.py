import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

start_time = time.time()

st.set_page_config(page_title="WTI Price", layout="wide")

# =========================
# Helper: render interpretation text
# =========================
def interpret(text: str):
    st.markdown(
        f"<p style='font-size:0.95rem; color:#444; margin-top:-0.5rem;'>{text}</p>",
        unsafe_allow_html=True,
    )

# =========================
# Sidebar
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
# Page header
# =========================
st.title("WTI Crude Oil Price")
st.caption(
    "West Texas Intermediate (WTI) is the benchmark crude oil price for the United States. "
    "This page explores weekly WTI price trends, volatility, and key price movements since 2012."
)

# =========================
# Config
# =========================
PROJECT_ID = "sipa-adv-c-giggling-wombat"
WTI_TABLE  = f"{PROJECT_ID}.petroleum_supply.weekly_wti"


@st.cache_resource
def get_bq_client():
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"]
    )
    return bigquery.Client(credentials=credentials, project=credentials.project_id)


@st.cache_data(ttl=60 * 60)
def load_wti() -> pd.DataFrame:
    client = get_bq_client()
    query  = f"SELECT week, wti_price FROM `{WTI_TABLE}` ORDER BY week"
    df = client.query(query).to_dataframe(create_bqstorage_client=False)
    df["week"]      = pd.to_datetime(df["week"])
    df["wti_price"] = pd.to_numeric(df["wti_price"], errors="coerce")
    return df.dropna().sort_values("week").reset_index(drop=True)


# =========================
# Load data
# =========================
try:
    wti = load_wti()
except Exception as e:
    st.error(f"Failed to load WTI data: {e}")
    st.stop()

# =========================
# Sidebar filters
# =========================
st.sidebar.header("Filters")
min_week = wti["week"].min().date()
max_week = wti["week"].max().date()

start_week = st.sidebar.date_input(
    "Start week",
    value=pd.to_datetime("2012-01-01").date(),
    min_value=min_week,
    max_value=max_week,
)
end_week = st.sidebar.date_input(
    "End week", value=max_week, min_value=min_week, max_value=max_week
)

# =========================
# Filter & derived columns
# =========================
filtered = wti[
    (wti["week"] >= pd.to_datetime(start_week)) &
    (wti["week"] <= pd.to_datetime(end_week))
].copy()

if filtered.empty:
    st.warning("No data available for selected date range.")
    st.stop()

filtered["wti_smooth"]    = filtered["wti_price"].rolling(4, center=True).mean()
filtered["weekly_change"] = filtered["wti_price"].diff()
filtered["pct_change"]    = filtered["wti_price"].pct_change() * 100
filtered["year"]          = filtered["week"].dt.year
filtered["rolling_std"]   = filtered["wti_price"].rolling(12).std()
filtered["ma4"]           = filtered["wti_price"].rolling(4).mean()
filtered["range12_high"]  = filtered["wti_price"].rolling(12).max()
filtered["range12_low"]   = filtered["wti_price"].rolling(12).min()

latest        = filtered.iloc[-1]
prev          = filtered.iloc[-2] if len(filtered) > 1 else None
latest_date   = latest["week"].strftime("%B %d, %Y")
prev_date     = prev["week"].strftime("%B %d, %Y") if prev is not None else ""
current_price = latest["wti_price"]
ma4_val       = latest["ma4"]
range_high    = latest["range12_high"]
range_low     = latest["range12_low"]
volatility    = latest["rolling_std"]
avg_vol       = filtered["rolling_std"].mean()

# =========================
# Summary metrics
# =========================
c1, c2, c3, c4 = st.columns(4)
c1.metric("Current WTI Price", f"${current_price:.2f}/bbl", help=f"As of {latest_date}")
c2.metric("Average Price",     f"${filtered['wti_price'].mean():.2f}/bbl")
c3.metric("All-time High",     f"${filtered['wti_price'].max():.2f}/bbl")
c4.metric("All-time Low",      f"${filtered['wti_price'].min():.2f}/bbl")

st.divider()

# =========================
# Chart 1: WTI Price timeline
# =========================
st.subheader("① WTI Price Over Time")

fig1 = go.Figure()
fig1.add_trace(go.Scatter(
    x=filtered["week"], y=filtered["wti_price"],
    name="Weekly price", mode="lines",
    line=dict(color="rgba(27,79,138,0.3)", width=1),
))
fig1.add_trace(go.Scatter(
    x=filtered["week"], y=filtered["wti_smooth"],
    name="4-week avg", mode="lines",
    line=dict(color="#1B4F8A", width=2.5),
))
fig1.update_layout(yaxis_title="USD per barrel", xaxis_title="Week",
                   hovermode="x unified", height=400,
                   legend=dict(orientation="h", yanchor="bottom", y=1.02))
st.plotly_chart(fig1, use_container_width=True)

if prev is not None:
    chg   = current_price - prev["wti_price"]
    pct   = (chg / prev["wti_price"]) * 100
    dir1  = "increased" if chg > 0 else "decreased"
    arr   = "" if chg > 0 else ""
    interpret(
        f"{arr} WTI <b>{dir1}</b> by <b>${abs(chg):.2f} ({abs(pct):.2f}%)</b> "
        f"from <b>{prev_date}</b> to <b>{latest_date}</b>, "
        f"suggesting short-term {'upward' if chg > 0 else 'downward'} pressure."
    )

if pd.notna(ma4_val):
    vs_ma = "above" if current_price > ma4_val else "below"
    impl = (
        "suggesting stronger short-term pricing momentum."
        if current_price > ma4_val
        else "which may suggest weaker short-term pricing."
    )
    interpret(
        f"The latest price on <b>{latest_date}</b> (<b>${current_price:.2f}</b>) is "
        f"<b>{vs_ma}</b> the 4-week moving average (<b>${ma4_val:.2f}</b>), {impl}"
    )

st.divider()

# =========================
# Chart 2: Weekly price change
# =========================
st.subheader("② Weekly Price Change")

fig2 = go.Figure()
fig2.add_trace(go.Bar(
    x=filtered["week"], y=filtered["weekly_change"],
    marker_color=filtered["weekly_change"].apply(lambda x: "steelblue" if x >= 0 else "crimson"),
    name="Weekly change",
))
fig2.update_layout(yaxis_title="USD change per barrel", xaxis_title="Week",
                   hovermode="x unified", height=380)
st.plotly_chart(fig2, use_container_width=True)

if prev is not None:
    chg         = current_price - prev["wti_price"]
    dir2        = "gain" if chg > 0 else "loss"
    max_chg     = filtered["weekly_change"].abs().max()
    max_chg_week = filtered.loc[
        filtered["weekly_change"].abs() == max_chg, "week"
    ].iloc[0]
    max_chg_date = max_chg_week.strftime("%B %d, %Y")
    interpret(
        f"The most recent week ending <b>{latest_date}</b> recorded a price {dir2} of "
        f"<b>${abs(chg):.2f}/bbl</b>. "
        f"The largest single-week move in this period was "
        f"<b>${max_chg:.2f}/bbl</b> on <b>{max_chg_date}</b>."
    )

st.divider()

# =========================
# Chart 3: Rolling volatility
# =========================
st.subheader("③ Price Volatility (12-week Rolling Std Dev)")

fig3 = go.Figure()
fig3.add_trace(go.Scatter(
    x=filtered["week"], y=filtered["rolling_std"],
    mode="lines", fill="tozeroy",
    line=dict(color="#1B4F8A", width=1.5),
    fillcolor="rgba(27,79,138,0.15)",
    name="Volatility",
))
fig3.update_layout(yaxis_title="Std Dev (USD/bbl)", xaxis_title="Week",
                   hovermode="x unified", height=360)
st.plotly_chart(fig3, use_container_width=True)

if pd.notna(volatility) and pd.notna(avg_vol):
    if volatility > avg_vol * 1.25:
        vol_desc = f"<b>relatively volatile</b> compared to its historical average (${avg_vol:.2f})"
    elif volatility < avg_vol * 0.75:
        vol_desc = f"<b>relatively stable</b> compared to its historical average (${avg_vol:.2f})"
    else:
        vol_desc = (
            f"at <b>moderate volatility</b> compared to its "
            f"historical average (${avg_vol:.2f})"
        )

    if pd.notna(range_high) and pd.notna(range_low):
        interpret(
            f"As of <b>{latest_date}</b>, WTI remains within its recent 12-week range of "
            f"<b>${range_low:.2f}</b> to <b>${range_high:.2f}</b>. "
            f"Recent price movements have been {vol_desc}."
        )

st.divider()

# =========================
# Chart 4: Annual average price
# =========================
st.subheader("④ Annual Average WTI Price")

annual = filtered.groupby("year")["wti_price"].mean().reset_index()
annual.columns = ["year", "avg_price"]

fig4 = px.bar(
    annual, x="year", y="avg_price",
    color="avg_price", color_continuous_scale="Blues",
    labels={"year": "Year", "avg_price": "Avg WTI Price (USD/bbl)"},
    text=annual["avg_price"].apply(lambda x: f"${x:.1f}"),
)
fig4.update_traces(textposition="outside")
fig4.update_layout(height=380, showlegend=False, coloraxis_showscale=False)
st.plotly_chart(fig4, use_container_width=True)

best_year  = annual.loc[annual["avg_price"].idxmax(), "year"]
worst_year = annual.loc[annual["avg_price"].idxmin(), "year"]
latest_yr  = annual[annual["year"] == latest["week"].year]["avg_price"].to_numpy()
latest_yr_str = f"${latest_yr[0]:.2f}/bbl" if len(latest_yr) > 0 else "N/A"

interpret(
    f"The highest annual average was in <b>{best_year}</b> (${annual['avg_price'].max():.2f}/bbl) "
    f"and the lowest in <b>{worst_year}</b> (${annual['avg_price'].min():.2f}/bbl). "
    f"The average so far in <b>{latest['week'].year}</b> is <b>{latest_yr_str}</b>."
)

st.divider()

# =========================
# Chart 5: Price distribution
# =========================
st.subheader("⑤ WTI Price Distribution")

fig5 = px.histogram(
    filtered, x="wti_price", nbins=50,
    color_discrete_sequence=["#1B4F8A"],
    labels={"wti_price": "WTI Price (USD/bbl)", "count": "Weeks"},
)
fig5.update_layout(height=360, bargap=0.05)
st.plotly_chart(fig5, use_container_width=True)

median_price = filtered["wti_price"].median()
pos          = "above" if current_price > median_price else "below"
half         = "upper" if current_price > median_price else "lower"
interpret(
    f"Over the selected period, the median WTI price was <b>${median_price:.2f}/bbl</b>. "
    f"The current price of <b>${current_price:.2f}</b> (as of <b>{latest_date}</b>) is "
    f"<b>{pos}</b> the historical median, placing it in the "
    f"<b>{half} half</b> of the price distribution."
)

st.divider()

with st.expander("Show raw WTI data"):
    display = filtered[["week", "wti_price", "weekly_change", "pct_change"]].copy()
    display["week"] = display["week"].dt.strftime("%Y-%m-%d")
    display.columns = ["Week", "WTI Price (USD/bbl)", "Weekly Change", "% Change"]
    st.dataframe(display.sort_values("Week", ascending=False), use_container_width=True)

elapsed = time.time() - start_time
st.caption(f"Page loaded in {elapsed:.2f} seconds")
