import logging
import yaml
import pandas as pd
from pathlib import Path
from datetime import datetime
from sklearn.ensemble import IsolationForest
from influxdb_client import InfluxDBClient

log = logging.getLogger(__name__)

config_path = Path(__file__).parent.parent / "config" / "config.yaml"
with open(config_path) as f:
    config = yaml.safe_load(f)

def fetch_data(hours=24):
    client = InfluxDBClient(
        url=config["influxdb"]["url"],
        token=config["influxdb"]["token"],
        org=config["influxdb"]["org"]
    )
    query_api = client.query_api()
    query = f'''
    from(bucket: "{config["influxdb"]["bucket"]}")
        |> range(start: -{hours}h)
        |> filter(fn: (r) => r._measurement == "sensor_data")
        |> filter(fn: (r) => r._field == "temperature" or r._field == "humidity")
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
    '''
    try:
        tables = query_api.query_data_frame(query)
        client.close()
        return tables
    except Exception as e:
        log.error(f"Error fetching data: {e}")
        client.close()
        return pd.DataFrame()

def detect_anomalies(df):
    if df.empty or len(df) < 10:
        log.warning("Not enough data for anomaly detection")
        df["anomaly"] = False
        df["anomaly_score"] = 0
        return df
    features = df[["temperature", "humidity"]].dropna()
    model = IsolationForest(
        contamination=0.05,
        random_state=42,
        n_estimators=100
    )
    predictions = model.fit_predict(features)
    scores = model.score_samples(features)
    df = df.loc[features.index].copy()
    df["anomaly"] = predictions == -1
    df["anomaly_score"] = scores
    anomaly_count = df["anomaly"].sum()
    log.info(f"Anomalies found: {anomaly_count} out of {len(df)} records")
    return df

def get_anomaly_summary(df):
    if df.empty:
        return {}
    return {
        "total_records": len(df),
        "anomaly_count": int(df["anomaly"].sum()),
        "anomaly_rate": round(df["anomaly"].mean() * 100, 2),
        "avg_temp": round(df["temperature"].mean(), 2),
        "max_temp": round(df["temperature"].max(), 2),
        "min_temp": round(df["temperature"].min(), 2),
    }