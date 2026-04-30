import time

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from google.cloud import bigquery
from google.oauth2 import service_account

start_time = time.time()

st.set_page_config(page_title="Conflict Context", layout="wide")


# =========================
# Helper: render interpretation
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
st.sidebar.caption("Source: GDELT")
st.sidebar.divider()

# =========================
# Page header
# =========================
st.title("Geopolitical Conflict Context")
st.caption(
    "This page explores conflict events in major oil-producing countries using GDELT — "
    "a real-time global event dataset sourced from worldwide news media. "
    "Countries covered: Russia, Iran, Iraq, Saudi Arabia, Libya, "
    "Venezuela, UAE, Kuwait, Nigeria, Algeria."
)

# =========================
# Config
# =========================
PROJECT_ID  = "sipa-adv-c-giggling-wombat"
GDELT_TABLE = f"{PROJECT_ID}.giggling_wombat.gdelt_weekly"

EVENT_ROOT_LABELS = {
    "15": "Military Posture",
    "16": "Reduce Relations",
    "17": "Coerce",
    "18": "Assault",
    "19": "Fight",
    "20": "Mass Violence",
}

ISO3_MAP = {
    "Russia":               "RUS",
    "Iran":                 "IRN",
    "Iraq":                 "IRQ",
    "Saudi Arabia":         "SAU",
    "Libya":                "LBY",
    "Venezuela":            "VEN",
    "United Arab Emirates": "ARE",
    "Kuwait":               "KWT",
    "Nigeria":              "NGA",
    "Algeria":              "DZA",
}


@st.cache_resource
def get_bq_client():
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"]
    )
    return bigquery.Client(credentials=credentials, project=credentials.project_id)


@st.cache_data(ttl=60 * 60)
def load_gdelt() -> pd.DataFrame:
    client = get_bq_client()
    query = f"""
        SELECT week, country, country_code, event_root_code, event_code,
               event_code_desc, event_count, total_mentions, avg_goldstein, avg_tone
        FROM `{GDELT_TABLE}`
        ORDER BY week
    """
    df = client.query(query).to_dataframe(create_bqstorage_client=False)
    df["week"] = pd.to_datetime(df["week"])
    df["event_root_label"] = df["event_root_code"].map(EVENT_ROOT_LABELS).fillna("Other")
    df["iso3"] = df["country"].map(ISO3_MAP)
    df["year"] = df["week"].dt.year
    return df


# =========================
# Load data
# =========================
try:
    gdelt = load_gdelt()
except Exception as e:
    st.error(f"Failed to load GDELT data: {e}")
    st.stop()

# =========================
# Sidebar filters
# =========================
st.sidebar.header("Filters")

min_week = gdelt["week"].min().date()
max_week = gdelt["week"].max().date()

start_week = st.sidebar.date_input(
    "Start week", value=pd.to_datetime("2015-01-01").date(),
    min_value=min_week, max_value=max_week
)
end_week = st.sidebar.date_input(
    "End week", value=max_week,
    min_value=min_week, max_value=max_week
)

all_countries = sorted(gdelt["country"].dropna().unique().tolist())
selected_countries = st.sidebar.multiselect("Countries", all_countries, default=all_countries)

all_root_codes = sorted(gdelt["event_root_code"].dropna().unique().tolist())
selected_root_codes = st.sidebar.multiselect(
    "Conflict type", options=all_root_codes, default=all_root_codes,
    format_func=lambda x: f"{x} — {EVENT_ROOT_LABELS.get(x, 'Other')}",
)

# =========================
# Filter data
# =========================
filtered = gdelt[
    (gdelt["week"] >= pd.to_datetime(start_week)) &
    (gdelt["week"] <= pd.to_datetime(end_week)) &
    (gdelt["country"].isin(selected_countries)) &
    (gdelt["event_root_code"].isin(selected_root_codes))
].copy()

if filtered.empty:
    st.warning("No data available for selected filters.")
    st.stop()

