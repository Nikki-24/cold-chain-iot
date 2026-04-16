import json
import logging
import yaml
import time
from datetime import datetime
from pathlib import Path
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

config_path = Path(__file__).parent.parent / "config" / "config.yaml"
with open(config_path) as f:
    config = yaml.safe_load(f)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("pipeline.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

bad_log = logging.getLogger("bad_data")
bad_handler = logging.FileHandler("bad_data.log")
bad_log.addHandler(bad_handler)
bad_log.setLevel(logging.WARNING)

influx_client = InfluxDBClient(
    url=config["influxdb"]["url"],
    token=config["influxdb"]["token"],
    org=config["influxdb"]["org"]
)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)

seen_messages = set()
record_count = 0

def validate(data):
    temp = data.get("temperature")
    humidity = data.get("humidity")
    if temp is None or humidity is None:
        return False, "null_value"
    try:
        temp = float(temp)
        humidity = float(humidity)
    except (ValueError, TypeError):
        return False, "malformed_value"
    if temp < config["thresholds"]["temp_min"] or temp > config["thresholds"]["temp_max"]:
        return False, f"out_of_range_temp:{temp}"
    if humidity < config["thresholds"]["humidity_min"] or humidity > config["thresholds"]["humidity_max"]:
        return False, f"out_of_range_humidity:{humidity}"
    return True, "ok"

def is_duplicate(data):
    msg_id = data.get("message_count")
    if msg_id in seen_messages:
        return True
    seen_messages.add(msg_id)
    return False

def enrich(data):
    temp = float(data["temperature"])
    data["alert"] = (
        temp < config["thresholds"]["temp_alert_low"] or
        temp > config["thresholds"]["temp_alert_high"]
    )
    data["processed_at"] = datetime.utcnow().isoformat()
    data["location"] = config["device"]["location"]
    return data

def write_to_influx(data):
    point = (
        Point("sensor_data")
        .tag("device_id", data.get("device_id", "unknown"))
        .tag("location", data.get("location", "unknown"))
        .field("temperature", float(data["temperature"]))
        .field("humidity", float(data["humidity"]))
        .field("alert", bool(data["alert"]))
        .time(datetime.utcnow(), WritePrecision.NS)
    )
    write_api.write(
        bucket=config["influxdb"]["bucket"],
        org=config["influxdb"]["org"],
        record=point
    )

def on_message(client, userdata, msg):
    global record_count
    try:
        raw = msg.payload.decode("utf-8")
        data = json.loads(raw)
        log.info(f"Received: {data}")
        if is_duplicate(data):
            bad_log.warning(f"DUPLICATE: {data}")
            log.warning("Duplicate message detected — skipping")
            return
        valid, reason = validate(data)
        if not valid:
            bad_log.warning(f"BAD_DATA [{reason}]: {data}")
            log.warning(f"Bad data [{reason}] — skipping")
            return
        data = enrich(data)
        write_to_influx(data)
        record_count += 1
        log.info(f"Written to InfluxDB — Total records: {record_count}")
    except Exception as e:
        log.error(f"Error processing message: {e}")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        log.info("Connected to MQTT broker")
        client.subscribe(config["mqtt"]["topic"])
        log.info(f"Subscribed to: {config['mqtt']['topic']}")