/*
 * Face Recognition Door Lock - servo controller
 *
 * The Python program sends one character over USB serial:
 *   'U' -> unlock (servo to UNLOCKED_ANGLE, green LED on)
 *   'L' -> lock   (servo to LOCKED_ANGLE, red LED on)
 *
 * Wiring:
 *   Servo signal (orange/yellow) -> D9
 *   Servo VCC (red)              -> 5V (use an external 5V supply for big servos)
 *   Servo GND (brown/black)      -> GND
 *   Green LED + 220 ohm resistor -> D6   (optional)
 *   Red LED   + 220 ohm resistor -> D7   (optional)
 */
#include <Servo.h>

const int SERVO_PIN = 9;
const int GREEN_LED = 6;
const int RED_LED = 7;
const int LOCKED_ANGLE = 0;
const int UNLOCKED_ANGLE = 90;

// Safety net: if the PC crashes while the door is open, lock it again.
const unsigned long MAX_UNLOCK_MS = 30000;

Servo latch;
bool unlocked = false;
unsigned long unlockedAt = 0;

void lockDoor() {
  latch.write(LOCKED_ANGLE);
  digitalWrite(GREEN_LED, LOW);
  digitalWrite(RED_LED, HIGH);
  unlocked = false;
}

void unlockDoor() {
  latch.write(UNLOCKED_ANGLE);
  digitalWrite(GREEN_LED, HIGH);
  digitalWrite(RED_LED, LOW);
  unlocked = true;
  unlockedAt = millis();
}

void setup() {
  pinMode(GREEN_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);
  latch.attach(SERVO_PIN);
  Serial.begin(9600);
  lockDoor();
}

void loop() {
  if (Serial.available() > 0) {
    char command = Serial.read();
    if (command == 'U') unlockDoor();
    if (command == 'L') lockDoor();
  }
  if (unlocked && millis() - unlockedAt > MAX_UNLOCK_MS) {
    lockDoor();
  }
}
