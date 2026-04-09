import subprocess
import time

while True:
    subprocess.run(["python", "main.py"])
    print("main.py crashed, restarting in 2 seconds...")
    time.sleep(2)