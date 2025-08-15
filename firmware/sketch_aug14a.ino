// ====== ESP32: 6x FSR → single HTTP POST (batch) ======
#include <WiFi.h>
#include <HTTPClient.h>

// --- Wi-Fi / Server ---
const char* WIFI_SSID     = "joun";      // <-- replace
const char* WIFI_PASSWORD = "qwertyasdf";  // <-- replace
const char* SERVER_URL    = "http://172.20.10.2:8000/ingest"; // <-- your FastAPI endpoint

// Sensor pin map (ADC1 preferred; GPIO15 is ADC2 fallback if GPIO35 is not available)
// ADC1: 36, 39, 34, 32, 33  |  ADC2: 15 (may be unstable with Wi-Fi)
const int SENSOR_PINS[6] = {36, 34, 39, 15, 33, 32};
const int NUM_SENSORS    = 6;

// Device ID (server will store as device_id and expand values[] to device_id-chN)
const char* BASE_DEVICE_ID = "fsr-node-01";

// Non-blocking loop timing (batch rate)
const uint32_t SAMPLE_INTERVAL_MS = 50;  // 20 Hz batch
uint32_t lastSampleMs = 0;

// Small pause after reading ADC2 pins to mitigate Wi-Fi contention
inline void pauseAfterAdc2(int gpio) {
  if (gpio == 15) {          // ADC2_CH3 on most ESP32
    delay(10);               // tune 5~20 ms as needed
  }
}

void waitForWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("WiFi connecting");
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - t0) < 20000) {
    delay(250);
    Serial.print(".");
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("WiFi connected. IP=%s RSSI=%d dBm\n",
                  WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println("WiFi connect timeout");
  }
}

// Batch POST: {"device_id":"...","values":[v0,...,v5]}
bool postBatch(int values[], int n) {
  if (WiFi.status() != WL_CONNECTED) {
    waitForWiFi();
    if (WiFi.status() != WL_CONNECTED) return false;
  }

  // Build JSON payload
  String json;
  json.reserve(64 + n * 6);  // rough prealloc
  json += "{\"device_id\":\"";
  json += BASE_DEVICE_ID;
  json += "\",\"values\":[";

  for (int i = 0; i < n; ++i) {
    json += String(values[i]);
    if (i < n - 1) json += ",";
  }
  json += "]}";

  WiFiClient client;
  HTTPClient http;
  if (!http.begin(client, SERVER_URL)) {
    Serial.println("HTTP begin failed");
    return false;
  }

  http.addHeader("Content-Type", "application/json");
  int code = http.POST(json);
  if (code > 0) {
    Serial.printf("POST %d: %s\n", code, http.getString().c_str());
  } else {
    Serial.printf("POST failed: %s\n", http.errorToString(code).c_str());
  }
  http.end();
  return (code >= 200 && code < 300);
}

void setup() {
  Serial.begin(115200);
  delay(200);

  // ADC setup: 12-bit (0..4095), 11dB attenuation ≈ 0..3.3V
  analogReadResolution(12);
  for (int i = 0; i < NUM_SENSORS; ++i) {
    analogSetPinAttenuation(SENSOR_PINS[i], ADC_11db);
    pinMode(SENSOR_PINS[i], INPUT);  // note: 36/39/34 are input-only
  }

  waitForWiFi();
}

void loop() {
  uint32_t now = millis();
  if (now - lastSampleMs < SAMPLE_INTERVAL_MS) return;
  lastSampleMs = now;

  // Read all channels
  int values[NUM_SENSORS];
  for (int ch = 0; ch < NUM_SENSORS; ++ch) {
    int gpio = SENSOR_PINS[ch];
    values[ch] = analogRead(gpio);   // 0..4095 on ESP32 @ 12-bit
    pauseAfterAdc2(gpio);            // mitigate Wi-Fi contention for ADC2 pins (e.g., 15)
    delay(2);                        // tiny spacing between channels (optional)
  }

  // Send once per batch with simple retry/backoff
  const int maxRetry = 3;
  int retry = 0;
  bool ok = false;
  while (retry < maxRetry && !(ok = postBatch(values, NUM_SENSORS))) {
    ++retry;
    delay(200 * retry);              // 200ms, 400ms, 600ms
  }
  if (!ok) Serial.println("Batch send failed after retries.");
}
