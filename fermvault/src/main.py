"""
fermvault app
main.py
"""

import tkinter as tk
import time
import os
import sys
import threading
import signal

# --- FIX: Ensure all classes used later are imported here ---
print("[DEBUG] Main: Importing SettingsManager...")
from settings_manager import SettingsManager
print("[DEBUG] Main: Importing TemperatureController...")
from temperature_controller import TemperatureController
print("[DEBUG] Main: Importing UIManager...")
from ui_manager import UIManager
print("[DEBUG] Main: Importing NotificationManager...")
from notification_manager import NotificationManager
print("[DEBUG] Main: Importing RelayControl...")
from relay_control import RelayControl
print("[DEBUG] Main: Importing APIManager...")
from api_manager import APIManager 
print("[DEBUG] Main: Importing FGCalculator...")
from fg_calculator import FGCalculator
print("[DEBUG] Main: All imports complete.")
# -------------------------------------------------------------

# --- FIX: CORRECT BCM PINS CORRESPONDING TO BOARD 37, 38, 40 ---
RELAY_PINS = {
    "Heat": 26, # Was 17 (Board Pin 37)
    "Cool": 20, # Was 27 (Board Pin 38)
    "Fan": 21,  # Was 22 (Board Pin 40)
}
# -----------------------------------------------------------------

# Get the base application directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- App Initialization ---
print("[DEBUG] Main: Step 1 - Initializing SettingsManager...")
settings = SettingsManager()

# --- NEW: Force Control Mode to Ambient on every launch ---
settings.set("control_mode", "Ambient Hold")
# --- END NEW ---

# --- MODIFICATION: Check shutdown status ---
if not settings.get_last_shutdown_status():
    print("[WARNING] Main: Previous shutdown was uncontrolled.")
else:
    print("[DEBUG] Main: Previous shutdown was controlled.")
# --- END MODIFICATION ---

print("[DEBUG] Main: Step 2 - Initializing Tkinter root...")
root = tk.Tk()
root.withdraw() 
print("[DEBUG] Main: Step 3 - Initializing APIManager...")

# 1. Load Dynamic API Manager
api_manager = APIManager(settings)
api_manager.discover_services(BASE_DIR)
print("[DEBUG] Main: Step 4 - Initializing NotificationManager...")

# 2. Create the NotificationManager instance
notification_manager = NotificationManager(settings, ui_manager=None) 
print("[DEBUG] Main: Step 5 - Initializing Control Components (RelayControl)...")

# 3. Initialize Control Components
relay_control = RelayControl(settings, RELAY_PINS)
print("[DEBUG] Main: Step 6 - Initializing Control Components (TempController)...")
temp_controller = TemperatureController(settings, relay_control)
print("[DEBUG] Main: Step 7 - Initializing FGCalculator...")

# 3.5. Initialize FG Calculator
fg_calculator = FGCalculator(settings, api_manager)

print("[DEBUG] Main: Step 8 - Deiconifying root...")
root.deiconify()
print("[DEBUG] Main: Step 9 - Initializing UIManager...")

# 4. Initialize UI
ui = UIManager(root, settings, temp_controller, api_manager, notification_manager, "Fermentation Vault v1.0", fg_calculator) 
print("[DEBUG] Main: Step 10 - Finalizing Circular References...")

# 5. Finalize Circular References
notification_manager.ui = ui 
temp_controller.notification_manager = notification_manager
relay_control.set_logger(ui.log_system_message) 
print("[DEBUG] Main: Step 11 - Starting Services...")

# --- CRITICAL FIX: SIGNAL HANDLING FOR TERMINAL CLOSURE ---
def handle_exit_signal(signum, frame):
    """
    Robust signal handler that prioritizes hardware cleanup over logging.
    Handles SIGHUP (Terminal Close) and SIGTERM (Logout/System Shutdown).
    """
    # 1. EXECUTE CLEANUP FIRST (Before attempting to print)
    # We use a try/except block to ensure one error doesn't stop the next cleanup step
    try:
        if 'relay_control' in globals() and relay_control:
            relay_control.cleanup_gpio()
    except Exception:
        pass # Hardware safety failed, nothing else we can do

    # 2. Attempt to log (This might fail if terminal is closed, so we wrap it)
    try:
        signal_name = "SIGHUP" if signum == signal.SIGHUP else "SIGTERM"
        print(f"\n[SHUTDOWN] Received {signal_name}. Hardware cleanup complete.")
    except (IOError, OSError):
        pass # Stdout is likely dead (terminal closed), ignore the error

    # 3. FORCE EXIT
    # We use os._exit() to kill the process immediately. 
    # sys.exit() throws an exception that Tkinter might catch/block.
    os._exit(0)

# Register the signals
signal.signal(signal.SIGHUP, handle_exit_signal)
signal.signal(signal.SIGTERM, handle_exit_signal)
# ----------------------------------------------------------

def shutdown_application():
    print(f"[SHUTDOWN] Controlled shutdown initiated...")
    
    if notification_manager:
        notification_manager.stop_scheduler()

    if temp_controller:
        temp_controller.stop_monitoring()
        
    if relay_control:
        relay_control.turn_off_all_relays()

    settings.set_controlled_shutdown(True)
    time.sleep(0.5)

    root.quit()
    root.destroy()
    print("[SHUTDOWN] Application closed.")
    # Explicitly call sys.exit to trigger the finally block below if not already triggered
    sys.exit(0)

# Bind shutdown function to window close event
root.protocol("WM_DELETE_WINDOW", shutdown_application)

print("[DEBUG] Main: Step 12 - Starting mainloop()...")

try:
    root.mainloop()
except KeyboardInterrupt:
    print("\n[SHUTDOWN] KeyboardInterrupt detected (Ctrl+C).")
except SystemExit:
    # This catches sys.exit() calls
    pass
except Exception as e:
    print(f"\n[CRITICAL ERROR] Application crashed: {e}")
finally:
    # This block handles standard exits (Window close, Ctrl+C)
    # The signal handler above handles the aggressive kills (Terminal close, Logout)
    print("[SHUTDOWN] Performing standard exit cleanup...")
    if 'relay_control' in locals() and relay_control:
        relay_control.cleanup_gpio()
    print("[SHUTDOWN] Cleanup complete.")
