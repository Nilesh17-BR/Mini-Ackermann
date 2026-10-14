#include <Arduino.h>
#include <Wire.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

// STM32duino 3.x Black Pill: USART1 PA9=TX, PA10=RX.
#define ControlSerial Serial1
#define DAC_SDA PB7
#define DAC_SCL PB6

constexpr uint8_t DAC_ADDRESS = 0x60;    // MCP4728 factory default; may differ
constexpr float DAC_VDD = 5.0f;          // Measure actual DAC supply
constexpr float DAC_LIMIT = 5.0f;
constexpr unsigned long BAUD = 115200;
constexpr unsigned long WATCHDOG_MS = 500;

constexpr float MAX_ALLOWED_VELOCITY = 100.0f;

uint8_t selectedChannel = 0;
float velocityMin = -5.0f, velocityMax = 5.0f;
float voltageMin = 0.0f, voltageMax = 5.0f;
bool configured = false;
bool dacReady = false;
bool timedOut = true;
unsigned long lastCommandMs = 0;
char line[96];
size_t used = 0;
bool discardLine = false;

uint16_t voltageToCode(float volts) {
  volts = constrain(volts, 0.0f, DAC_VDD);
  float scaled = volts * 4096.0f / DAC_VDD;
  if (scaled >= 4095.0f) return 4095;
  return (uint16_t)(scaled + 0.5f);
}

// MCP4728 multi-write, VREF=VDD, normal mode, gain 1, volatile only.
// LDAC must be tied LOW for immediate output changes.
bool writeChannel(uint8_t ch, float volts) {
  if (ch > 3) return false;
  uint16_t code = voltageToCode(volts);
  Wire.beginTransmission(DAC_ADDRESS);
  Wire.write((uint8_t)(0x40 | (ch << 1))); // Multi-write command, channel
  Wire.write((uint8_t)((code >> 8) & 0x0F)); // VREF=0, PD=00, GAIN=0
  Wire.write((uint8_t)(code & 0xFF));
  return Wire.endTransmission() == 0;
}

float velocityToVoltage(float velocity) {
  velocity = constrain(velocity, velocityMin, velocityMax);
  return voltageMin + (velocity - velocityMin) *
         (voltageMax - voltageMin) / (velocityMax - velocityMin);
}

float neutralVoltage() { return velocityToVoltage(0.0f); }

bool writeAll(float volts) {
  bool ok = true;
  for (uint8_t ch = 0; ch < 4; ++ch) {
    if (!writeChannel(ch, volts)) ok = false;
  }
  if (!ok) dacReady = false;
  return ok;
}

bool stopOutputs() {
  // Only valid once configured; otherwise neutral is unknown.
  return writeAll(configured ? neutralVoltage() : 0.0f);
}

bool parseFloats(const char *s, float *v, uint8_t count) {
  const char *p = s;
  for (uint8_t i = 0; i < count; ++i) {
    char *end = nullptr;
    v[i] = strtod(p, &end);
    if (end == p || !isfinite(v[i])) return false;
    p = end;
    if (i + 1 < count) {
      if (*p != ',') return false;
      ++p;
    }
  }
  return *p == '\0';
}

void processChannel(const char *data) {
  if (strlen(data) != 1 || data[0] < '0' || data[0] > '3') {
    ControlSerial.println("ERR:INVALID_CHANNEL");
    return;
  }
  if (!stopOutputs()) {
    configured = false;
    timedOut = true;
    ControlSerial.println("ERR:DAC_WRITE_FAILED");
    return;
  }
  selectedChannel = (uint8_t)(data[0] - '0');
  timedOut = true;
  ControlSerial.print("OK:CH:");
  ControlSerial.println(selectedChannel);
}

