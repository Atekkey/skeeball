import subprocess
import time
import RPi.GPIO as GPIO


while True:
    GPIO.cleanup()
    subprocess.run(["python", "main.py"])
    print("main.py crashed, restarting in 2 seconds...")
    time.sleep(2)