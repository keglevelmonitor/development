# keglevel app
#
# ui_manager.py
import tkinter as tk
from tkinter import ttk, messagebox

# --- UPDATED IMPORTS: Import APP_REVISION explicitly ---
from ui_manager_base import MainUIBase, APP_REVISION
from popup_manager_mixin import PopupManagerMixin
# -----------------------------------------------------

try:
    from sensor_logic import IS_RASPBERRY_PI_MODE
except ImportError:
    IS_RASPBERRY_PI_MODE = False

# --- COMPOSITION CLASS: Inherits from both base classes ---
class UIManager(MainUIBase, PopupManagerMixin):
    # MODIFIED: Added app_version_string argument (kept for compatibility but overridden internally)
    def __init__(self, root, settings_manager_instance, sensor_logic_instance, notification_service_instance, temp_logic_instance, num_sensors, app_version_string):
        
        # --- FIX: Override the passed version with the Master Revision Constant ---
        # This ensures ui_manager_base.py is the single source of truth for the version.
        real_version = APP_REVISION
        # ------------------------------------------------------------------------

        # 1. Initialize MainUIBase
        MainUIBase.__init__(self, root, settings_manager_instance, sensor_logic_instance, notification_service_instance, temp_logic_instance, num_sensors, real_version)
        
        # 2. Initialize PopupManagerMixin
        # We pass 'real_version' here so the About popup displays the dynamic date/time
        PopupManagerMixin.__init__(self, settings_manager_instance, num_sensors, real_version)

        # 3. Final Setup: Link Menu Commands
        self._setup_menu_commands()

        # 4. Final Setup: Link Callbacks to Core Services
        if self.sensor_logic:
            self.sensor_logic.ui_callbacks = {
                "update_sensor_data_cb": self.update_sensor_data_display,
                "update_sensor_stability_cb": self.update_sensor_stability_display,
                "update_header_status_cb": self.update_header_status,
                "update_sensor_connection_status_cb": self.update_sensor_connection_status,
                "update_cal_data_cb": self.update_cal_popup_display 
            }
        if self.temp_logic:
            self.temp_logic.ui_callbacks["update_temp_display_cb"] = self.update_temperature_display

        # 5. Final link steps (Notification Service Manager)
        if self.notification_service: 
            self.notification_service.ui_manager = self
            self.notification_service.ui_manager_status_update_cb = self.update_notification_status_display
            
    def update_cal_popup_display(self, flow_rate_lpm, dispensed_pour_liters):
        """Puts a task on the queue to update the live calibration popup data."""
        self.ui_update_queue.put(("update_cal_data", (flow_rate_lpm, dispensed_pour_liters)))