weekly = filtered.groupby("week").agg(
    avg_goldstein=("avg_goldstein", "mean"),
    event_count=("event_count", "sum"),
    total_mentions=("total_mentions", "sum"),
    avg_tone=("avg_tone", "mean"),
).reset_index()
weekly["goldstein_smooth"] = weekly["avg_goldstein"].rolling(4, center=True).mean()

start_str = pd.to_datetime(start_week).strftime("%B %d, %Y")
end_str   = pd.to_datetime(end_week).strftime("%B %d, %Y")

# =========================
# Summary metrics
# =========================
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total conflict events",  f"{filtered['event_count'].sum():,.0f}")
c2.metric("Total media mentions",   f"{filtered['total_mentions'].sum():,.0f}")
c3.metric("Avg Goldstein score",    f"{filtered['avg_goldstein'].mean():.2f}")
c4.metric("Avg news tone",          f"{filtered['avg_tone'].mean():.2f}")

st.divider()

# =========================
# Chart 1: Choropleth map
# =========================
st.subheader("① Conflict Intensity Map")

map_df = filtered.groupby(["year", "country", "iso3"]).agg(
    avg_goldstein=("avg_goldstein", "mean"),
    event_count=("event_count", "sum"),
    total_mentions=("total_mentions", "sum"),
).reset_index().round({"avg_goldstein": 2})

g_min = map_df["avg_goldstein"].min()
g_max = map_df["avg_goldstein"].max()
g_mid = (g_min + g_max) / 2

fig_map = px.choropleth(
    map_df, locations="iso3", color="avg_goldstein",
    hover_name="country",
    hover_data={
        "avg_goldstein": ":.2f", "event_count": ":,.0f",
        "total_mentions": ":,.0f", "iso3": False, "year": False,
    },
    animation_frame="year",
    color_continuous_scale=[
        [0.0, "#d73027"], [0.3, "#f46d43"], [0.5, "#fee08b"],
        [0.7, "#d9ef8b"], [1.0, "#1a9850"],
    ],
    range_color=[g_min, g_max],
    labels={
        "avg_goldstein": "Avg Goldstein",
        "event_count": "Events",
        "total_mentions": "Mentions",
    },
)
fig_map.update_geos(
    showframe=False, showcoastlines=True, coastlinecolor="lightgray",
    showland=True, landcolor="#f5f5f5", showocean=True, oceancolor="#e8f4f8",
    showlakes=True, lakecolor="#e8f4f8", showcountries=True, countrycolor="white",
    projection_type="natural earth",
)
fig_map.update_layout(
    coloraxis_colorbar=dict(
        title="Goldstein",
        tickvals=[g_min, g_mid, g_max],
        ticktext=[f"{g_min:.1f} (Intense)", f"{g_mid:.1f}", f"{g_max:.1f} (Calm)"],
    ),
    height=520, margin=dict(l=0, r=0, t=10, b=0),
)
st.plotly_chart(fig_map, use_container_width=True)

# Interpretation — map
most_intense_country = map_df.groupby("country")["avg_goldstein"].mean().idxmin()
most_intense_score   = map_df.groupby("country")["avg_goldstein"].mean().min()
calmest_country      = map_df.groupby("country")["avg_goldstein"].mean().idxmax()
calmest_score        = map_df.groupby("country")["avg_goldstein"].mean().max()
most_intense_year_row = map_df.loc[map_df["avg_goldstein"].idxmin()]

interpret(
    f"Across the selected period (<b>{start_str}</b> to <b>{end_str}</b>), "
    f"<b>{most_intense_country}</b> had the most intense conflict with "
    f"an average Goldstein score of "
    f"<b>{most_intense_score:.2f}</b>, while <b>{calmest_country}</b> was the most stable "
    f"(score: <b>{calmest_score:.2f}</b>). "
    f"The single most intense country-year was <b>{most_intense_year_row['country']}</b> in "
    f"<b>{int(most_intense_year_row['year'])}</b> "
    f"(score: <b>{most_intense_year_row['avg_goldstein']:.2f}</b>)."
)

st.divider()

# =========================
# Chart 2: Goldstein timeline
# =========================
st.subheader("② Conflict Intensity Over Time")

y_min = weekly["avg_goldstein"].min()
y_max = weekly["avg_goldstein"].max()
y_pad = (y_max - y_min) * 0.15

