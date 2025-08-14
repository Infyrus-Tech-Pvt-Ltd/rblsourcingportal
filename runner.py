import subprocess
import threading
import time

DEPLOYMENT_TYPE = "docker" #linux,docker,windows

# Define the commands

if DEPLOYMENT_TYPE == "windows":
    # Windows
    commands = [
        ["./venv/Scripts/python.exe", "./app.py"],
        ["./backend/pocketbase.exe", "serve", "--http=0.0.0.0:8090"]
    ]
elif DEPLOYMENT_TYPE == "linux":
        # Linux
        commands = [
            ["./venv/bin/python", "./app.py"],
            ["./backend/pocketbase", "serve", "--http=0.0.0.0:8090"]
        ]
elif DEPLOYMENT_TYPE == "docker":
        # Docker
        commands = [
            ["python", "./app.py"],
            ["./backend/pocketbase", "serve", "--http=0.0.0.0:8090"]
        ]
else:
        print("Unknown deployment type")
        exit(1)

# Function to run a command and restart it if it crashes
def run_command(cmd):
    while True:
        try:
            print(f"Starting: {' '.join(cmd)}")
            process = subprocess.Popen(cmd)
            process.wait()
            print(f"Process exited: {' '.join(cmd)}. Restarting in 2 seconds...")
            time.sleep(2)
        except Exception as e:
            print(f"Error running {' '.join(cmd)}: {e}")
            time.sleep(2)

# Start each command in a separate thread
threads = []
for cmd in commands:
    t = threading.Thread(target=run_command, args=(cmd,), daemon=True)
    t.start()
    threads.append(t)

# Keep the main thread alive
try:
    while True:
        time.sleep(10)
except KeyboardInterrupt:
    print("Shutting down...")
