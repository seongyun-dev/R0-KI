#include <Arduino.h>
#include <Wire.h>
#include <esp_arduino_version.h>
#include <esp_task_wdt.h>

// RO-KI wiring fixed in the hardware assembly guide.
constexpr uint8_t LEFT_RPWM = 25;
constexpr uint8_t LEFT_LPWM = 26;
constexpr uint8_t RIGHT_RPWM = 27;
constexpr uint8_t RIGHT_LPWM = 33;
constexpr uint8_t MOTOR_ENABLE = 13;

constexpr uint8_t LEFT_ENCODER_A = 34;
constexpr uint8_t LEFT_ENCODER_B = 35;
constexpr uint8_t RIGHT_ENCODER_A = 36;
constexpr uint8_t RIGHT_ENCODER_B = 39;
constexpr uint8_t BATTERY_ADC = 32;

constexpr uint8_t I2C_SDA = 21;
constexpr uint8_t I2C_SCL = 22;
// The installed servo PCA9685 has address jumpers set to 0x60.
// 0x70 is the PCA9685 ALLCALL address and must not be used as a device address.
constexpr uint8_t PCA9685_ADDRESS = 0x60;
constexpr uint8_t SERVO_CHANNEL = 0;
constexpr uint8_t PCA_MODE1 = 0x00;
constexpr uint8_t PCA_MODE2 = 0x01;
constexpr uint8_t PCA_PRESCALE = 0xFE;
constexpr uint8_t PCA_ALL_LED_ON_L = 0xFA;
constexpr uint8_t PCA_ALL_LED_ON_H = 0xFB;
constexpr uint8_t PCA_ALL_LED_OFF_L = 0xFC;
constexpr uint8_t PCA_ALL_LED_OFF_H = 0xFD;

constexpr uint8_t LINE_PINS[5] = {16, 17, 18, 19, 23};
constexpr uint8_t LINE_SENSOR_COUNT =
  sizeof(LINE_PINS) / sizeof(LINE_PINS[0]);

constexpr uint32_t SERIAL_BAUD = 115200;
constexpr uint32_t PWM_FREQUENCY_HZ = 20000;
constexpr uint8_t PWM_RESOLUTION_BITS = 8;
constexpr uint16_t PWM_MAX = (1U << PWM_RESOLUTION_BITS) - 1U;

constexpr uint8_t MAX_TEST_SPEED_PERCENT = 25;
constexpr uint16_t MIN_TEST_PULSE_MS = 50;
constexpr uint16_t MAX_TEST_PULSE_MS = 500;
constexpr uint32_t ARM_WINDOW_MS = 5000;
constexpr uint8_t MAX_DRIVE_SPEED_PERCENT = 20;
constexpr uint32_t DRIVE_WATCHDOG_MS = 400;
constexpr uint32_t ODOMETRY_INTERVAL_MS = 100;
constexpr uint32_t HARDWARE_STATUS_INTERVAL_MS = 100;
constexpr uint16_t MAX_SERIAL_BYTES_PER_LOOP = 128;
constexpr uint8_t MAX_COMMANDS_PER_LOOP = 1;
constexpr uint32_t MAX_COMMAND_SEQUENCE = 2147483647UL;

constexpr uint8_t CONTROL_STEERING_MIN_ANGLE = 40;
constexpr uint8_t CONTROL_STEERING_MAX_ANGLE = 120;
constexpr uint8_t SERVO_MIN_TEST_ANGLE = 60;
constexpr uint8_t SERVO_MAX_TEST_ANGLE = 100;
constexpr uint8_t SERVO_CENTER_ANGLE = 80;
constexpr uint16_t SERVO_AUTO_OFF_MS = 3000;

constexpr float BATTERY_DIVIDER_RATIO = 5.0F;

enum class MotorStatus {
  NORMAL,
  FAULT,
  DISCONNECTED,
};

enum class LineSensorStatus {
  NORMAL,
  FAULT,
  DISCONNECTED,
};

volatile int32_t leftEncoderTicks = 0;
volatile int32_t rightEncoderTicks = 0;
portMUX_TYPE encoderMux = portMUX_INITIALIZER_UNLOCKED;

bool motorArmed = false;
bool servoArmed = false;
bool pcaDetected = false;
uint32_t motorArmDeadline = 0;
uint32_t servoArmDeadline = 0;
uint32_t motorStopDeadline = 0;
uint32_t servoOffDeadline = 0;
bool motorPulseActive = false;
bool servoPulseActive = false;
bool driveActive = false;
bool operatingControlActive = false;
char driveDirection = 'S';
uint32_t driveWatchdogDeadline = 0;
int16_t operatingLeftPwm = 0;
int16_t operatingRightPwm = 0;
uint8_t operatingServoAngle = SERVO_CENTER_ANGLE;
bool operatingServoApplied = false;
uint32_t odometrySequence = 0;
uint32_t lastCommandSequence = 0;
bool commandSequenceInitialized = false;
uint32_t nextOdometryDeadline = 0;
uint32_t nextHardwareStatusDeadline = 0;
String stopReason = "BOOT";
String faultCode = "NONE";

String commandBuffer;

void IRAM_ATTR onLeftEncoderA() {
  const int delta = digitalRead(LEFT_ENCODER_B) ? 1 : -1;
  portENTER_CRITICAL_ISR(&encoderMux);
  leftEncoderTicks += delta;
  portEXIT_CRITICAL_ISR(&encoderMux);
}

void IRAM_ATTR onRightEncoderA() {
  const int delta = digitalRead(RIGHT_ENCODER_B) ? 1 : -1;
  portENTER_CRITICAL_ISR(&encoderMux);
  rightEncoderTicks += delta;
  portEXIT_CRITICAL_ISR(&encoderMux);
}

