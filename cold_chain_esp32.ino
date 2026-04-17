#include <WiFi.h>
#include <PubSubClient.h>
#include <DHT.h>
#include <ArduinoJson.h>

// WiFi credentials - change these to your home WiFi
const char* ssid = "Dum dum";
const char* password = "Comcast@2024";
const char* mqtt_server = "10.0.0.119";

// MQTT broker - your laptop's IP address
const int mqtt_port = 1883;
const char* mqtt_topic = "fridge/sensor";
const char* device_id = "fridge_01";

// DHT22 sensor
#define DHTPIN 4
#define DHTTYPE DHT22
DHT dht(DHTPIN, DHTTYPE);

WiFiClient espClient;
PubSubClient client(espClient);

int messageCount = 0;

void setup_wifi() {
  Serial.println("Connecting to WiFi...");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi connected!");
  Serial.print("IP address: ");
  Serial.println(WiFi.localIP());
}

void reconnect_mqtt() {
  while (!client.connected()) {
    Serial.print("Connecting to MQTT...");
    if (client.connect(device_id)) {
      Serial.println("connected!");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" retrying in 5 seconds");
      delay(5000);
    }
  }
}

float injectFailure(float value, int count) {
  // Spike every 50 messages
  if (count % 50 == 0) {
    Serial.println("INJECTING: temperature spike");
    return 99.9;
  }
  // Out of range every 75 messages
  if (count % 75 == 0) {
    Serial.println("INJECTING: out of range value");
    return -99.9;
  }
  return value;
}

void loop() {
  if (!client.connected()) {
    reconnect_mqtt();
  }
  client.loop();

  float temperature = dht.readTemperature();
  float humidity = dht.readHumidity();

  messageCount++;

  // Inject duplicate message every 30 messages
  bool isDuplicate = (messageCount % 30 == 0);

  // Inject null/dropout every 40 messages
  bool isDropout = (messageCount % 40 == 0);

  if (isDropout) {
    Serial.println("INJECTING: sensor dropout - skipping message");
    delay(10000);
    return;
  }

  // Inject spike failure
  temperature = injectFailure(temperature, messageCount);

  // Build JSON payload
  StaticJsonDocument<200> doc;
  doc["device_id"] = device_id;
  if (isnan(temperature)) { doc["temperature"] = (char*)nullptr; } else { doc["temperature"] = temperature; }
 if (isnan(humidity)) { doc["humidity"] = (char*)nullptr; } else { doc["humidity"] = humidity; }
  doc["message_count"] = messageCount;
  doc["is_duplicate"] = isDuplicate;
  doc["timestamp"] = millis();

  char payload[200];
  serializeJson(doc, payload);

  // Publish to MQTT
  client.publish(mqtt_topic, payload);
  Serial.print("Published: ");
  Serial.println(payload);

  // If duplicate, publish again immediately
  if (isDuplicate) {
    Serial.println("INJECTING: duplicate message");
    client.publish(mqtt_topic, payload);
  }

  delay(10000); // Send every 10 seconds
}

void setup() {
  Serial.begin(115200);
  dht.begin();
  setup_wifi();
  client.setServer(mqtt_server, mqtt_port);
  Serial.println("Cold Chain Monitor Started");
  Serial.print("Device ID: ");
  Serial.println(device_id);
}