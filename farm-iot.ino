#include "Particle.h"
#include "PietteTech_DHT.h"

// ==========================================
// PIN DEFINITIONS
// ==========================================
#define DHTPIN D2
#define DHTTYPE DHT11
#define SMOKE_PIN A0
#define BUZZER_PIN D4

PietteTech_DHT dht(DHTPIN, DHTTYPE);

// ==========================================
// CLIMATE / SAFETY THRESHOLDS
// ==========================================
const int SMOKE_THRESHOLD = 2500;

// When smoke is clear: passive ventilation above TEMP_WINDOW_OPEN_C; AC above TEMP_COOLING_ON_C
// with window closed (no open-window + cooling at the same time).
const double TEMP_WINDOW_OPEN_C = 26.0;
const double TEMP_COOLING_ON_C = 27.0;

// ==========================================
// SENSOR VALUES (cloud variables)
// ==========================================
double temperature = 0.0;
double humidity = 0.0;
int smokeLevel = 0;

// Smoke alarm drives buzzer on Argon; BLE mirrors window + cooling (never both on when cooling runs).
bool alarmActive = false;

// Actuator commands mirrored on Xenon (servo = window, relay = cooling).
// Use int for Particle.variable compatibility with Cloud API polling.
int windowOpen = 0;
int coolingOn = 0;

unsigned long lastReadTime = 0;
unsigned long lastPublishTime = 0;
const unsigned long READ_INTERVAL = 5000;
const unsigned long PUBLISH_INTERVAL = 30000;

// ==========================================
// BLE CONFIGURATION (Central → Xenon peripheral)
// ==========================================
const BleUuid xenonServiceUuid("b4250400-fb4b-4746-b2b0-93f0e61122c6");
const BleUuid actuatorCharUuid("b4250401-fb4b-4746-b2b0-93f0e61122c6");

BlePeerDevice xenonPeer;
BleCharacteristic actuatorCharacteristic;
bool connectedToXenon = false;

// Sync BLE whenever commands change or link comes up.
bool forceBleUpdate = true;
int lastBleWindow = -1;
int lastBleCooling = -1;

void setup() {
    Serial.begin(115200);

    pinMode(SMOKE_PIN, INPUT);
    pinMode(BUZZER_PIN, OUTPUT);
    digitalWrite(BUZZER_PIN, LOW);

    Particle.variable("Temperature", temperature);
    Particle.variable("Humidity", humidity);
    Particle.variable("SmokeLevel", smokeLevel);
    Particle.variable("Alarm", alarmActive);

    // Dashboard / Flask poller read these (see modules/config.py aliases).
    Particle.variable("WindowOpen", windowOpen);
    Particle.variable("CoolingOn", coolingOn);

    BLE.on();
    Serial.println("Argon gateway started. Scanning for Xenon...");
}

void loop() {
    unsigned long currentMillis = millis();

    // 1. BLE CONNECTION -------------------------------------------------
    if (!xenonPeer.connected()) {
        connectedToXenon = false;
        lastBleWindow = -1;
        lastBleCooling = -1;

        BleScanResult scanResults[20];
        int count = BLE.scan(scanResults, 20);

        for (int i = 0; i < count; i++) {
            BleUuid foundUuids[4];
            size_t uuidCount = scanResults[i].advertisingData().serviceUUID(foundUuids, 4);

            bool foundXenon = false;
            for (size_t j = 0; j < uuidCount; j++) {
                if (foundUuids[j] == xenonServiceUuid) {
                    foundXenon = true;
                    break;
                }
            }

            if (foundXenon) {
                xenonPeer = BLE.connect(scanResults[i].address());

                if (xenonPeer.connected()) {
                    xenonPeer.getCharacteristicByUUID(actuatorCharacteristic, actuatorCharUuid);
                    connectedToXenon = true;
                    forceBleUpdate = true;
                    Serial.println("Connected to Xenon via BLE.");
                    break;
                }
            }
        }
    }

    // 2. SENSORS + ACTUATOR COMMAND STATE ------------------------------
    if (currentMillis - lastReadTime >= READ_INTERVAL) {
        lastReadTime = currentMillis;

        bool dhtOk = false;
        int dhtResult = dht.acquireAndWait(1000);
        if (dhtResult == DHTLIB_OK) {
            temperature = dht.getCelsius();
            humidity = dht.getHumidity();
            dhtOk = true;
        }

        smokeLevel = analogRead(SMOKE_PIN);

        bool smokeAlarm = (smokeLevel > SMOKE_THRESHOLD);

        if (smokeAlarm) {
            alarmActive = true;
            digitalWrite(BUZZER_PIN, HIGH);
            // Ventilate; keep cooling off while window is open / clearing smoke.
            windowOpen = 1;
            coolingOn = 0;
        } else {
            alarmActive = false;
            digitalWrite(BUZZER_PIN, LOW);

            if (dhtOk) {
                // AC has priority when hot: cooling on ⇒ window must stay closed.
                if (temperature > TEMP_COOLING_ON_C) {
                    coolingOn = 1;
                    windowOpen = 0;
                } else if (temperature > TEMP_WINDOW_OPEN_C) {
                    coolingOn = 0;
                    windowOpen = 1;
                } else {
                    coolingOn = 0;
                    windowOpen = 0;
                }
            } else {
                windowOpen = 0;
                coolingOn = 0;
            }
        }

        // Invariant: never command cooling with an open window.
        if (coolingOn) {
            windowOpen = 0;
        }

        // Push state to Xenon (byte0 = window 0/1, byte1 = cooling 0/1).
        if (connectedToXenon &&
            (windowOpen != lastBleWindow || coolingOn != lastBleCooling || forceBleUpdate)) {
            uint8_t pkt[2] = { static_cast<uint8_t>(windowOpen), static_cast<uint8_t>(coolingOn) };
            actuatorCharacteristic.setValue(pkt, 2);
            lastBleWindow = windowOpen;
            lastBleCooling = coolingOn;
            forceBleUpdate = false;
        }

        Serial.printf(
            "Temp: %.1f C | Hum: %.1f %% | Smoke: %d | Alarm: %s | Window: %s | Cooling: %s\n",
            temperature,
            humidity,
            smokeLevel,
            alarmActive ? "ON" : "OFF",
            windowOpen ? "OPEN" : "CLOSED",
            coolingOn ? "ON" : "OFF");
    }

    // 3. CLOUD EVENT (optional; dashboard uses Particle.variable from this device)
    if (currentMillis - lastPublishTime >= PUBLISH_INTERVAL) {
        lastPublishTime = currentMillis;
        char payload[160];
        snprintf(
            payload,
            sizeof(payload),
            "{\"temp\":%.1f,\"hum\":%.1f,\"smoke\":%d,\"alarm\":%d,\"window\":%d,\"cooling\":%d}",
            temperature,
            humidity,
            smokeLevel,
            alarmActive ? 1 : 0,
            windowOpen,
            coolingOn);

        Particle.publish("environmental_data", payload, PRIVATE);
    }
}