void writeMotorPwm(uint8_t pin, uint8_t duty) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(pin, duty);
#else
  if (pin == LEFT_RPWM) ledcWrite(0, duty);
  if (pin == LEFT_LPWM) ledcWrite(1, duty);
  if (pin == RIGHT_RPWM) ledcWrite(2, duty);
  if (pin == RIGHT_LPWM) ledcWrite(3, duty);
#endif
}

void attachMotorPwm() {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(LEFT_RPWM, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  ledcAttach(LEFT_LPWM, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  ledcAttach(RIGHT_RPWM, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  ledcAttach(RIGHT_LPWM, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
#else
  ledcSetup(0, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  ledcSetup(1, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  ledcSetup(2, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  ledcSetup(3, PWM_FREQUENCY_HZ, PWM_RESOLUTION_BITS);
  ledcAttachPin(LEFT_RPWM, 0);
  ledcAttachPin(LEFT_LPWM, 1);
  ledcAttachPin(RIGHT_RPWM, 2);
  ledcAttachPin(RIGHT_LPWM, 3);
#endif
}

void zeroMotorPwm() {
  writeMotorPwm(LEFT_RPWM, 0);
  writeMotorPwm(LEFT_LPWM, 0);
  writeMotorPwm(RIGHT_RPWM, 0);
  writeMotorPwm(RIGHT_LPWM, 0);
}

void stopMotors() {
  zeroMotorPwm();
  digitalWrite(MOTOR_ENABLE, LOW);
  motorPulseActive = false;
  driveActive = false;
  operatingControlActive = false;
  driveDirection = 'S';
  motorArmed = false;
  operatingLeftPwm = 0;
  operatingRightPwm = 0;
}

bool i2cWrite8(uint8_t address, uint8_t reg, uint8_t value) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool i2cRead8(uint8_t address, uint8_t reg, uint8_t &value) {
  Wire.beginTransmission(address);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(address, static_cast<uint8_t>(1)) != 1) return false;
  value = Wire.read();
  return true;
}

bool pcaWriteChannel(uint8_t channel, uint16_t onCount, uint16_t offCount) {
  if (channel > 15) return false;
  const uint8_t base = 0x06 + (4 * channel);
  Wire.beginTransmission(PCA9685_ADDRESS);
  Wire.write(base);
  Wire.write(onCount & 0xFF);
  Wire.write((onCount >> 8) & 0x0F);
  Wire.write(offCount & 0xFF);
  Wire.write((offCount >> 8) & 0x0F);
  return Wire.endTransmission() == 0;
}

bool pcaChannelOff(uint8_t channel) {
  if (channel > 15) return false;
  const uint8_t base = 0x06 + (4 * channel);
  Wire.beginTransmission(PCA9685_ADDRESS);
  Wire.write(base);
  Wire.write(0);
  Wire.write(0);
  Wire.write(0);
  Wire.write(0x10);  // full-off bit
  return Wire.endTransmission() == 0;
}

bool pcaSoftwareReset() {
  // PCA9685 software-reset general call: address 0x00, data 0x06.
  Wire.beginTransmission(0x00);
  Wire.write(0x06);
  const bool acknowledged = Wire.endTransmission() == 0;
  delay(5);
  return acknowledged;
}

bool initializePca9685() {
  Wire.beginTransmission(PCA9685_ADDRESS);
  if (Wire.endTransmission() != 0) return false;

  if (!pcaSoftwareReset()) return false;

  // Explicit known state: auto-increment, internal clock, sleep while
  // programming the prescaler, totem-pole outputs, and no group override.
  constexpr uint8_t prescale = 121;
  constexpr uint8_t mode1SleepAutoIncrement = 0x30;
  constexpr uint8_t mode1AwakeAutoIncrement = 0x20;
  constexpr uint8_t mode1RestartAutoIncrement = 0xA0;
  constexpr uint8_t mode2TotemPole = 0x04;

  if (!i2cWrite8(PCA9685_ADDRESS, PCA_MODE1, mode1SleepAutoIncrement)) return false;
  if (!i2cWrite8(PCA9685_ADDRESS, PCA_MODE2, mode2TotemPole)) return false;
  if (!i2cWrite8(PCA9685_ADDRESS, PCA_PRESCALE, prescale)) return false;
  if (!i2cWrite8(PCA9685_ADDRESS, PCA_ALL_LED_ON_L, 0)) return false;
  if (!i2cWrite8(PCA9685_ADDRESS, PCA_ALL_LED_ON_H, 0)) return false;
  if (!i2cWrite8(PCA9685_ADDRESS, PCA_ALL_LED_OFF_L, 0)) return false;
  if (!i2cWrite8(PCA9685_ADDRESS, PCA_ALL_LED_OFF_H, 0)) return false;
  if (!i2cWrite8(PCA9685_ADDRESS, PCA_MODE1, mode1AwakeAutoIncrement)) return false;
  delay(5);
  if (!i2cWrite8(PCA9685_ADDRESS, PCA_MODE1, mode1RestartAutoIncrement)) return false;

  return pcaChannelOff(SERVO_CHANNEL);
}

bool readPcaChannel(
  uint8_t channel,
  uint8_t &onLow,
  uint8_t &onHigh,
  uint8_t &offLow,
  uint8_t &offHigh
) {
  if (channel > 15) return false;
  const uint8_t base = 0x06 + (4 * channel);
  return
    i2cRead8(PCA9685_ADDRESS, base, onLow) &&
    i2cRead8(PCA9685_ADDRESS, base + 1, onHigh) &&
    i2cRead8(PCA9685_ADDRESS, base + 2, offLow) &&
    i2cRead8(PCA9685_ADDRESS, base + 3, offHigh);
}

void printPcaStatus() {
  uint8_t mode1 = 0;
  uint8_t mode2 = 0;
  uint8_t prescale = 0;
  uint8_t onLow = 0;
  uint8_t onHigh = 0;
  uint8_t offLow = 0;
  uint8_t offHigh = 0;
  const bool ok =
    i2cRead8(PCA9685_ADDRESS, PCA_MODE1, mode1) &&
    i2cRead8(PCA9685_ADDRESS, PCA_MODE2, mode2) &&
    i2cRead8(PCA9685_ADDRESS, PCA_PRESCALE, prescale) &&
    readPcaChannel(
      SERVO_CHANNEL,
      onLow,
      onHigh,
      offLow,
      offHigh
    );

  Serial.printf(
    "{\"type\":\"pcaStatus\",\"ok\":%s,\"address\":\"60\","
    "\"channel\":%u,\"mode1\":%u,\"mode2\":%u,\"prescale\":%u,"
    "\"onLow\":%u,\"onHigh\":%u,\"offLow\":%u,\"offHigh\":%u}\n",
    ok ? "true" : "false",
    SERVO_CHANNEL,
    mode1,
    mode2,
    prescale,
    onLow,
    onHigh,
    offLow,
    offHigh
  );
}

void servoOff() {
  if (pcaDetected) pcaChannelOff(SERVO_CHANNEL);
  operatingServoApplied = false;
  servoPulseActive = false;
  servoArmed = false;
}

uint16_t servoAngleToCount(uint8_t angle) {
  // Conservative standard-servo mapping: 500-2500 us in a 20 ms period.
  const uint32_t pulseUs = 500UL + (static_cast<uint32_t>(angle) * 2000UL / 180UL);
  return static_cast<uint16_t>((pulseUs * 4096UL) / 20000UL);
}

void emergencyStop() {
  stopMotors();
  servoOff();
  stopReason = "EMERGENCY_STOP";
}

bool deadlineReached(uint32_t deadline) {
  return static_cast<int32_t>(millis() - deadline) >= 0;
}

void printReady() {
  Serial.println(
    "{\"type\":\"ready\",\"firmware\":\"roki-safe-hw-test\","
    "\"version\":\"1.2.1\",\"armed\":false}"
  );
}

void printHello(uint32_t sequence) {
  Serial.printf(
    "{\"type\":\"hello\",\"firmware\":\"roki-operating\","
    "\"version\":\"2.2.0\",\"protocol\":1,\"sequence\":%lu,"
    "\"commandTimeoutMs\":400,\"telemetryIntervalMs\":100}\n",
    static_cast<unsigned long>(sequence)
  );
}

void readEncoderSnapshot(int32_t &leftTicks, int32_t &rightTicks) {
  portENTER_CRITICAL(&encoderMux);
  leftTicks = leftEncoderTicks;
  rightTicks = rightEncoderTicks;
  portEXIT_CRITICAL(&encoderMux);
}

float readBatteryVoltage() {
  const uint32_t batteryMv = analogReadMilliVolts(BATTERY_ADC);
  return static_cast<float>(batteryMv) * BATTERY_DIVIDER_RATIO / 1000.0F;
}

float batteryVoltageToPercent(float packVoltage) {
  // Approximate resting-voltage curve for a 3S LiPo. This is deliberately
  // conservative and exists to satisfy the backend contract (0..100 percent);
  // voltage is also emitted separately for calibration and diagnostics.
  constexpr float cellVoltages[] = {
    3.30F, 3.50F, 3.60F, 3.70F, 3.80F, 3.90F, 4.00F, 4.10F, 4.20F
  };
  constexpr float percentages[] = {
    0.0F, 3.0F, 10.0F, 25.0F, 45.0F, 65.0F, 80.0F, 90.0F, 100.0F
  };
  constexpr size_t pointCount =
    sizeof(cellVoltages) / sizeof(cellVoltages[0]);

  const float cellVoltage = packVoltage / 3.0F;
  if (cellVoltage <= cellVoltages[0]) return 0.0F;
  if (cellVoltage >= cellVoltages[pointCount - 1]) return 100.0F;

  for (size_t index = 1; index < pointCount; ++index) {
    if (cellVoltage > cellVoltages[index]) continue;
    const float lowerVoltage = cellVoltages[index - 1];
    const float upperVoltage = cellVoltages[index];
    const float lowerPercent = percentages[index - 1];
    const float upperPercent = percentages[index];
    const float ratio =
      (cellVoltage - lowerVoltage) / (upperVoltage - lowerVoltage);
    return lowerPercent + ratio * (upperPercent - lowerPercent);
  }
  return 0.0F;
}

void printOdometry() {
  int32_t leftTicks;
  int32_t rightTicks;
  readEncoderSnapshot(leftTicks, rightTicks);
  Serial.printf(
    "{\"type\":\"odometry\",\"seq\":%lu,\"uptimeMs\":%lu,"
    "\"leftTicks\":%ld,\"rightTicks\":%ld}\n",
    static_cast<unsigned long>(odometrySequence++),
    static_cast<unsigned long>(millis()),
    static_cast<long>(leftTicks),
    static_cast<long>(rightTicks)
  );
}

const char *motorStatusText(MotorStatus status) {
  switch (status) {
    case MotorStatus::NORMAL: return "NORMAL";
    case MotorStatus::FAULT: return "FAULT";
    case MotorStatus::DISCONNECTED: return "DISCONNECTED";
  }
  return "FAULT";
}

const char *lineSensorStatusText(LineSensorStatus status) {
  switch (status) {
    case LineSensorStatus::NORMAL: return "NORMAL";
    case LineSensorStatus::FAULT: return "FAULT";
    case LineSensorStatus::DISCONNECTED: return "DISCONNECTED";
  }
  return "FAULT";
}

MotorStatus currentMotorStatus() {
  return faultCode == "NONE" ? MotorStatus::NORMAL : MotorStatus::FAULT;
}

LineSensorStatus currentLineSensorStatus() {
  // Digital inputs have no electrical disconnect diagnostic yet.
  return LineSensorStatus::NORMAL;
}

void readLineSensorSnapshot(uint8_t values[LINE_SENSOR_COUNT]) {
  for (uint8_t i = 0; i < LINE_SENSOR_COUNT; ++i) {
    values[i] = static_cast<uint8_t>(digitalRead(LINE_PINS[i]));
  }
}

void printHardwareStatus() {
  const float batteryVoltage = readBatteryVoltage();
  const float batteryPercent = batteryVoltageToPercent(batteryVoltage);
  uint8_t lineValues[LINE_SENSOR_COUNT];
  readLineSensorSnapshot(lineValues);
  Serial.printf(
    "{\"type\":\"hardwareStatus\",\"battery\":%.2f,"
    "\"batteryVoltage\":%.2f,\"motor\":\"%s\",\"lineSensor\":\"%s\","
    "\"lineValues\":[",
    static_cast<double>(batteryPercent),
    static_cast<double>(batteryVoltage),
    motorStatusText(currentMotorStatus()),
    lineSensorStatusText(currentLineSensorStatus())
  );
  for (uint8_t i = 0; i < LINE_SENSOR_COUNT; ++i) {
    if (i) Serial.print(',');
    Serial.print(lineValues[i]);
  }
  Serial.println("]}");
}

void printOperatingData() {
  printOdometry();
  printHardwareStatus();
}

void printStatus() {
  int32_t leftTicks;
  int32_t rightTicks;
  readEncoderSnapshot(leftTicks, rightTicks);

  const uint16_t batteryRaw = analogRead(BATTERY_ADC);
  const uint32_t batteryMv = analogReadMilliVolts(BATTERY_ADC);
  const float batteryVoltage =
    static_cast<float>(batteryMv) * BATTERY_DIVIDER_RATIO / 1000.0F;

  Serial.print("{\"type\":\"status\",\"safeFirmware\":true");
  Serial.print(",\"motorArmed\":");
  Serial.print(motorArmed ? "true" : "false");
  Serial.print(",\"driveActive\":");
  Serial.print(driveActive ? "true" : "false");
  Serial.print(",\"driveDirection\":\"");
  Serial.print(driveDirection);
  Serial.print('"');
  Serial.print(",\"servoArmed\":");
  Serial.print(servoArmed ? "true" : "false");
  Serial.print(",\"pca9685\":");
  Serial.print(pcaDetected ? "true" : "false");
  Serial.print(",\"leftEncoder\":");
  Serial.print(leftTicks);
  Serial.print(",\"rightEncoder\":");
  Serial.print(rightTicks);
  Serial.print(",\"batteryRaw\":");
  Serial.print(batteryRaw);
  Serial.print(",\"batteryVoltage\":");
  Serial.print(batteryVoltage, 2);
  Serial.print(",\"line\":[");
  for (uint8_t i = 0; i < LINE_SENSOR_COUNT; ++i) {
    if (i) Serial.print(',');
    Serial.print(digitalRead(LINE_PINS[i]));
  }
  Serial.println("]}");
}

void writeSignedMotorPwm(
  int16_t leftPwm,
  int16_t rightPwm
) {
  const uint8_t leftDuty = static_cast<uint8_t>(abs(leftPwm));
  const uint8_t rightDuty = static_cast<uint8_t>(abs(rightPwm));

  // Confirmed mapping: LEFT LPWM and RIGHT RPWM are forward.
  writeMotorPwm(LEFT_RPWM, leftPwm < 0 ? leftDuty : 0);
  writeMotorPwm(LEFT_LPWM, leftPwm > 0 ? leftDuty : 0);
  writeMotorPwm(RIGHT_RPWM, rightPwm > 0 ? rightDuty : 0);
  writeMotorPwm(RIGHT_LPWM, rightPwm < 0 ? rightDuty : 0);
}

bool setOperatingServo(uint8_t angle) {
  if (operatingServoApplied && angle == operatingServoAngle) return true;
  if (!pcaDetected) {
    pcaDetected = initializePca9685();
    operatingServoApplied = false;
  }
  if (!pcaDetected) return false;
  if (!pcaWriteChannel(SERVO_CHANNEL, 0, servoAngleToCount(angle))) {
    operatingServoApplied = false;
    return false;
  }
  operatingServoAngle = angle;
  operatingServoApplied = true;
  return true;
}

bool startOrRefreshOperatingControl(
  int16_t leftPwm,
  int16_t rightPwm,
  uint8_t servoAngle
) {
  if (!setOperatingServo(servoAngle)) return false;
  if (!driveActive) {
    zeroMotorPwm();
    digitalWrite(MOTOR_ENABLE, HIGH);
  }
  writeSignedMotorPwm(leftPwm, rightPwm);
  operatingLeftPwm = leftPwm;
  operatingRightPwm = rightPwm;
  operatingServoAngle = servoAngle;
  motorPulseActive = false;
  motorArmed = false;
  driveActive = leftPwm != 0 || rightPwm != 0;
  driveDirection = 'O';
  driveWatchdogDeadline = millis() + DRIVE_WATCHDOG_MS;
  operatingControlActive = true;
  stopReason = driveActive ? "NONE" : "CONTROL_ZERO";
  return true;
}

bool acceptCommandSequence(uint32_t sequence) {
  if (
    commandSequenceInitialized &&
    sequence <= lastCommandSequence &&
    !(lastCommandSequence == MAX_COMMAND_SEQUENCE && sequence == 0)
  ) {
    return false;
  }
  lastCommandSequence = sequence;
  commandSequenceInitialized = true;
  return true;
}

bool processOperatingJson(const String &command) {
  unsigned long sequence = 0;
  int speed = 0;
  int steering = 0;
  char trailing = '\0';
  if (command.startsWith("{\"type\":\"control\",")) {
    if (
      sscanf(
        command.c_str(),
        "{\"type\":\"control\",\"speed\":%d,\"steering\":%d,"
        "\"sequence\":%lu}%c",
        &speed,
        &steering,
        &sequence,
        &trailing
      ) != 3 ||
      sequence > MAX_COMMAND_SEQUENCE ||
      speed < -static_cast<int>(PWM_MAX) ||
      speed > static_cast<int>(PWM_MAX) ||
      steering < CONTROL_STEERING_MIN_ANGLE ||
      steering > CONTROL_STEERING_MAX_ANGLE
    ) {
      emergencyStop();
      stopReason = "INVALID_CONTROL";
      faultCode = "INVALID_CONTROL";
      Serial.println("{\"type\":\"error\",\"fault\":\"INVALID_CONTROL\"}");
      return true;
    }
    if (!acceptCommandSequence(static_cast<uint32_t>(sequence))) {
      emergencyStop();
      stopReason = "STALE_SEQUENCE";
      faultCode = "STALE_SEQUENCE";
      Serial.printf(
        "{\"type\":\"error\",\"fault\":\"STALE_SEQUENCE\","
        "\"sequence\":%lu}\n",
        sequence
      );
      return true;
    }
    if (!startOrRefreshOperatingControl(
      static_cast<int16_t>(speed),
      static_cast<int16_t>(speed),
      static_cast<uint8_t>(steering)
    )) {
      emergencyStop();
      stopReason = "SERVO_WRITE_FAILED";
      faultCode = "SERVO_WRITE_FAILED";
      Serial.printf(
        "{\"type\":\"error\",\"fault\":\"SERVO_WRITE_FAILED\","
        "\"sequence\":%lu}\n",
        sequence
      );
      return true;
    }
    faultCode = "NONE";
    Serial.printf(
      "{\"type\":\"ack\",\"command\":\"CONTROL\",\"sequence\":%lu}\n",
      sequence
    );
    return true;
  }

  const char *type = nullptr;
  if (command.startsWith("{\"type\":\"stop\",")) type = "stop";
  if (command.startsWith("{\"type\":\"status\",")) type = "status";
  if (command.startsWith("{\"type\":\"encoder_zero\",")) type = "encoder_zero";
  if (command.startsWith("{\"type\":\"hello\",")) {
    unsigned int protocol = 0;
    if (
      sscanf(
        command.c_str(),
        "{\"type\":\"hello\",\"protocol\":%u,\"sequence\":%lu}%c",
        &protocol,
        &sequence,
        &trailing
      ) != 2 ||
      protocol != 1 ||
      sequence > MAX_COMMAND_SEQUENCE
    ) {
      emergencyStop();
      stopReason = "INVALID_HELLO";
      faultCode = "INVALID_HELLO";
      Serial.println("{\"type\":\"error\",\"fault\":\"INVALID_HELLO\"}");
      return true;
    }
    // HELLO starts a new protocol session after a Jetson process restart.
    lastCommandSequence = static_cast<uint32_t>(sequence);
    commandSequenceInitialized = true;
    faultCode = "NONE";
    printHello(static_cast<uint32_t>(sequence));
    return true;
  }
  if (type == nullptr) return false;
  const String expectedPrefix = String("{\"type\":\"") + type
    + "\",\"sequence\":";
  if (
    sscanf(
      command.c_str(),
      (expectedPrefix + "%lu}%c").c_str(),
      &sequence,
      &trailing
    ) != 1 ||
    sequence > MAX_COMMAND_SEQUENCE
  ) {
    emergencyStop();
    stopReason = "INVALID_COMMAND";
    faultCode = "INVALID_COMMAND";
    Serial.println("{\"type\":\"error\",\"fault\":\"INVALID_COMMAND\"}");
    return true;
  }
  String commandName(type);
  commandName.toUpperCase();
  // STOP is always accepted, including after a Jetson sequence reset.
  if (
    commandName != "STOP" &&
    !acceptCommandSequence(static_cast<uint32_t>(sequence))
  ) {
    emergencyStop();
    stopReason = "STALE_SEQUENCE";
    faultCode = "STALE_SEQUENCE";
    Serial.println("{\"type\":\"error\",\"fault\":\"STALE_SEQUENCE\"}");
    return true;
  }
  if (commandName == "STOP") {
    lastCommandSequence = static_cast<uint32_t>(sequence);
    commandSequenceInitialized = true;
    stopMotors();
    servoOff();
    stopReason = "STOP_COMMAND";
    faultCode = "NONE";
  } else if (commandName == "ENCODER_ZERO") {
    portENTER_CRITICAL(&encoderMux);
    leftEncoderTicks = 0;
    rightEncoderTicks = 0;
    portEXIT_CRITICAL(&encoderMux);
  }
  Serial.printf(
    "{\"type\":\"ack\",\"command\":\"%s\",\"sequence\":%lu}\n",
    commandName.c_str(),
    sequence
  );
  if (commandName == "STATUS" || commandName == "ENCODER_ZERO") {
    printOperatingData();
  }
  return true;
}

void printI2cScan() {
  Serial.print("{\"type\":\"i2c\",\"addresses\":[");
  bool first = true;
  for (uint8_t address = 1; address < 127; ++address) {
    esp_task_wdt_reset();
    Wire.beginTransmission(address);
    if (Wire.endTransmission() == 0) {
      if (!first) Serial.print(',');
      Serial.print('"');
      if (address < 16) Serial.print('0');
      Serial.print(address, HEX);
      Serial.print('"');
      first = false;
    }
  }
  Serial.println("]}");
}

void printHelp() {
  Serial.println(
    "{\"type\":\"help\",\"commands\":[\"HELLO\",\"CONTROL <leftPwm> "
    "<rightPwm> <servoAngle>\",\"STOP\",\"STATUS\",\"PING\",\"I2C_SCAN\","
    "\"PCA_STATUS\",\"ENCODER_ZERO\",\"ESTOP\",\"ARM MOTORS\",\"ARM SERVO\","
    "\"MOTOR <L|R|BOTH> <A|B> <1..25> <50..500>\","
    "\"DRIVE <F|R> <1..20>\",\"DRIVE STOP\","
    "\"SERVO <60..100>\",\"SERVO_OFF\"]}"
  );
}

uint8_t percentToDuty(uint8_t percent) {
  return static_cast<uint8_t>((static_cast<uint16_t>(percent) * PWM_MAX) / 100U);
}

void startMotorPulse(
  const String &side,
  const String &channel,
  uint8_t speedPercent,
  uint16_t durationMs
) {
  stopMotors();
  // stopMotors() clears the arm flag, so enable only after every validation.
  digitalWrite(MOTOR_ENABLE, HIGH);

  const uint8_t duty = percentToDuty(speedPercent);
  if (side == "L" || side == "BOTH") {
    writeMotorPwm(channel == "A" ? LEFT_RPWM : LEFT_LPWM, duty);
  }
  if (side == "R" || side == "BOTH") {
    writeMotorPwm(channel == "A" ? RIGHT_RPWM : RIGHT_LPWM, duty);
  }

  motorPulseActive = true;
  motorStopDeadline = millis() + durationMs;

  Serial.printf(
    "{\"type\":\"motorPulse\",\"side\":\"%s\",\"channel\":\"%s\","
    "\"speed\":%u,\"durationMs\":%u}\n",
    side.c_str(),
    channel.c_str(),
    speedPercent,
    durationMs
  );
}

void startOrRefreshDrive(char direction, uint8_t speedPercent) {
  const bool starting = !driveActive;
  if (starting) {
    zeroMotorPwm();
    digitalWrite(MOTOR_ENABLE, HIGH);
  }

  const uint8_t duty = percentToDuty(speedPercent);
  if (direction == 'F') {
    // Confirmed physical mapping: LEFT B is forward, RIGHT A is forward.
    writeMotorPwm(LEFT_RPWM, 0);
    writeMotorPwm(LEFT_LPWM, duty);
    writeMotorPwm(RIGHT_RPWM, duty);
    writeMotorPwm(RIGHT_LPWM, 0);
  } else {
    // Confirmed physical mapping: LEFT A is reverse, RIGHT B is reverse.
    writeMotorPwm(LEFT_RPWM, duty);
    writeMotorPwm(LEFT_LPWM, 0);
    writeMotorPwm(RIGHT_RPWM, 0);
    writeMotorPwm(RIGHT_LPWM, duty);
  }

  motorPulseActive = false;
  motorArmed = false;
  driveActive = true;
  driveDirection = direction;
  driveWatchdogDeadline = millis() + DRIVE_WATCHDOG_MS;

  Serial.printf(
    "{\"type\":\"drive\",\"direction\":\"%c\",\"speed\":%u,"
    "\"watchdogMs\":%u,\"starting\":%s}\n",
    direction,
    speedPercent,
    DRIVE_WATCHDOG_MS,
    starting ? "true" : "false"
  );
}

void processCommand(String command) {
  command.trim();
  if (command.isEmpty()) return;
  if (processOperatingJson(command)) return;
  command.toUpperCase();

  if (command == "PING") {
    printReady();
    return;
  }
  if (command == "HELLO") {
    printHello(commandSequenceInitialized ? lastCommandSequence : 0);
    return;
  }
  if (command == "HELP") {
    printHelp();
    return;
  }
  if (command == "STATUS") {
    Serial.println("{\"type\":\"ack\",\"command\":\"STATUS\"}");
    printOperatingData();
    return;
  }
  if (command == "I2C_SCAN") {
    printI2cScan();
    return;
  }
  if (command == "PCA_STATUS") {
    printPcaStatus();
    return;
  }
  if (command == "ENCODER_ZERO") {
    portENTER_CRITICAL(&encoderMux);
    leftEncoderTicks = 0;
    rightEncoderTicks = 0;
    portEXIT_CRITICAL(&encoderMux);
    Serial.println("{\"type\":\"ack\",\"command\":\"ENCODER_ZERO\"}");
    printOperatingData();
    return;
  }
  if (command == "STOP") {
    stopMotors();
    servoOff();
    stopReason = "STOP_COMMAND";
    faultCode = "NONE";
    Serial.println("{\"type\":\"ack\",\"command\":\"STOP\"}");
    return;
  }
  if (command == "ESTOP" || command == "DISARM") {
    emergencyStop();
    Serial.println("{\"type\":\"estop\",\"stopped\":true}");
    return;
  }

  if (command.startsWith("CONTROL ")) {
    int leftPwm = 0;
    int rightPwm = 0;
    int servoAngle = 0;
    char trailing = '\0';
    if (
      sscanf(
        command.c_str(),
        "CONTROL %d %d %d %c",
        &leftPwm,
        &rightPwm,
        &servoAngle,
        &trailing
      ) != 3 ||
      leftPwm < -static_cast<int>(PWM_MAX) ||
      leftPwm > static_cast<int>(PWM_MAX) ||
      rightPwm < -static_cast<int>(PWM_MAX) ||
      rightPwm > static_cast<int>(PWM_MAX) ||
      servoAngle < CONTROL_STEERING_MIN_ANGLE ||
      servoAngle > CONTROL_STEERING_MAX_ANGLE
    ) {
      emergencyStop();
      stopReason = "INVALID_CONTROL";
      faultCode = "INVALID_CONTROL";
      Serial.println("{\"type\":\"error\",\"fault\":\"INVALID_CONTROL\"}");
      return;
    }
    if (!startOrRefreshOperatingControl(
      static_cast<int16_t>(leftPwm),
      static_cast<int16_t>(rightPwm),
      static_cast<uint8_t>(servoAngle)
    )) {
      emergencyStop();
      stopReason = "SERVO_WRITE_FAILED";
      faultCode = "SERVO_WRITE_FAILED";
      Serial.println("{\"type\":\"error\",\"fault\":\"SERVO_WRITE_FAILED\"}");
      return;
    }
    Serial.println("{\"type\":\"ack\",\"command\":\"CONTROL\"}");
    return;
  }
  if (command == "ARM MOTORS") {
    stopMotors();
    motorArmed = true;
    motorArmDeadline = millis() + ARM_WINDOW_MS;
    Serial.println("{\"type\":\"armed\",\"target\":\"motors\",\"expiresMs\":5000}");
    return;
  }
  if (command == "ARM SERVO") {
    servoOff();
    servoArmed = true;
    servoArmDeadline = millis() + ARM_WINDOW_MS;
    Serial.println("{\"type\":\"armed\",\"target\":\"servo\",\"expiresMs\":5000}");
    return;
  }
  if (command == "SERVO_OFF") {
    servoOff();
    Serial.println("{\"type\":\"servo\",\"off\":true}");
    return;
  }

  if (command == "DRIVE STOP") {
    stopMotors();
    Serial.println("{\"type\":\"drive\",\"stopped\":true}");
    return;
  }

  if (command.startsWith("DRIVE ")) {
    char direction = '\0';
    char trailing = '\0';
    int speed = 0;
    if (
      sscanf(
        command.c_str(),
        "DRIVE %c %d %c",
        &direction,
        &speed,
        &trailing
      ) != 2 ||
      (direction != 'F' && direction != 'R') ||
      speed < 1 ||
      speed > MAX_DRIVE_SPEED_PERCENT
    ) {
      stopMotors();
      Serial.println("{\"type\":\"error\",\"fault\":\"INVALID_DRIVE_COMMAND\"}");
      return;
    }

    if (driveActive && direction != driveDirection) {
      stopMotors();
      Serial.println(
        "{\"type\":\"error\",\"fault\":\"STOP_BEFORE_DIRECTION_CHANGE\"}"
      );
      return;
    }

    if (
      !driveActive &&
      (!motorArmed || deadlineReached(motorArmDeadline))
    ) {
      stopMotors();
      Serial.println("{\"type\":\"error\",\"fault\":\"DRIVE_NOT_ARMED\"}");
      return;
    }

    startOrRefreshDrive(direction, static_cast<uint8_t>(speed));
    return;
  }

  if (command.startsWith("MOTOR ")) {
    if (!motorArmed || deadlineReached(motorArmDeadline)) {
      stopMotors();
      Serial.println("{\"type\":\"error\",\"fault\":\"MOTOR_NOT_ARMED\"}");
      return;
    }

    char sideBuffer[8] = {0};
    char channelBuffer[8] = {0};
    int speed = 0;
    int duration = 0;
    const int parsed = sscanf(
      command.c_str(),
      "MOTOR %7s %7s %d %d",
      sideBuffer,
      channelBuffer,
      &speed,
      &duration
    );
    const String side(sideBuffer);
    const String channel(channelBuffer);

    if (
      parsed != 4 ||
      (side != "L" && side != "R" && side != "BOTH") ||
      (channel != "A" && channel != "B") ||
      speed < 1 ||
      speed > MAX_TEST_SPEED_PERCENT ||
      duration < MIN_TEST_PULSE_MS ||
      duration > MAX_TEST_PULSE_MS
    ) {
      stopMotors();
      Serial.println("{\"type\":\"error\",\"fault\":\"INVALID_MOTOR_PULSE\"}");
      return;
    }

    startMotorPulse(
      side,
      channel,
      static_cast<uint8_t>(speed),
      static_cast<uint16_t>(duration)
    );
    return;
  }

  if (command.startsWith("SERVO ")) {
    stopMotors();
    if (!servoArmed || deadlineReached(servoArmDeadline)) {
      servoOff();
      Serial.println("{\"type\":\"error\",\"fault\":\"SERVO_NOT_ARMED\"}");
      return;
    }

    int angle = -1;
    if (
      sscanf(command.c_str(), "SERVO %d", &angle) != 1 ||
      angle < SERVO_MIN_TEST_ANGLE ||
      angle > SERVO_MAX_TEST_ANGLE
    ) {
      servoOff();
      Serial.println("{\"type\":\"error\",\"fault\":\"INVALID_SERVO_ANGLE\"}");
      return;
    }

    if (!pcaDetected) pcaDetected = initializePca9685();
    if (!pcaDetected) {
      servoOff();
      Serial.println("{\"type\":\"error\",\"fault\":\"PCA9685_NOT_FOUND\"}");
      return;
    }

    const uint16_t count = servoAngleToCount(static_cast<uint8_t>(angle));
    if (!pcaWriteChannel(SERVO_CHANNEL, 0, count)) {
      servoOff();
      Serial.println("{\"type\":\"error\",\"fault\":\"PCA9685_WRITE_FAILED\"}");
      return;
    }
    printPcaStatus();

    servoPulseActive = true;
    servoOffDeadline = millis() + SERVO_AUTO_OFF_MS;
    servoArmed = false;
    Serial.printf(
      "{\"type\":\"servo\",\"angle\":%d,\"autoOffMs\":%u}\n",
      angle,
      SERVO_AUTO_OFF_MS
    );
    return;
  }

  emergencyStop();
  stopReason = "INVALID_COMMAND";
  faultCode = "INVALID_COMMAND";
  Serial.println("{\"type\":\"error\",\"fault\":\"UNKNOWN_COMMAND\"}");
}

void setup() {
  // Set output latches low before changing pin mode.
  digitalWrite(MOTOR_ENABLE, LOW);
  digitalWrite(LEFT_RPWM, LOW);
  digitalWrite(LEFT_LPWM, LOW);
  digitalWrite(RIGHT_RPWM, LOW);
  digitalWrite(RIGHT_LPWM, LOW);

  pinMode(MOTOR_ENABLE, OUTPUT);
  pinMode(LEFT_RPWM, OUTPUT);
  pinMode(LEFT_LPWM, OUTPUT);
  pinMode(RIGHT_RPWM, OUTPUT);
  pinMode(RIGHT_LPWM, OUTPUT);

  attachMotorPwm();
  stopMotors();

  pinMode(LEFT_ENCODER_A, INPUT);
  pinMode(LEFT_ENCODER_B, INPUT);
  pinMode(RIGHT_ENCODER_A, INPUT);
  pinMode(RIGHT_ENCODER_B, INPUT);
  attachInterrupt(digitalPinToInterrupt(LEFT_ENCODER_A), onLeftEncoderA, RISING);
  attachInterrupt(digitalPinToInterrupt(RIGHT_ENCODER_A), onRightEncoderA, RISING);

  pinMode(BATTERY_ADC, INPUT);
  analogReadResolution(12);
  analogSetPinAttenuation(BATTERY_ADC, ADC_11db);

  for (uint8_t pin : LINE_PINS) pinMode(pin, INPUT_PULLUP);

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(100000);
  pcaDetected = initializePca9685();
  servoOff();

  Serial.begin(SERIAL_BAUD);
  commandBuffer.reserve(128);
  delay(150);

  // Recover the whole firmware if the single Arduino loop stops progressing.
  // The motor command watchdog remains the faster, independent motion stop.
  enableLoopWDT();
}

void serviceTelemetry() {
  if (deadlineReached(nextOdometryDeadline)) {
    printOdometry();
    nextOdometryDeadline = millis() + ODOMETRY_INTERVAL_MS;
  }
  if (deadlineReached(nextHardwareStatusDeadline)) {
    printHardwareStatus();
    nextHardwareStatusDeadline =
      millis() + HARDWARE_STATUS_INTERVAL_MS;
  }
}

void loop() {
  if (motorPulseActive && deadlineReached(motorStopDeadline)) {
    stopMotors();
    Serial.println("{\"type\":\"motorPulse\",\"stopped\":true,\"armed\":false}");
  }
  if (motorArmed && deadlineReached(motorArmDeadline)) {
    stopMotors();
    Serial.println("{\"type\":\"armTimeout\",\"target\":\"motors\"}");
  }
  if (
    (driveActive || operatingControlActive) &&
    deadlineReached(driveWatchdogDeadline)
  ) {
    stopMotors();
    servoOff();
    stopReason = "COMMAND_TIMEOUT";
    faultCode = "COMMAND_TIMEOUT";
    Serial.println("{\"type\":\"error\",\"fault\":\"COMMAND_TIMEOUT\"}");
  }
  if (servoArmed && deadlineReached(servoArmDeadline)) {
    servoOff();
    Serial.println("{\"type\":\"armTimeout\",\"target\":\"servo\"}");
  }
  if (servoPulseActive && deadlineReached(servoOffDeadline)) {
    servoOff();
    Serial.println("{\"type\":\"servo\",\"off\":true,\"reason\":\"AUTO_OFF\"}");
  }

  // Telemetry is safety-critical progress, so never place an unbounded command
  // backlog ahead of its deadline.
  serviceTelemetry();

  uint16_t serialBytesProcessed = 0;
  uint8_t commandsProcessed = 0;
  while (
    Serial.available() > 0 &&
    serialBytesProcessed < MAX_SERIAL_BYTES_PER_LOOP &&
    commandsProcessed < MAX_COMMANDS_PER_LOOP
  ) {
    const char incoming = static_cast<char>(Serial.read());
    ++serialBytesProcessed;
    if (incoming == '\n') {
      processCommand(commandBuffer);
      commandBuffer = "";
      ++commandsProcessed;
      continue;
    }
    if (incoming == '\r') continue;
    if (commandBuffer.length() >= 120) {
      commandBuffer = "";
      emergencyStop();
      faultCode = "COMMAND_TOO_LONG";
      Serial.println("{\"type\":\"error\",\"fault\":\"COMMAND_TOO_LONG\"}");
      continue;
    }
    commandBuffer += incoming;
  }

  // A CONTROL command may spend bounded time in I2C. Recheck deadlines before
  // returning so that a busy input stream cannot starve either telemetry line.
  serviceTelemetry();
}
