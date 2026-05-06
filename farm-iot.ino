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
// VARIABLES & TIMERS
// ==========================================
double temperature = 0.0;
double humidity = 0.0;
int smokeLevel = 0;

bool alarmActive = false;
bool previousAlarmState = false; // NEW: Tracks the last state we sent
bool forceBleUpdate = true;      // NEW: Forces an update when we first connect

const int SMOKE_THRESHOLD = 2500; 

unsigned long lastReadTime = 0;
unsigned long lastPublishTime = 0;
const unsigned long READ_INTERVAL = 5000;    
const unsigned long PUBLISH_INTERVAL = 30000; 

// ==========================================
// BLE CONFIGURATION (Central Role)
// ==========================================
const BleUuid xenonServiceUuid("b4250400-fb4b-4746-b2b0-93f0e61122c6");
const BleUuid actuatorCharUuid("b4250401-fb4b-4746-b2b0-93f0e61122c6");

BlePeerDevice xenonPeer;
BleCharacteristic actuatorCharacteristic;
bool connectedToXenon = false;

void setup() {
    Serial.begin(115200);
    
    pinMode(SMOKE_PIN, INPUT);
    pinMode(BUZZER_PIN, OUTPUT);
    digitalWrite(BUZZER_PIN, LOW);

    Particle.variable("Temperature", temperature);
    Particle.variable("Humidity", humidity);
    Particle.variable("SmokeLevel", smokeLevel);
    Particle.variable("Alarm", alarmActive);

    BLE.on();
    Serial.println("Argon Gateway Started. Scanning for Xenon...");
}

void loop() {
    unsigned long currentMillis = millis();

    // 1. MANAGE BLE CONNECTION ---------------------------------------
    if (!xenonPeer.connected()) {
        connectedToXenon = false;
        
        BleScanResult scanResults[20];
        int count = BLE.scan(scanResults, 20);
        
        for (int i = 0; i < count; i++) {
            BleUuid foundUuids[4];
            
            // FIX 1: Added () to advertisingData
            // To this (removed the 's' at the end):
            size_t uuidCount = scanResults[i].advertisingData().serviceUUID(foundUuids, 4);
            
            bool foundXenon = false;
            for (size_t j = 0; j < uuidCount; j++) {
                if (foundUuids[j] == xenonServiceUuid) {
                    foundXenon = true;
                    break;
                }
            }

            if (foundXenon) {
                // FIX 2: Added () to address
                xenonPeer = BLE.connect(scanResults[i].address());
                
                if (xenonPeer.connected()) {
                    xenonPeer.getCharacteristicByUUID(actuatorCharacteristic, actuatorCharUuid);
                    connectedToXenon = true;
                    forceBleUpdate = true; // Force it to sync state immediately on connection
                    Serial.println("Successfully connected to Xenon via BLE!");
                    break; 
                }
            }
        }
    }

    // 2. READ SENSORS (Every 5 Seconds) ------------------------------
    if (currentMillis - lastReadTime >= READ_INTERVAL) {
        lastReadTime = currentMillis;

        int result = dht.acquireAndWait(1000); 
        if (result == DHTLIB_OK) {
            temperature = dht.getCelsius();
            humidity = dht.getHumidity();
        }

        smokeLevel = analogRead(SMOKE_PIN);
        
        // Safety Logic: Evaluate Smoke
        if (smokeLevel > SMOKE_THRESHOLD) {
            alarmActive = true;
            digitalWrite(BUZZER_PIN, HIGH); // Sound local buzzer
        } else {
            alarmActive = false;
            digitalWrite(BUZZER_PIN, LOW); // Silence buzzer
        }

        // NEW: ONLY send BLE command if the alarm state CHANGED (or if we just connected)
        if (connectedToXenon && (alarmActive != previousAlarmState || forceBleUpdate)) {
            uint8_t command = alarmActive ? 1 : 0;
            actuatorCharacteristic.setValue(&command, 1);
            
            previousAlarmState = alarmActive; // Remember what we just sent
            forceBleUpdate = false;           // Turn off the force flag
        }

        Serial.printf("Temp: %.1f C | Hum: %.1f %% | Smoke: %d | Alarm: %s\n", 
                      temperature, humidity, smokeLevel, alarmActive ? "ON" : "OFF");
    }

    // 3. PUBLISH TO PARTICLE CLOUD (Every 30 Seconds) ----------------
    if (currentMillis - lastPublishTime >= PUBLISH_INTERVAL) {
        lastPublishTime = currentMillis;
        char payload[128];
        snprintf(payload, sizeof(payload), "{\"temp\":%.1f, \"hum\":%.1f, \"smoke\":%d, \"alarm\":%d}", 
                 temperature, humidity, smokeLevel, alarmActive);

        Particle.publish("environmental_data", payload, PRIVATE);
    }
}