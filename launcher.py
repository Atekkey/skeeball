import subprocess
import sys
import time
import RPi.GPIO as GPIO

subprocess.run(["git", "pull"])
while True:
    GPIO.cleanup()
    subprocess.run(["python", "main.py"] + sys.argv[1:])
    print("main.py crashed, restarting in 2 seconds...")
    time.sleep(2)