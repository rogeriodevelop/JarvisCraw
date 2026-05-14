import pyautogui
import time
import os

def test_control():
    try:
        width, height = pyautogui.size()
        print(f"Screen resolution: {width}x{height}")
        
        # Move to center
        cx, cy = width // 2, height // 2
        print(f"Moving to center: ({cx}, {cy})")
        pyautogui.moveTo(cx, cy, duration=1)
        
        # Small circle
        print("Drawing a small circle...")
        for i in range(10):
            pyautogui.moveRel(10, 0, duration=0.1)
            pyautogui.moveRel(0, 10, duration=0.1)
            pyautogui.moveRel(-10, 0, duration=0.1)
            pyautogui.moveRel(0, -10, duration=0.1)
            
        print("Test finished successfully.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_control()
