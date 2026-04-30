import time

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account
from scipy import stats

start_time = time.time()

st.set_page_config(page_title="Price Transmission Analysis", layout="wide")

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

P_SIGNIFICANCE = 0.05
MAX_LAG = 12


def interpret(text: str):
    st.markdown(
        f"<p style='font-size:0.95rem; color:#444; margin-top:-0.5rem;'>{text}</p>",
        unsafe_allow_html=True,
    )


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

st.title("Price Transmission Analysis")
st.caption(
    "This page quantifies the relationship between geopolitical conflict intensity, "
    "WTI crude oil prices, and U.S. retail gasoline prices — and explores how long "
    "it takes for conflict signals to transmit through to prices consumers pay "
    "at the pump."
)

PROJECT_ID = "sipa-adv-c-giggling-wombat"
GDELT_TABLE = f"{PROJECT_ID}.giggling_wombat.gdelt_weekly"
WTI_TABLE = f"{PROJECT_ID}.petroleum_supply.weekly_wti"
GASOLINE_TABLE = f"{PROJECT_ID}.giggling_wombat.weekly_gasoline"


@st.cache_resource
def get_bq_client():
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"]
    )
    return bigquery.Client(credentials=credentials, project=credentials.project_id)


@st.cache_data(ttl=60 * 60)
def load_data() -> pd.DataFrame:
    client = get_bq_client()

    gdelt = client.query(f"""
        SELECT
            DATE(week) as week,
            AVG(avg_goldstein) as avg_goldstein,
            SUM(total_mentions) as total_mentions
        FROM `{GDELT_TABLE}`
        WHERE week IS NOT NULL
        GROUP BY DATE(week)
        ORDER BY week
    """).to_dataframe(create_bqstorage_client=False)

    wti = client.query(f"""
        SELECT DATE(week) as week, wti_price
        FROM `{WTI_TABLE}`
        WHERE week IS NOT NULL
        ORDER BY week
    """).to_dataframe(create_bqstorage_client=False)

    gasoline = client.query(f"""
        SELECT DATE(week) as week, gasoline_price
        FROM `{GASOLINE_TABLE}`
        WHERE week IS NOT NULL
        ORDER BY week
    """).to_dataframe(create_bqstorage_client=False)

    for frame in [gdelt, wti, gasoline]:
        frame["week"] = pd.to_datetime(frame["week"]).dt.to_period("W").dt.start_time

    gdelt = (
        gdelt.groupby("week")
        .agg(
            avg_goldstein=("avg_goldstein", "mean"),
            total_mentions=("total_mentions", "sum"),
        )
        .reset_index()
    )
    wti = wti.groupby("week").agg(wti_price=("wti_price", "mean")).reset_index()
    gasoline = gasoline.groupby("week").agg(gasoline_price=("gasoline_price", "mean")).reset_index()

    df = gdelt.merge(wti, on="week", how="inner").merge(gasoline, on="week", how="inner")
    df["avg_goldstein"] = pd.to_numeric(df["avg_goldstein"], errors="coerce")
    df["wti_price"] = pd.to_numeric(df["wti_price"], errors="coerce")
    df["gasoline_price"] = pd.to_numeric(df["gasoline_price"], errors="coerce")
    return df.dropna().sort_values("week").reset_index(drop=True)


try:
    df = load_data()
except Exception as e:
    st.error(f"Failed to load data: {e}")
    st.stop()

if df.empty:
    st.error("No data available after merging all datasets.")
    st.stop()

st.sidebar.header("Filters")
min_week = df["week"].min().date()
max_week = df["week"].max().date()

start_week = st.sidebar.date_input(
    "Start week", value=min_week, min_value=min_week, max_value=max_week
)
end_week = st.sidebar.date_input("End week", value=max_week, min_value=min_week, max_value=max_week)

filtered = df[
    (df["week"] >= pd.to_datetime(start_week)) & (df["week"] <= pd.to_datetime(end_week))
].copy()

