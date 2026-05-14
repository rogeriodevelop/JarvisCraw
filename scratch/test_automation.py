import sys
import os

# Add current dir to path
sys.path.append(os.getcwd())

from agent_runner import computer_control, launch_app, manage_background_task

print("--- Testing computer_control (Imports and Screenshot Syntax) ---")
try:
    # We won't actually take a screenshot in the headless/remote environment if it fails, 
    # but we can check if pyautogui is importable and size() works.
    import pyautogui
    size = pyautogui.size()
    print(f"Screen size detected: {size}")
except Exception as e:
    print(f"PyAutoGUI Error (Expected if no display): {e}")

print("\n--- Testing launch_app syntax ---")
# Testing with a benign command like 'echo' via start
res = launch_app("echo hello")
print(f"Result: {res}")

print("\n--- Testing manage_background_task syntax ---")
# Start a task that logs every 1s, wait 3s, and see if log exists
res = manage_background_task("start", "test instruction", interval=1)
print(f"Result: {res}")

import time
time.sleep(3)

log_path = "scratch/background_tasks.log"
if os.path.exists(log_path):
    with open(log_path, "r") as f:
        print(f"Log content:\n{f.read()}")
else:
    print("Log file not created!")
