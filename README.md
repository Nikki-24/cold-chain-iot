# Cold Chain IoT Monitoring Pipeline

## Use Case
A pharmacy storage fridge must stay between 2°C and 8°C at all times. This pipeline monitors temperature and humidity in real time using an ESP32 + DHT22 sensor, detects anomalies using Isolation Forest ML, and displays live telemetry on a Streamlit dashboard.

**Problem:** Cold chain failures cause medicine spoilage and food safety violations.
**Why this pipeline:** Manual monitoring misses short temperature spikes. Automated real-time monitoring catches issues immediately.
**Decisions enabled:** Alert staff when fridge goes out of safe range, identify faulty sensors, track historical trends.

## Architecture###
ESP32 + DHT22 → WiFi → MQTT Broker → Python Processor → InfluxDB → Streamlit Dashboard
(Mosquitto)         ↓                              ↓
Bad Data Log              Isolation Forest ML

 Why each component
- **ESP32**: Low cost, built-in WiFi, Arduino support, works with DHT22
- **DHT22**: Accurate temperature ±0.5°C and humidity ±2%, ideal for cold chain
- **MQTT**: Lightweight pub/sub protocol for IoT — low bandwidth, async, handles dropped connections
- **InfluxDB**: Time-series database built for sensor data — fast writes, powerful time queries
- **Streamlit**: Python dashboard with auto-refresh — live telemetry with minimal code
- **Isolation Forest**: Unsupervised ML anomaly detection — no labeled data needed

## Project Structure
cold_chain_iot/
├── src/
│   ├── processor.py      # MQTT subscriber, validator, InfluxDB writer
│   ├── ml_model.py       # Isolation Forest anomaly detection
│   └── dashboard.py      # Live Streamlit dashboard
├── config/
│   └── config.yaml       # All configuration settings
├── scripts/
└── README.md

## Database Schema

**Measurement:** sensor_data

| Type | Name | Description |
|------|------|-------------|
| Timestamp | _time | UTC timestamp of reading |
| Tag | device_id | Device identifier e.g. fridge_01 |
| Tag | location | Physical location e.g. pharmacy_storage |
| Field | temperature | Temperature in Celsius (float) |
| Field | humidity | Relative humidity percent (float) |
| Field | alert | True if outside safe range (boolean) |

Tags are indexed for fast filtering by device. Fields store measurements. Schema fits time-series workloads because all queries are time-bounded and filtered by device_id.

## Setup Steps

### 1. Clone the repository
```bash
git clone https://github.com/Nikki-24/cold-chain-iot.git
cd cold-chain-iot
```

### 2. Install Python dependencies
```bash
pip install paho-mqtt influxdb-client streamlit scikit-learn pandas plotly
```

### 3. Install and start Mosquitto
```bash
brew install mosquitto
brew services start mosquitto
```

### 4. Install and start InfluxDB
```bash
brew install influxdb@2
brew services start influxdb@2
```
Open http://localhost:8086 and set up:
- Organization: iot_project
- Bucket: cold_chain
- Copy the API token into config/config.yaml

### 5. Configure
Edit config/config.yaml and add your InfluxDB API token.

### 6. Flash the ESP32
Open cold_chain_esp32.ino in Arduino IDE and update:
```cpp
const char* ssid = "YOUR_WIFI_NAME";
const char* password = "YOUR_WIFI_PASSWORD";
const char* mqtt_server = "YOUR_LAPTOP_IP";
```
Find your laptop IP:
```bash
ipconfig getifaddr en0
```
Upload to ESP32 via Arduino IDE.

### 7. Run the pipeline

Terminal 1 — Start the processor:
```bash
cd cold_chain_iot
python src/processor.py
```

Terminal 2 — Start the dashboard:
```bash
cd cold_chain_iot
streamlit run src/dashboard.py
```

Open http://localhost:8501 to see the live dashboard.

## Sample InfluxDB Queries

Average temperature last hour:
```flux
from(bucket: "cold_chain")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "sensor_data")
  |> filter(fn: (r) => r._field == "temperature")
  |> mean()
```

Count alerts last 24 hours:
```flux
from(bucket: "cold_chain")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "sensor_data")
  |> filter(fn: (r) => r._field == "alert")
  |> filter(fn: (r) => r._value == true)
  |> count()
```

Max temperature per hour:
```flux
from(bucket: "cold_chain")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "sensor_data")
  |> filter(fn: (r) => r._field == "temperature")
  |> aggregateWindow(every: 1h, fn: max)
```

## ML — Isolation Forest Anomaly Detection
- **Input features**: temperature, humidity
- **Algorithm**: Isolation Forest (contamination=0.05, n_estimators=100)
- **Output**: anomaly flag True or False plus anomaly score per reading
- **How results are used**: Anomalies are highlighted red on the dashboard. Operators investigate flagged readings to determine if the fridge door was left open, sensor failed, or compressor is malfunctioning.

## Failure Scenarios Handled

| Scenario | How it is handled |
|----------|------------------|
| Null sensor value | Logged to bad_data.log, message skipped |
| Out of range temp less than -10 or greater than 60 | Rejected, logged, skipped |
| Out of range humidity less than 0 or greater than 100 | Rejected, logged, skipped |
| Duplicate message | Detected via message_count tracking, skipped |
| Sensor spike | Injected every 50 messages in ESP32 code |
| Sensor dropout | Injected every 40 messages in ESP32 code |
| Communication failure | MQTT auto-reconnect handles broker disconnection |

## Induced Failures in Device Code
The ESP32 code deliberately injects failures to demonstrate pipeline robustness:
- Every 50 messages → temperature spike 99.9°C
- Every 75 messages → out of range value -99.9°C
- Every 40 messages → sensor dropout message skipped
- Every 30 messages → duplicate message published twice

## Records
- Sampling interval: 10 seconds
- 10,000 records equals approximately 28 hours of runtime
- Leave ESP32 running overnight to collect records

## Scaling to Enterprise
For enterprise scale this design would require:
- MQTT broker cluster such as HiveMQ or AWS IoT Core instead of local Mosquitto
- Stream processing layer such as Apache Kafka between MQTT and storage
- InfluxDB Cloud or TimescaleDB on managed infrastructure
- Containerization with Docker and Kubernetes
- CI/CD pipeline for automated testing and deployment
- Role-based access control on the dashboard