if filtered.empty:
    st.warning("No data available for selected date range.")
    st.stop()

start_str = pd.to_datetime(start_week).strftime("%B %d, %Y")
end_str = pd.to_datetime(end_week).strftime("%B %d, %Y")

r1, _ = stats.pearsonr(filtered["avg_goldstein"], filtered["wti_price"])
r2, _ = stats.pearsonr(filtered["wti_price"], filtered["gasoline_price"])

c1, c2, c3, c4 = st.columns(4)
c1.metric("Weeks of data", f"{len(filtered):,}")
c2.metric("Conflict -> WTI (r)", f"{r1:.3f}")
c3.metric("WTI -> Gasoline (r)", f"{r2:.3f}")
c4.metric("Avg Goldstein score", f"{filtered['avg_goldstein'].mean():.2f}")

st.divider()

# =========================
# Section 1: Conflict -> WTI
# =========================
st.header("① How Much Does Conflict Affect WTI Price?")

slope1, intercept1, r1, p1, _ = stats.linregress(filtered["avg_goldstein"], filtered["wti_price"])

col1, col2 = st.columns([2, 1])

with col1:
    fig1 = px.scatter(
        filtered,
        x="avg_goldstein",
        y="wti_price",
        color="week",
        color_continuous_scale="Blues",
        opacity=0.6,
        labels={
            "avg_goldstein": "Avg Goldstein Score (← More conflict)",
            "wti_price": "WTI Price (USD/bbl)",
            "week": "Week",
        },
        trendline="ols",
    )
    fig1.update_layout(height=420, coloraxis_showscale=False)
    st.plotly_chart(fig1, use_container_width=True)

with col2:
    st.markdown("### Key Statistics")
    st.metric("Pearson R", f"{r1:.3f}")
    st.metric("R²", f"{r1**2:.3f}")
    st.metric("P-value", f"{p1:.4f}")
    st.metric("Slope", f"{slope1:.2f} USD/unit")
    st.markdown("---")
    sig1 = "Statistically significant" if p1 < P_SIGNIFICANCE else "Not significant"
    st.markdown(f"**{sig1}** (p < 0.05)")

    st.markdown("**Technical:**")
    st.markdown(
        f"A 1-unit increase in Goldstein score is associated with a "
        f"**${slope1:.2f}/bbl** change in WTI."
    )

    st.markdown("**In plain English:**")
    direction1 = "rises" if slope1 < 0 else "falls"
    reliable = "statistically reliable" if p1 < P_SIGNIFICANCE else "not statistically reliable"
    st.info(
        f"When conflict intensifies in oil-producing countries, "
        f"WTI price tends to **{direction1}** by about "
        f"**${abs(slope1):.2f}/bbl** per unit of increased conflict intensity. "
        f"This is {reliable} based on {len(filtered):,} weeks of data "
        f"({start_str} to {end_str})."
    )

sig_text1 = (
    "This is statistically significant (p < 0.05)."
    if p1 < P_SIGNIFICANCE
    else "This is not statistically significant (p >= 0.05)."
)
interpret(
    f"Over <b>{len(filtered):,} weeks</b> from <b>{start_str}</b> to "
    f"<b>{end_str}</b>, the Pearson correlation between conflict intensity "
    f"and WTI price was <b>r = {r1:.3f}</b> (R² = {r1**2:.3f}), meaning "
    f"conflict explains <b>{r1**2 * 100:.1f}%</b> of WTI price variation. "
    f"{sig_text1}"
)

st.divider()

# =========================
# Section 2: WTI -> Gasoline
# =========================
st.header("② How Much Does WTI Affect Gasoline Price?")

slope2, intercept2, r2, p2, _ = stats.linregress(filtered["wti_price"], filtered["gasoline_price"])

col3, col4 = st.columns([2, 1])

