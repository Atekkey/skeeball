import subprocess
import sys
import time
import RPi.GPIO as GPIO

subprocess.run(["git", "pull"])
while True:
    try:
        GPIO.cleanup()
        subprocess.run(["python", "main.py"] + sys.argv[1:])
        print("main.py crashed, restarting in 2 seconds...")
        time.sleep(2)
    except KeyboardInterrupt:
        print("Stopped by user")
        GPIO.cleanup()
        break