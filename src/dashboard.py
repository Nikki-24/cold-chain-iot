import sys
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yaml
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent))
from ml_model import fetch_data, detect_anomalies, get_anomaly_summary

config_path = Path(__file__).parent.parent / "config" / "config.yaml"
with open(config_path) as f:
    config = yaml.safe_load(f)

st.set_page_config(
    page_title="Cold Chain Monitor",
    page_icon="🌡",
    layout="wide"
)

st.title("Cold Chain Temperature Monitor")
st.caption(f"Device: {config['device']['id']} | Location: {config['device']['location']}")

def load_data(hours=24):
    try:
        df = fetch_data(hours=hours)
        if df.empty:
            return pd.DataFrame()
        df = df.rename(columns={"_time": "time"})
        df["time"] = pd.to_datetime(df["time"])
        df = df.sort_values("time")
        return df
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

st.sidebar.header("Controls")
hours = st.sidebar.slider("Hours of data", 1, 48, 24)
auto_refresh = st.sidebar.checkbox("Auto refresh (10s)", value=True)

df = load_data(hours=hours)

if df.empty:
    st.warning("No data yet. Make sure your ESP32 is running and sending data.")
    st.stop()

df = detect_anomalies(df)
summary = get_anomaly_summary(df)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Records", summary.get("total_records", 0))
col2.metric("Anomalies Found", summary.get("anomaly_count", 0))
col3.metric("Avg Temperature", f"{summary.get('avg_temp', 0)}°C")
col4.metric("Anomaly Rate", f"{summary.get('anomaly_rate', 0)}%")

st.divider()

st.subheader("Live Temperature & Humidity")
fig1 = go.Figure()
fig1.add_trace(go.Scatter(
    x=df["time"], y=df["temperature"],
    name="Temperature (°C)",
    line=dict(color="#EF4444", width=2)
))
fig1.add_trace(go.Scatter(
    x=df["time"], y=df["humidity"],
    name="Humidity (%)",
    line=dict(color="#3B82F6", width=2),
    yaxis="y2"
))
fig1.add_hline(y=config["thresholds"]["temp_alert_high"],
               line_dash="dash", line_color="orange",
               annotation_text="Max safe (8°C)")
fig1.add_hline(y=config["thresholds"]["temp_alert_low"],
               line_dash="dash", line_color="blue",
               annotation_text="Min safe (2°C)")
fig1.update_layout(
    yaxis=dict(title="Temperature (°C)"),
    yaxis2=dict(title="Humidity (%)", overlaying="y", side="right"),
    hovermode="x unified",
    height=400
)
st.plotly_chart(fig1, use_container_width=True)

st.divider()

st.subheader("Anomaly Detection — Isolation Forest")
fig2 = px.scatter(
    df, x="time", y="temperature",
    color="anomaly",
    color_discrete_map={True: "#EF4444", False: "#22C55E"},
    labels={"anomaly": "Anomaly", "temperature": "Temperature (°C)"},
    height=400
)
fig2.add_hline(y=config["thresholds"]["temp_alert_high"],
               line_dash="dash", line_color="orange")
fig2.add_hline(y=config["thresholds"]["temp_alert_low"],
               line_dash="dash", line_color="blue")
st.plotly_chart(fig2, use_container_width=True)

st.divider()

st.subheader("Recent Readings")
recent = df.tail(20)[["time", "temperature", "humidity", "anomaly"]].copy()
recent["time"] = recent["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
recent["temperature"] = recent["temperature"].round(2)
recent["humidity"] = recent["humidity"].round(2)
st.dataframe(recent, use_container_width=True)

if auto_refresh:
    time.sleep(10)
    st.rerun()