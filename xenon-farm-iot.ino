#include "Particle.h"

// Keep using Particle's standard **Servo** library (add it under Libraries in Build / Workbench).
// Avoid `#include <Servo.h>` here — many Particle CLI/Xcode layouts don't put that header on the include path.

SYSTEM_MODE(MANUAL);

// ==========================================
// PIN DEFINITIONS
// ==========================================
const int RELAY_PIN = D2;   // Cooling: LOW = relay energized (AC on), HIGH = off (matches prior sketch).
const int SERVO_PIN = A0;   // Window: servo angle maps open/closed.

Servo myServo;

// Last commanded state (for logging).
bool lastWindowOpen = false;
bool lastCoolingOn = false;

// ==========================================
// BLE CONFIGURATION (Peripheral)
// ==========================================
const BleUuid xenonServiceUuid("b4250400-fb4b-4746-b2b0-93f0e61122c6");
const BleUuid actuatorCharUuid("b4250401-fb4b-4746-b2b0-93f0e61122c6");

void onDataReceived(const uint8_t* data, size_t len, const BlePeerDevice& peer, void* context);

// Payload from Argon: byte0 = window (1 open), byte1 = cooling (1 on). Buffer sized > payload for BLE stacks.
BleCharacteristic actuatorCharacteristic(
    "Actuator",
    BleCharacteristicProperty::WRITE,
    actuatorCharUuid,
    8,
    onDataReceived,
    NULL);

// ==========================================
// LOGGING (USB + Serial1 / FTDI)
// ==========================================
void logMessage(String msg) {
    Serial.println(msg);
    Serial1.println(msg);
}

static void applyActuators(bool windowOpen, bool coolingOn) {
    // Cooling relay
    digitalWrite(RELAY_PIN, coolingOn ? LOW : HIGH);
    // Window servo (tune angles if your linkage differs)
    myServo.write(windowOpen ? 90 : 0);

    if (windowOpen != lastWindowOpen || coolingOn != lastCoolingOn) {
        lastWindowOpen = windowOpen;
        lastCoolingOn = coolingOn;
        char buf[80];
        snprintf(
            buf,
            sizeof(buf),
            "Actuators -> window %s | cooling %s",
            windowOpen ? "OPEN" : "CLOSED",
            coolingOn ? "ON" : "OFF");
        logMessage(String(buf));
    }
}

// ==========================================
// SETUP
// ==========================================
void setup() {
    Serial.begin(115200);
    Serial1.begin(115200);

    waitFor(Serial.isConnected, 3000);

    pinMode(RELAY_PIN, OUTPUT);
    digitalWrite(RELAY_PIN, HIGH); // cooling OFF

    myServo.attach(SERVO_PIN);
    applyActuators(false, false);

    BLE.on();
    actuatorCharacteristic.onDataReceived(onDataReceived, NULL);
    BLE.addCharacteristic(actuatorCharacteristic);

    BleAdvertisingData advData;
    advData.appendServiceUUID(xenonServiceUuid);
    BLE.advertise(&advData);

    logMessage("Xenon actuator node started. BLE actuator writes: 2 bytes [window][cooling], or legacy 1 byte.");
}

// ==========================================
// LOOP
// ==========================================
void loop() {
    static unsigned long lastHeartbeat = 0;
    if (millis() - lastHeartbeat >= 5000) {
        lastHeartbeat = millis();
        logMessage("Xenon alive. Waiting for BLE commands from Argon...");
    }
}

// ==========================================
// BLE CALLBACK
// ==========================================
void onDataReceived(const uint8_t* data, size_t len, const BlePeerDevice& peer, void* context) {
    if (len == 0) {
        return;
    }

    bool windowCmd;
    bool coolingCmd;

    if (len >= 2) {
        // Current protocol: byte0 = window (1 = open), byte1 = cooling (1 = on).
        windowCmd = (data[0] != 0);
        coolingCmd = (data[1] != 0);
    } else {
        // Legacy single-byte alarm command: 1 = both on, 0 = both off.
        uint8_t command = data[0];
        windowCmd = (command != 0);
        coolingCmd = (command != 0);
        logMessage("Legacy 1-byte actuator command received → applying both equally.");
    }

    applyActuators(windowCmd, coolingCmd);
}