fig2 = go.Figure()
fig2.add_trace(go.Scatter(
    x=weekly["week"], y=weekly["avg_goldstein"],
    name="Weekly", mode="lines",
    line=dict(color="rgba(220,20,60,0.2)", width=1),
))
fig2.add_trace(go.Scatter(
    x=weekly["week"], y=weekly["goldstein_smooth"],
    name="4-week avg", mode="lines",
    line=dict(color="crimson", width=2.5),
))
fig2.update_layout(
    yaxis=dict(title="Goldstein Score (↑ = more conflict)", autorange="reversed",
               range=[-7.5, y_min - y_pad]),
    xaxis_title="Week", hovermode="x unified", height=400,
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig2, use_container_width=True)

# Interpretation — timeline
most_intense_week = weekly.loc[weekly["avg_goldstein"].idxmin(), "week"].strftime("%B %d, %Y")
most_intense_val  = weekly["avg_goldstein"].min()
calmest_week      = weekly.loc[weekly["avg_goldstein"].idxmax(), "week"].strftime("%B %d, %Y")
calmest_val       = weekly["avg_goldstein"].max()
latest_week_str   = weekly["week"].iloc[-1].strftime("%B %d, %Y")
latest_gold       = weekly["avg_goldstein"].iloc[-1]

interpret(
    f"The most intense conflict week was <b>{most_intense_week}</b> with a Goldstein score of "
    f"<b>{most_intense_val:.2f}</b>. The calmest week was <b>{calmest_week}</b> "
    f"(score: <b>{calmest_val:.2f}</b>). "
    f"As of <b>{latest_week_str}</b>, the average Goldstein score is <b>{latest_gold:.2f}</b>, "
    f"which is {'below' if latest_gold < weekly['avg_goldstein'].mean() else 'above'} "
    f"the period average "
    f"of <b>{weekly['avg_goldstein'].mean():.2f}</b>."
)

st.divider()

# =========================
# Chart 3: Event type breakdown
# =========================
st.subheader("③ Event Type Breakdown Over Time")

by_type = filtered.groupby(["week", "event_root_label"])["event_count"].sum().reset_index()
fig3 = px.area(
    by_type, x="week", y="event_count", color="event_root_label",
    labels={"event_count": "Event count", "week": "Week", "event_root_label": "Conflict type"},
    color_discrete_sequence=px.colors.qualitative.Set2,
)
fig3.update_layout(hovermode="x unified", height=400,
                   legend=dict(orientation="h", yanchor="bottom", y=1.02))
st.plotly_chart(fig3, use_container_width=True)

# Interpretation — event type
top_type       = filtered.groupby("event_root_label")["event_count"].sum().idxmax()
top_type_count = filtered.groupby("event_root_label")["event_count"].sum().max()
top_type_pct   = top_type_count / filtered["event_count"].sum() * 100
second_type    = filtered.groupby("event_root_label")["event_count"].sum().nlargest(2).index[1]

interpret(
    f"The dominant conflict type in the selected period was <b>{top_type}</b>, "
    f"accounting for <b>{top_type_pct:.1f}%</b> of all conflict events "
    f"({int(top_type_count):,} events). "
    f"The second most common type was <b>{second_type}</b>."
)

st.divider()

# =========================
# Chart 4: Conflict intensity by country
# =========================
st.subheader("④ Conflict Intensity by Country")

by_country = filtered.groupby("country").agg(
    avg_goldstein=("avg_goldstein", "mean"),
    total_mentions=("total_mentions", "sum"),
).reset_index().sort_values("avg_goldstein", ascending=True)

fig4 = px.bar(
    by_country, x="avg_goldstein", y="country", orientation="h",
    color="total_mentions", color_continuous_scale="Reds_r",
    labels={
        "avg_goldstein": "Avg Goldstein Score",
        "country": "Country",
        "total_mentions": "Media mentions",
    },
    height=420,
)
fig4.add_vline(x=0, line_color="gray", line_dash="dash")
st.plotly_chart(fig4, use_container_width=True)