with col3:
    fig2 = px.scatter(
        filtered,
        x="wti_price",
        y="gasoline_price",
        color="week",
        color_continuous_scale="Oranges",
        opacity=0.6,
        labels={
            "wti_price": "WTI Price (USD/bbl)",
            "gasoline_price": "Gasoline Price (USD/gal)",
            "week": "Week",
        },
        trendline="ols",
    )
    fig2.update_layout(height=420, coloraxis_showscale=False)
    st.plotly_chart(fig2, use_container_width=True)

with col4:
    st.markdown("### Key Statistics")
    st.metric("Pearson R", f"{r2:.3f}")
    st.metric("R²", f"{r2**2:.3f}")
    st.metric("P-value", f"{p2:.4f}")
    st.metric("Slope", f"${slope2:.4f}/gal per $/bbl")
    st.markdown("---")
    sig2 = "Statistically significant" if p2 < P_SIGNIFICANCE else "Not significant"
    st.markdown(f"**{sig2}** (p < 0.05)")

    st.markdown("**Technical:**")
    st.markdown(
        f"A $1 increase in WTI is associated with a **${slope2:.4f}/gal** change in gasoline."
    )

    st.markdown("**In plain English:**")
    cents = slope2 * 100
    st.info(
        f"Every **$1 increase in crude oil price** leads to about "
        f"**{cents:.1f} cents more per gallon** at the pump. "
        f"With R² = {r2**2:.3f}, crude oil explains "
        f"**{r2**2 * 100:.0f}%** of gasoline price variation — "
        f"making it the single biggest driver of what consumers pay."
    )

sig_text2 = (
    "This relationship is statistically significant (p < 0.05)."
    if p2 < P_SIGNIFICANCE
    else "This relationship is not statistically significant (p >= 0.05)."
)
interpret(
    f"WTI crude oil price explains <b>{r2**2 * 100:.1f}%</b> of the variation "
    f"in U.S. gasoline prices (R² = {r2**2:.3f}, r = {r2:.3f}). "
    f"For every <b>$1 increase</b> in WTI, gasoline prices rise by "
    f"approximately <b>{slope2 * 100:.1f} cents per gallon</b>. "
    f"{sig_text2}"
)

st.divider()

# =========================
# Section 3: Time lag analysis
# =========================
st.header("③ Time Lag Analysis: How Long Does It Take?")

lags = list(range(1, MAX_LAG + 1))
corr_conflict_wti = []
corr_conflict_gas = []
corr_wti_gas = []

for lag in lags:
    for src, tgt, store in [
        ("avg_goldstein", "wti_price", corr_conflict_wti),
        ("avg_goldstein", "gasoline_price", corr_conflict_gas),
        ("wti_price", "gasoline_price", corr_wti_gas),
    ]:
        shifted = filtered[src].shift(lag)
        valid = filtered[[tgt]].join(shifted.rename("shifted")).dropna()
        r, _ = stats.pearsonr(valid["shifted"], valid[tgt])
        store.append(round(r, 4))

fig3 = go.Figure()
fig3.add_trace(
    go.Scatter(
        x=lags,
        y=corr_conflict_wti,
        name="Conflict -> WTI",
        mode="lines+markers",
        line=dict(color="#1B4F8A", width=2),
        marker=dict(size=8),
    )
)
fig3.add_trace(
    go.Scatter(
        x=lags,
        y=corr_conflict_gas,
        name="Conflict -> Gasoline",
        mode="lines+markers",
        line=dict(color="crimson", width=2),
        marker=dict(size=8),
    )
)
fig3.add_trace(
    go.Scatter(
        x=lags,
        y=corr_wti_gas,
        name="WTI -> Gasoline",
        mode="lines+markers",
        line=dict(color="#DC641E", width=2),
        marker=dict(size=8),
    )
)
fig3.add_hline(y=0, line_color="gray", line_dash="dash", line_width=1)
fig3.update_layout(
    xaxis=dict(title="Lag (weeks)", tickvals=lags),
    yaxis_title="Pearson Correlation",
    hovermode="x unified",
    height=420,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig3, use_container_width=True)

