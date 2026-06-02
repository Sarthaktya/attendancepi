"""
Physical hardware feedback — LEDs and buzzer wired to Pi GPIO.

Wiring (BCM numbering):
    GPIO 5  → 220Ω → Blue LED  → GND   (success / marked present)
    GPIO 27 → 220Ω → Red LED   → GND   (unknown face / not matched)
    GPIO 22 → Active buzzer (+) → GND  (audio feedback)

    Note: GPIO 17 was the original blue LED pin but it's reserved by
    the 5-inch touchscreen ("pendown"). GPIO 5 is the replacement.

All actions are non-blocking — internally they spawn short daemon threads
so the main CV loop never stalls on a beep or LED timing.

Gracefully no-ops on machines without gpiozero (laptop testing).
"""

import threading
import time

try:
    from gpiozero import LED, Buzzer
    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False


# Pin assignments (BCM)
BLUE_LED_PIN = 5     # GPIO 17 was the original choice but it's reserved by the touchscreen
RED_LED_PIN  = 27
BUZZER_PIN   = 22


class Feedback:
    def __init__(self, enabled=True):
        self.enabled = enabled and GPIO_AVAILABLE

        if not self.enabled:
            print("Hardware feedback disabled (gpiozero unavailable or HARDWARE_ENABLED=False)")
            return

        self.blue   = LED(BLUE_LED_PIN)
        self.red    = LED(RED_LED_PIN)
        self.buzzer = Buzzer(BUZZER_PIN)

        # Make sure everything starts in a clean OFF state — Pi GPIO pins
        # can default to HIGH at boot before any code runs
        self.blue.off()
        self.red.off()
        self.buzzer.off()

        print("Hardware feedback ready (Blue=GPIO5, Red=GPIO27, Buzzer=GPIO22)")

    # ── Public events ─────────────────────────────────────────────────────────

    def marked_present(self):
        """Blue LED on for 3 sec + single short beep."""
        if not self.enabled:
            return
        threading.Thread(target=self._marked_present, daemon=True).start()

    def unknown_face(self):
        """Red LED flashes 3 times + double beep."""
        if not self.enabled:
            return
        threading.Thread(target=self._unknown_face, daemon=True).start()

    def cleanup(self):
        if not self.enabled:
            return
        self.blue.off()
        self.red.off()
        self.buzzer.off()

    # ── Internal sequences ────────────────────────────────────────────────────

    def _marked_present(self):
        self.blue.on()
        self._beep(0.15)
        time.sleep(3.0)
        self.blue.off()

    def _unknown_face(self):
        self._beep(0.08)
        time.sleep(0.08)
        self._beep(0.08)

        for _ in range(3):
            self.red.on()
            time.sleep(0.25)
            self.red.off()
            time.sleep(0.25)

    def _beep(self, duration):
        self.buzzer.on()
        time.sleep(duration)
        self.buzzer.off()