# Interpretation — by country
most_conflict_c  = by_country.iloc[0]["country"]
most_conflict_s  = by_country.iloc[0]["avg_goldstein"]
least_conflict_c = by_country.iloc[-1]["country"]
least_conflict_s = by_country.iloc[-1]["avg_goldstein"]
most_mentioned_c = by_country.loc[by_country["total_mentions"].idxmax(), "country"]
most_mentioned_n = by_country["total_mentions"].max()

interpret(
    f"Among the selected countries, <b>{most_conflict_c}</b> had the most severe average conflict "
    f"(Goldstein: <b>{most_conflict_s:.2f}</b>), while "
    f"<b>{least_conflict_c}</b> was relatively more stable "
    f"(Goldstein: <b>{least_conflict_s:.2f}</b>). "
    f"<b>{most_mentioned_c}</b> attracted the most media attention with "
    f"<b>{most_mentioned_n:,.0f}</b> total mentions."
)

st.divider()

# =========================
# Chart 5: Media attention heatmap
# =========================
st.subheader("⑤ Media Attention Heatmap by Country & Year")

heatmap_df    = filtered.groupby(["year", "country"])["total_mentions"].sum().reset_index()
heatmap_pivot = heatmap_df.pivot_table(
    index="country", columns="year", values="total_mentions", aggfunc="sum"
).fillna(0)

fig5 = px.imshow(
    heatmap_pivot, color_continuous_scale="YlOrRd",
    labels=dict(x="Year", y="Country", color="Media mentions"),
    aspect="auto", text_auto=".0f",
)
fig5.update_layout(height=420)
st.plotly_chart(fig5, use_container_width=True)

# Interpretation — heatmap
peak_row      = heatmap_df.loc[heatmap_df["total_mentions"].idxmax()]
peak_country  = peak_row["country"]
peak_year     = int(peak_row["year"])
peak_mentions = peak_row["total_mentions"]

# Year with most total mentions
year_totals     = heatmap_df.groupby("year")["total_mentions"].sum()
busiest_year    = int(year_totals.idxmax())
busiest_mentions = year_totals.max()

interpret(
    f"The highest single-year media attention was recorded for <b>{peak_country}</b> in "
    f"<b>{peak_year}</b> with <b>{peak_mentions:,.0f}</b> total mentions. "
    f"Overall, <b>{busiest_year}</b> was the most covered year across all oil-producing countries "
    f"with <b>{busiest_mentions:,.0f}</b> total mentions."
)

st.divider()

# =========================
# Chart 6: Top conflict event types
# =========================
st.subheader("⑥ Most Covered Conflict Event Types")

top_events = (
    filtered.groupby("event_code_desc")["total_mentions"].sum()
    .reset_index()
    .sort_values("total_mentions", ascending=True)
    .tail(15)
)

fig6 = px.bar(
    top_events, x="total_mentions", y="event_code_desc", orientation="h",
    color="total_mentions", color_continuous_scale="Reds",
    labels={"total_mentions": "Total media mentions", "event_code_desc": "Event type"},
)
fig6.update_layout(height=450, showlegend=False)
st.plotly_chart(fig6, use_container_width=True)

# Interpretation — top events
top_event_name     = top_events.iloc[-1]["event_code_desc"]
top_event_mentions = top_events.iloc[-1]["total_mentions"]
top_event_pct      = top_event_mentions / filtered["total_mentions"].sum() * 100
second_event_name  = top_events.iloc[-2]["event_code_desc"]

interpret(
    f"The most media-covered conflict event type was <b>{top_event_name}</b> with "
    f"<b>{top_event_mentions:,.0f}</b> mentions, representing <b>{top_event_pct:.1f}%</b> "
    f"of all conflict-related media coverage. "
    f"The second most covered was <b>{second_event_name}</b>."
)

st.divider()

with st.expander("Show raw GDELT data"):
    display = filtered.sort_values("week", ascending=False).copy()
    display["week"] = display["week"].dt.strftime("%Y-%m-%d")
    st.dataframe(display, use_container_width=True)

elapsed = time.time() - start_time
st.caption(f"Page loaded in {elapsed:.2f} seconds")