best_lag_wti = lags[np.argmax(np.abs(corr_conflict_wti))]
best_lag_gas = lags[np.argmax(np.abs(corr_conflict_gas))]
best_lag_wti_gas = lags[np.argmax(np.abs(corr_wti_gas))]

col5, col6, col7 = st.columns(3)
col5.metric(
    "Strongest Conflict -> WTI lag",
    f"{best_lag_wti} weeks",
    f"r = {corr_conflict_wti[best_lag_wti - 1]:.3f}",
)
col6.metric(
    "Strongest Conflict -> Gasoline lag",
    f"{best_lag_gas} weeks",
    f"r = {corr_conflict_gas[best_lag_gas - 1]:.3f}",
)
col7.metric(
    "Strongest WTI -> Gasoline lag",
    f"{best_lag_wti_gas} weeks",
    f"r = {corr_wti_gas[best_lag_wti_gas - 1]:.3f}",
)

interpret(
    f"Geopolitical conflict in oil-producing countries takes about "
    f"<b>{best_lag_wti} week(s)</b> to have its strongest effect on WTI crude "
    f"oil prices (r = {corr_conflict_wti[best_lag_wti - 1]:.3f}), and about "
    f"<b>{best_lag_gas} week(s)</b> before consumers feel it at the pump "
    f"(r = {corr_conflict_gas[best_lag_gas - 1]:.3f}). "
    f"WTI price changes transmit to gasoline prices most strongly after "
    f"<b>{best_lag_wti_gas} week(s)</b> "
    f"(r = {corr_wti_gas[best_lag_wti_gas - 1]:.3f}). "
    f"This suggests policymakers have a window of roughly "
    f"<b>{best_lag_gas} weeks</b> to respond before a conflict-driven oil "
    f"price spike reaches everyday consumers."
)

st.divider()

# =========================
# Section 4: Full transmission chain
# =========================
st.header("④ Full Transmission Chain Over Time")

norm = filtered.copy()
for col in ["avg_goldstein", "wti_price", "gasoline_price"]:
    norm[col] = (norm[col] - norm[col].mean()) / norm[col].std()
norm["avg_goldstein"] = norm["avg_goldstein"] * -1

fig4 = go.Figure()
fig4.add_trace(
    go.Scatter(
        x=norm["week"],
        y=norm["avg_goldstein"],
        name="Conflict Intensity (inverted)",
        mode="lines",
        line=dict(color="crimson", width=1.5, dash="dot"),
    )
)
fig4.add_trace(
    go.Scatter(
        x=norm["week"],
        y=norm["wti_price"],
        name="WTI Price",
        mode="lines",
        line=dict(color="#1B4F8A", width=2),
    )
)
fig4.add_trace(
    go.Scatter(
        x=norm["week"],
        y=norm["gasoline_price"],
        name="Gasoline Price",
        mode="lines",
        line=dict(color="#DC641E", width=2),
    )
)
fig4.update_layout(
    yaxis_title="Normalized value (z-score)",
    xaxis_title="Week",
    hovermode="x unified",
    height=420,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig4, use_container_width=True)

direction_str = "negative" if r1 < 0 else "positive"
interpret(
    f"The normalized chart above shows the full transmission chain from "
    f"<b>{start_str}</b> to <b>{end_str}</b>. "
    f"WTI (blue) and gasoline (orange) prices move closely together "
    f"(r = {r2:.3f}), while conflict intensity (red dashed) shows a "
    f"{direction_str} relationship with both price series. "
    f"Visually, peaks in conflict intensity tend to precede upward movements "
    f"in WTI and gasoline prices by approximately "
    f"<b>{best_lag_wti} to {best_lag_gas} weeks</b>."
)

st.divider()

with st.expander("Show merged dataset"):
    display = filtered.copy()
    display["week"] = display["week"].dt.strftime("%Y-%m-%d")
    st.dataframe(display, use_container_width=True)

elapsed = time.time() - start_time
st.caption(f"Page loaded in {elapsed:.2f} seconds")