void processMap(const char *data) {
  float v[4];
  if (!parseFloats(data, v, 4)) {
    ControlSerial.println("ERR:BAD_MAP_FORMAT");
    return;
  }
  // Range must include 0 m/s so that STOP has a defined neutral voltage.
  if (v[0] < -MAX_ALLOWED_VELOCITY || v[0] > 0.0f || v[1] < 0.0f ||
      v[1] > MAX_ALLOWED_VELOCITY || v[1] <= v[0] ||
      v[2] < 0.0f || v[3] > DAC_LIMIT || v[3] <= v[2]) {
    ControlSerial.println("ERR:INVALID_MAP");
    return;
  }
  // Compute new neutral independently of previous configuration.
  const float nextNeutral = v[2] + (0.0f - v[0]) *
                            (v[3] - v[2]) / (v[1] - v[0]);
  timedOut = true;
  // CAUTION: mapping transitions require downstream drive to be disabled.
  if (!writeAll(nextNeutral)) {
    configured = false;
    ControlSerial.println("ERR:DAC_WRITE_FAILED");
    return;
  }
  velocityMin = v[0]; velocityMax = v[1];
  voltageMin = v[2]; voltageMax = v[3];
  configured = true;
  dacReady = true;
  ControlSerial.print("OK:MAP:");
  for (uint8_t i = 0; i < 4; ++i) {
    if (i) ControlSerial.print(',');
    ControlSerial.print(v[i], 3);
  }
  ControlSerial.println();
}

void processVelocity(const char *data) {
  if (!configured || !dacReady) {
    ControlSerial.println("ERR:NOT_CONFIGURED");
    return;
  }
  float input[1];
  if (!parseFloats(data, input, 1)) {
    stopOutputs();
    timedOut = true;
    ControlSerial.println("ERR:BAD_VELOCITY");
    return;
  }
  float velocity = constrain(input[0], velocityMin, velocityMax);
  float volts = velocityToVoltage(velocity);
  if (!writeChannel(selectedChannel, volts)) {
    stopOutputs();
    timedOut = true;
    configured = false;
    ControlSerial.println("ERR:DAC_WRITE_FAILED");
    return;
  }
  lastCommandMs = millis();
  timedOut = false;
  ControlSerial.print("OK:CMD:");
  ControlSerial.print(velocity, 3);
  ControlSerial.print(",CH:");
  ControlSerial.print(selectedChannel);
  ControlSerial.print(",VL:");
  ControlSerial.println(volts, 3);
}

void processLine(const char *cmd) {
  if (strcmp(cmd, "PING") == 0) ControlSerial.println("PONG");
  else if (strcmp(cmd, "STATUS") == 0) {
    ControlSerial.print("STATUS:CH:"); ControlSerial.print(selectedChannel);
    ControlSerial.print(",DAC:"); ControlSerial.print(dacReady ? 1 : 0);
    ControlSerial.print(",CONFIG:"); ControlSerial.print(configured ? 1 : 0);
    ControlSerial.print(",NEUTRAL:");
    ControlSerial.println(configured ? neutralVoltage() : 0.0f, 3);
  }
  else if (strncmp(cmd, "CH:", 3) == 0) processChannel(cmd + 3);
  else if (strncmp(cmd, "MAP:", 4) == 0) processMap(cmd + 4);
  else if (strncmp(cmd, "CMD:", 4) == 0) processVelocity(cmd + 4);
  else if (strcmp(cmd, "STOP") == 0) {
    timedOut = true;
    ControlSerial.println(stopOutputs() ? "OK:STOP" : "ERR:DAC_WRITE_FAILED");
  }
  else if (*cmd) ControlSerial.println("ERR:UNKNOWN_COMMAND");
}

void setup() {
  ControlSerial.begin(BAUD);
  Wire.setSDA(DAC_SDA);
  Wire.setSCL(DAC_SCL);
  Wire.begin();
  Wire.setClock(100000UL);
  delay(100);
  // Neutral cannot be known until valid MAP is received.
  dacReady = writeAll(0.0f);
  ControlSerial.println(dacReady ? "DAC_INITIALIZED" : "ERR:DAC_NOT_FOUND");
  ControlSerial.println("BLACKPILL_READY");
}

void loop() {
  while (ControlSerial.available()) {
    char c = (char)ControlSerial.read();
    if (c == '\n') {
      if (!discardLine) {
        line[used] = '\0';
        processLine(line);
      }
      used = 0;
      discardLine = false;
    } else if (c != '\r' && !discardLine) {
      if (used < sizeof(line) - 1) line[used++] = c;
      else {
        used = 0;
        discardLine = true;
        ControlSerial.println("ERR:LINE_TOO_LONG");
      }
    }
  }
  if (configured && !timedOut &&
      (unsigned long)(millis() - lastCommandMs) > WATCHDOG_MS) {
    bool ok = stopOutputs();
    timedOut = true;
    if (!ok) ControlSerial.println("ERR:DAC_WRITE_FAILED");
    ControlSerial.println("WARN:SERIAL_TIMEOUT");
  }
}