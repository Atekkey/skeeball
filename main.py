PI = 1
if PI:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)

import time



SWITCH_PINS = {
    17: 1,
    18: 2,
    22: 3,
    23: 4,
    24: 5,
}


def ball_scored(channel):
    global score
    points = SWITCH_PINS[channel]
    score += points
    print(f"PIN {channel} TRIGGERED")


# SETUP
for pin in SWITCH_PINS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(
        pin,
        GPIO.FALLING,        # FALLING = pin goes LOW (switch closes)
        callback=ball_scored,
        bouncetime=300       # 300ms debounce — ignores rapid re-triggers
    )



score = 0

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print(f"Game over! Final score: {score}")
    GPIO.cleanup()