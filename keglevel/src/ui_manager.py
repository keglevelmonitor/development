# keglevel app
#
# ui_manager.py
import tkinter as tk
from tkinter import ttk, messagebox

# --- NEW: Import base classes ---
from ui_manager_base import MainUIBase
from popup_manager_mixin import PopupManagerMixin
# ------------------------------------

# --- REFACTORED: Remove direct imports of everything now in the base/mixin files ---
# We keep only the necessary imports needed for the final class definition if any, 
# but most were moved to the base files.

# --- NEW: Import platform flag from sensor_logic (kept here for redundancy/clean imports) ---
try:
    from sensor_logic import IS_RASPBERRY_PI_MODE
except ImportError:
    IS_RASPBERRY_PI_MODE = False
# ------------------------------------

# --- COMPOSITION CLASS: Inherits from both base classes ---
class UIManager(MainUIBase, PopupManagerMixin):
    # MODIFIED: Added app_version_string argument
    def __init__(self, root, settings_manager_instance, sensor_logic_instance, notification_service_instance, temp_logic_instance, num_sensors, app_version_string):
        
        # 1. Initialize MainUIBase (sets up main window, root vars, calls _create_widgets)
        # MODIFIED: Pass app_version_string
        MainUIBase.__init__(self, root, settings_manager_instance, sensor_logic_instance, notification_service_instance, temp_logic_instance, num_sensors, app_version_string)
        
        # 2. Initialize PopupManagerMixin (sets up all popup-specific tk.StringVar variables)
        # MODIFIED: Pass app_version_string to mixin for direct access
        PopupManagerMixin.__init__(self, settings_manager_instance, num_sensors, app_version_string)

        # 3. Final Setup: Link Menu Commands (requires both bases to be initialized)
        self._setup_menu_commands()

        # 4. Final Setup: Link Callbacks to Core Services
        # Note: These link methods from MainUIBase (e.g., update_sensor_data_display) 
        # to the service instances passed during init.
        if self.sensor_logic:
            self.sensor_logic.ui_callbacks = {
                "update_sensor_data_cb": self.update_sensor_data_display,
                "update_sensor_stability_cb": self.update_sensor_stability_display,
                "update_header_status_cb": self.update_header_status,
                "update_sensor_connection_status_cb": self.update_sensor_connection_status,
                # --- NEW: Calibration Live Data Callback ---
                "update_cal_data_cb": self.update_cal_popup_display 
                # ------------------------------------------
            }
        if self.temp_logic:
            self.temp_logic.ui_callbacks["update_temp_display_cb"] = self.update_temperature_display

        # 5. Final link steps (Notification Service Manager)
        if self.notification_service: 
            self.notification_service.ui_manager = self
            self.notification_service.ui_manager_status_update_cb = self.update_notification_status_display
            
    # --- NEW METHOD: Expose flow calibration update through the queue ---
    def update_cal_popup_display(self, flow_rate_lpm, dispensed_pour_liters):
        """Puts a task on the queue to update the live calibration popup data."""
        # This calls the method inherited from MainUIBase to queue the update
        self.ui_update_queue.put(("update_cal_data", (flow_rate_lpm, dispensed_pour_liters)))
    # --- END NEW METHOD ---

    # --- MODIFIED: UIManager._poll_ui_update_queue is in MainUIBase. I will update MainUIBase ---
