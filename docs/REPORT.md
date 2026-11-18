# Project Report – Face Recognition Door Lock

## 1. Introduction

Traditional keys can be lost, copied or forgotten. This project replaces the
key with the user's face: a camera at the door identifies the visitor and a
servo motor opens the latch for authorised people. When the visitor is unknown,
the system does not simply refuse; it informs the owner by SMS, shows them a
photo of the visitor, and lets them open the door remotely from their phone.

## 2. Objectives

- Unlock a door automatically for people registered in a face database.
- Give an unrecognised visitor a limited number of tries.
- Alert the owner by SMS, with the visitor's photo, when recognition fails.
- Let the owner unlock or refuse access remotely.
- Keep a log of every access event.

## 3. System overview

| Block | Role | Technology |
|---|---|---|
| Camera | captures the visitor | USB webcam / Pi camera |
| Vision | detects and recognises the face | Python, OpenCV (Haar cascade + LBPH) |
| Controller | decides: open, retry or alert | Python state machine |
| Actuator | moves the latch | servo motor on Arduino or Raspberry Pi |
| Alert | informs the owner | Twilio SMS |
| Remote control | owner's Unlock / Deny page | Flask web server |

## 4. Face recognition

### 4.1 Detection

Each frame is converted to grayscale and scanned with OpenCV's Haar cascade
frontal-face classifier. If several faces are visible, the largest one (the
person closest to the door) is used.

### 4.2 Database (enrolment)

`enroll.py` captures about 50 samples of each authorised person. Every sample
is cropped to the face, resized to 200×200 pixels and histogram-equalised to
reduce the effect of lighting. Samples are stored in `dataset/<name>/`.

### 4.3 Recognition

`train.py` trains an LBPH (Local Binary Patterns Histograms) recogniser on the
dataset. LBPH describes the local texture of the face as histograms and
compares them with the stored ones. For a new face it returns the closest
person and a distance: the smaller the distance, the better the match. A face
whose distance is above `MATCH_THRESHOLD` is treated as unknown.

LBPH was chosen because it is included in OpenCV, trains in seconds, needs few
images and runs in real time on small hardware such as a Raspberry Pi.

## 5. Access logic

The controller is a state machine fed with one recognition result per frame:

1. **Idle** – waiting for a face.
2. **Scanning** – one try lasts a few seconds. The door opens only if the same
   known person is recognised in several consecutive frames, so a single
   false match cannot open it.
3. **Retry** – if the try fails, the visitor sees "Try again" and gets another one.
4. **Owner alert** – after the last failed try, a snapshot is saved, a
   single-use approval request is created, and an SMS with its link is sent.
5. **Waiting for owner** – the owner opens the link, sees the photo and taps
   **Unlock** or **Deny**. With no answer before the timeout, the request expires.
6. **Unlocked** – the servo opens the latch, then re-locks after a few seconds.

## 6. Hardware

The servo is driven in one of two ways:

- **Arduino** – the PC sends `U` (unlock) or `L` (lock) over USB serial; the
  sketch moves the servo on pin D9 and switches a green/red LED. As a safety
  net the Arduino re-locks by itself if no lock command arrives.
- **Raspberry Pi** – the servo is connected to a PWM-capable GPIO pin and
  controlled with `gpiozero`.

## 7. Owner notification and remote unlock

The SMS is sent through the Twilio API. It contains a link to a small web page
served by the door lock itself (Flask), showing the visitor's photo and the
two buttons. Security measures:

- each request has a random, unguessable token in its link;
- the link expires and can be answered only once;
- unlocking requires pressing the button (HTTP POST), so merely opening or
  previewing the link never opens the door;
- the web server only records the answer; the controller moves the servo.

## 8. Testing

The access logic and the web page are covered by automated tests
(`tests/test_doorlock.py`) that run without camera or hardware: recognised
face, retries, owner alert, approval, denial, expiry, SMS failure, invalid
token. Recognition quality itself depends on the camera and lighting and
should be evaluated on the final installation by adjusting `MATCH_THRESHOLD`.

## 9. Limitations and future work

- A 2D camera can be fooled by a photo: add liveness detection (blink or
  depth check).
- LBPH is sensitive to strong lighting changes: a deep-learning embedding
  model would be more robust.
- Add a fallback (keypad or RFID) and an owner login on the approval page.

## 10. Conclusion

The project combines computer vision, embedded control and web/SMS services
into a complete access-control prototype: known faces enter hands-free, and
the owner stays in control of every other visitor from their phone.
