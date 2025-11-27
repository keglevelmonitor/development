"""
fermvault app
settings_manager.py
"""

import json
import os
import time
import uuid
import sys 
import hmac
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
import threading 

# --- MODIFIED: Use the filename from our plan ---
SETTINGS_FILE = "fermvault_settings.json"
# --- MODIFIED: Removed BREW_SESSIONS_FILE (it's saved in the main settings) ---

# --- CONTROL MODE DEFAULTS ---
DEFAULT_CONTROL_MODE = "Beer Hold"
DEFAULT_AMBIENT_HOLD_F = 37.0
DEFAULT_BEER_HOLD_F = 55.0
DEFAULT_RAMP_UP_HOLD_F = 68.0
DEFAULT_RAMP_UP_DURATION_HOURS = 30.0
DEFAULT_FAST_CRASH_HOLD_F = 34.0
# --- END CONTROL MODE DEFAULTS ---


class SettingsManager:
    
    # --- DEFAULT STRUCTURES ---
    def _get_default_settings(self):
        """Assembles the complete default settings dictionary."""
        return {
            "control_settings": self._get_default_control_settings(),
            "notification_settings": self._get_default_notification_settings(),
            "smtp_settings": self._get_default_smtp_settings(),
            "status_request_settings": self._get_default_status_request_settings(),
            "api_settings": self._get_default_api_settings(),
            "compressor_protection_settings": self._get_default_compressor_protection_settings(),
            "system_settings": self._get_default_system_settings()
        }

    def _get_default_control_settings(self):
        return {
            "control_mode": DEFAULT_CONTROL_MODE,
            "ambient_hold_f": DEFAULT_AMBIENT_HOLD_F,
            "beer_hold_f": DEFAULT_BEER_HOLD_F,
            "ramp_up_hold_f": DEFAULT_RAMP_UP_HOLD_F,
            "ramp_up_duration_hours": DEFAULT_RAMP_UP_DURATION_HOURS,
            "fast_crash_hold_f": DEFAULT_FAST_CRASH_HOLD_F,
            "temp_units": "F", # F or C
        }

    # FIXED
    def _get_default_system_settings(self):
        return {
            # "license_key": "" <-- REMOVED
            "controlled_shutdown": False,
            "ds18b20_ambient_sensor": "unassigned",
            "ds18b20_beer_sensor": "unassigned",
            
            # --- NEW: Relay Logic Defaults ---
            "relay_logic_configured": False, # Forces wizard on first run
            "relay_active_high": False,      # Default to Active Low (Standard)
            # ---------------------------------

            "brew_session_title": "",
            "active_api_service": "OFF",
            "current_brew_session_id": None,
            
            # --- MODIFICATION START: Use the correct Recipe defaults ---
            "brew_sessions_list": [
                "Recipe 1", "Recipe 2", "Recipe 3", "Recipe 4", "Recipe 5",
                "Recipe 6", "Recipe 7", "Recipe 8", "Recipe 9", "Recipe 10",
            ],
            # --- MODIFICATION END ---
            
            # --- MODIFICATION: Added new setting for PID logging ---
            "pid_logging_enabled": False,
            # --- END MODIFICATION ---
            
            # --- MODIFICATION: Added PID parameters ---
            "pid_kp": 2.0,
            "pid_ki": 0.03,
            "pid_kd": 20.0,
            # --- END MODIFICATION ---

            # --- NEW: Added Expert Tuning Parameters ---
            "pid_idle_zone": 0.5,
            "ambient_deadband": 1.0,
            "beer_pid_envelope_width": 1.0,
            "ramp_pre_ramp_tolerance": 0.2,
            "ramp_thermo_deadband": 0.1,
            "ramp_pid_landing_zone": 0.5,
            "crash_pid_envelope_width": 2.0,
            # --- END NEW ---
            
            # --- NEW: Added for EULA/Support Popup ---
            "show_eula_on_launch": True,
            "eula_agreed": False, 
            # --- END NEW ---
            
            # --- FIX: ALL TRANSIENT KEYS MUST BE DEFINED ---
            "beer_temp_actual": "--.-",
            "amb_temp_actual": "--.-",
            "beer_temp_timestamp": "--:--:--",
            "amb_temp_timestamp": "--:--:--",
            "og_timestamp_var": "--:--:--",
            "sg_timestamp_var": "--:--:--",
            
            "amb_min_setpoint": 0.0,
            "amb_max_setpoint": 0.0,
            "beer_setpoint_current": 0.0,
            "amb_target_setpoint": 0.0,
            
            "heat_state": "Heating OFF",
            "cool_state": "Cooling OFF",
            
            # --- NEW KEY: Define the restriction status key ---
            "cool_restriction_status": "",
            # --- END NEW KEY ---
            
            # --- NEW KEY: For sensor errors ---
            "sensor_error_message": "",
            # --- END NEW KEY ---
            
            "cooling_delay_message": "init", # Key for logging
            "monitoring_state": "OFF",
            
            "og_display_var": "-.---",
            "sg_display_var": "-.---",
            
            # --- MODIFICATION: Renamed/Added FG variables ---
            "fg_status_var": "", # This is now the MESSAGE (e.g., "", "Stable")
            "fg_value_var": "-.---",    # This is now the VALUE (e.g., "-.---", "1.010")
            # --- END MODIFICATION ---
            
            # --- NEW: Replaced fan_control_mode with aux_relay_mode ---
            "aux_relay_mode": "Monitoring",
            "fan_state": "Fan OFF", # Transient key for UI display
            # --- END NEW ---
        }
            
    def _get_default_compressor_protection_settings(self):
        # All stored in SECONDS, displayed in MINUTES in UI
        return {
            "cooling_dwell_time_s": 180, # 3 minutes
            "max_cool_runtime_s": 7200,    # 120 minutes (2 hours)
            "fail_safe_shutdown_time_s": 3600, # 60 minutes (1 hour rest)
        }

    def _get_default_notification_settings(self):
        # This replaces push_notification_settings and conditional_notification_settings
        return {
            # Push Notification Settings (0 = Disabled/None)
            "frequency_hours": 0, # 0 (None), 1, 2, 4, 8, 12, 24
            
            # --- NEW: Conditional Notification Settings ---
            "conditional_enabled": False,
            "conditional_amb_min": 32.0, # Stored in Fahrenheit
            "conditional_amb_max": 85.0, # Stored in Fahrenheit
            "conditional_beer_min": 32.0, # Stored in Fahrenheit
            "conditional_beer_max": 75.0, # Stored in Fahrenheit
            "conditional_fg_stable": False,
            "conditional_amb_sensor_lost": False,
            "conditional_beer_sensor_lost": False
        }
        
    def _get_default_smtp_settings(self):
        return {
            "server_email": "", "server_password": "", "email_recipient": "",
            "smtp_server": "", "smtp_port": 587,
            # --- MODIFICATION: Removed SMS keys ---
        }

    def _get_default_api_settings(self):
        return {
            "active_api_service": "OFF",
            "api_key": "",
            "api_call_frequency_s": 1200, # 20 minutes
            
            # --- NEW: Added for UI logging toggle ---
            "api_logging_enabled": False,
            # --- END NEW ---
            
            "fg_check_frequency_h": 24, # 24 hours
            # FG Calculation Parameters
            "tolerance": 0.0005,
            "window_size": 450,
            "max_outliers": 4,
        }
        
    def _get_default_status_request_settings(self):
        return {
            "enable_status_request": False,
            "authorized_sender": "",
            "rpi_email_address": "",
            "rpi_email_password": "",
            "imap_server": "",
            "imap_port": 993,
        }
    
    def _get_default_brew_session_settings(self):
        # Manually entered sessions for API OFF mode fallback
        return [
            "Recipe 1", "Recipe 2", "Recipe 3", "Recipe 4", "Recipe 5",
            "Recipe 6", "Recipe 7", "Recipe 8", "Recipe 9", "Recipe 10",
        ]
    
    # --- INITIALIZATION ---
    def __init__(self, settings_file_path=None):
        
        # --- MODIFICATION: Define the user data directory ---
        self.data_dir = os.path.join(os.path.expanduser('~'), 'fermvault-data')
        
        # --- NEW PRINT FOR DEBUGGING ---
        print(f"[DEBUG] SettingsManager: Target data directory is {self.data_dir}")
        # --- END NEW PRINT ---
        
        # --- MODIFICATION: Ensure this directory exists (SAFTEY CHECK) ---
        try:
            os.makedirs(self.data_dir, exist_ok=True)
        except OSError as e:
            # If the initial creation fails, log it
            print(f"[ERROR] SettingsManager: Initial creation of data directory failed: {e}")
        
        # --- MODIFICATION: Set the settings file path to be *inside* the data_dir ---
        self.settings_file = settings_file_path or os.path.join(self.data_dir, SETTINGS_FILE)
        # --- END MODIFICATIONS ---
        
        self.settings = {}
        self._data_lock = threading.RLock()
        
        self.brew_sessions = [""] * 10
        
        self.was_controlled_shutdown = False

        # Load all settings
        self._load_settings()


    # FIXED
    def _load_settings(self):
        try:
            with self._data_lock:
                # 1. Check if the file exists in the desired new location
                if not os.path.exists(self.settings_file):
                    # 2. If not, create the entire directory structure *before* writing
                    os.makedirs(self.data_dir, exist_ok=True) 

                    print(f"[SettingsManager] No settings file found at {self.settings_file}. Creating new one with defaults.")
                    self.settings = self._get_default_settings()
                    self._save_all_settings() # This performs the first write to the correct path
                else:
                    with open(self.settings_file, 'r') as f:
                        self.settings = json.load(f)
                    
                    # --- FIX: Ensure all default categories exist ---
                    default_settings = self._get_default_settings()
                    for key, value in default_settings.items():
                        if key not in self.settings:
                            self.settings[key] = value
                        # Ensure nested dicts (like system_settings) have all keys
                        elif isinstance(value, dict):
                            for sub_key, sub_value in value.items():
                                if sub_key not in self.settings[key]:
                                    
                                    # --- MIGRATION LOGIC START ---
                                    # If 'relay_logic_configured' is missing from an EXISTING file, it means
                                    # the user is updating from an older version. The older version ONLY supported
                                    # Active Low. Therefore, we force them to "Configured + Active Low".
                                    if sub_key == "relay_logic_configured":
                                        print("[SettingsManager] Migrating legacy user: Defaulting to Active Low logic.")
                                        self.settings[key][sub_key] = True # Force 'Configured' to skip wizard
                                    else:
                                        # For all other missing keys (including relay_active_high), use the default.
                                        # Default for relay_active_high is False (Active Low), which is correct.
                                        self.settings[key][sub_key] = sub_value
                                    # --- MIGRATION LOGIC END ---
                                    
                # --- MODIFICATION START: Load brew sessions from main settings ---
                self.brew_sessions = self.settings['system_settings'].get('brew_sessions_list', [""] * 10)
                # --- MODIFICATION END ---
                
                # --- MODIFICATION: Capture shutdown state *before* resetting it ---
                # 1. Read the value that was loaded from the JSON file
                self.was_controlled_shutdown = self.settings.get('system_settings', {}).get('controlled_shutdown', False)
                # 2. Now, reset the flag to False for the *current* session
                self.settings['system_settings']['controlled_shutdown'] = False
                # --- END MODIFICATION ---

        except Exception as e:
            # --- MODIFICATION: Updated error message ---
            print(f"[ERROR] Critical error loading {self.settings_file}; default settings loaded")
            # --- END MODIFICATION ---
            self.settings = self._get_default_settings()
            # --- MODIFICATION START: Load default brew sessions ---
            self.brew_sessions = self.settings['system_settings'].get('brew_sessions_list', [""] * 10)
            # --- MODIFICATION END ---
            # --- MODIFICATION: Ensure reset on critical error ---
            self.was_controlled_shutdown = False
            self.settings['system_settings']['controlled_shutdown'] = False
            # --- END MODIFICATION ---

    def _save_all_settings(self):
        try:
            with self._data_lock:
                # --- MODIFICATION: File path is now correct from __init__ ---
                with open(self.settings_file, 'w') as f:
                    json.dump(self.settings, f, indent=4)
            # --- MODIFICATION START: Remove comment ---
            # (Brew sessions are now saved with all settings)
            # --- MODIFICATION END ---
        except Exception as e:
            print(f"[ERROR] Failed to save settings to {self.settings_file}: {e}")

    # ... (rest of the file is unchanged and correct) ...
    
    def save_brew_sessions(self, sessions_list):
        """Saves the brew session list directly to the main settings file."""
        # 1. Update the main settings dictionary in memory
        self.settings['system_settings']['brew_sessions_list'] = sessions_list
        
        # 2. Update the instance attribute
        self.brew_sessions = sessions_list
        
        # 3. Save all settings to the main vault_settings.json
        self._save_all_settings()
        print("[SettingsManager] Brew sessions list saved to vault_settings.json.")
        
    def reset_all_settings_to_defaults(self):
        # Reset all internal settings and save
        # --- MODIFICATION: Call _get_default_settings() directly ---
        self.settings = self._get_default_settings()
        # --- END MODIFICATION ---
        self.brew_sessions = self._get_default_brew_session_settings()
        self._save_all_settings()
        self.save_brew_sessions(self.brew_sessions)
        print("SettingsManager: All settings reset to defaults.")

    # --- GENERAL SETTERS/GETTERS ---
    
    # --- MODIFICATION: Add new getter ---
    def get_last_shutdown_status(self):
        """Returns True if the last shutdown was controlled, False otherwise."""
        return self.was_controlled_shutdown
    # --- END MODIFICATION ---
    
    def get(self, key, default=None):
        # A simplified getter that flattens the nested dictionaries for easy access
        # --- FIX: Acquire lock for safe read from multiple threads ---
        with self._data_lock:
            for category in self.settings.values():
                if isinstance(category, dict) and key in category:
                    return category[key]
        return default

    def set(self, key, value):
        # A simplified setter that finds the key in nested dictionaries and updates it
        # --- FIX: Acquire lock for safe write from multiple threads ---
        with self._data_lock:
            for category_name, category_data in self.settings.items():
                if isinstance(category_data, dict) and key in category_data:
                    category_data[key] = value
                    
                    # --- CRITICAL FIX: Only save persistent settings to disk (avoiding disk I/O in the monitor loop) ---
                    transient_keys = [
                        "beer_temp_actual", "amb_temp_actual", "beer_temp_timestamp", "amb_temp_timestamp", 
                        "og_timestamp_var", "sg_timestamp_var",
                        "amb_min_setpoint", "amb_max_setpoint", "beer_setpoint_current", "amb_target_setpoint",
                        "heat_state", "cool_state", 
                        
                        # --- NEW KEY: Add the restriction status key ---
                        "cool_restriction_status", 
                        # --- END NEW KEY ---
                        
                        # --- NEW KEY: Add sensor error message ---
                        "sensor_error_message",
                        # --- END NEW KEY ---

                        "cooling_delay_message", "fan_state", "monitoring_state",
                        "og_display_var", "sg_display_var", 
                        
                        # --- MODIFICATION: Added FG vars ---
                        "fg_status_var", "fg_value_var"
                        # --- END MODIFICATION ---
                    ]
                    
                    if key not in transient_keys:
                         self._save_all_settings() # Save persistent data to disk
                    # Transient data is only updated in memory, which is what the monitoring loop needs.
                    return True
        
        # If key was not found, log an error
        print(f"[ERROR] SettingsManager: Key '{key}' not found in any category. Set failed.")
        return False
        
    # --- SPECIFIC GETTERS/SETTERS (Used by UI/Controller/Notifications) ---
    
    def get_system_settings(self):
        """Retrieves system and manually stored sensor settings needed for the UI."""
        # --- FIX: Acquire lock for safe read ---
        with self._data_lock:
            settings = self.settings['system_settings'].copy()
            return settings
        
    def get_all_control_settings(self):
        with self._data_lock: # FIX: Acquire lock
            # Ensure a copy is returned for thread safety if it were to be modified later
            return self.settings['control_settings'].copy()

    def save_control_settings(self, new_settings):
        # Assumes new_settings contains all keys from _get_default_control_settings
        with self._data_lock: # FIX: Acquire lock
            self.settings['control_settings'].update(new_settings)
            self._save_all_settings()

    def get_all_smtp_settings(self):
        with self._data_lock: # FIX: Acquire lock
            return self.settings['smtp_settings'].copy()

    def get_all_status_request_settings(self):
        with self._data_lock: # FIX: Acquire lock
            return self.settings['status_request_settings'].copy()
        
    def save_status_request_settings(self, new_settings):
        # Assumes new_settings contains all keys from _get_default_status_request_settings
        with self._data_lock: # FIX: Acquire lock
            self.settings['status_request_settings'].update(new_settings)
            self.settings['smtp_settings']['smtp_server'] = new_settings.get('smtp_server', self.settings['smtp_settings']['smtp_server'])
            self.settings['smtp_settings']['smtp_port'] = new_settings.get('smtp_port', self.settings['smtp_settings']['smtp_port'])
            self._save_all_settings()

    def get_all_api_settings(self):
        with self._data_lock: # FIX: Acquire lock
            return self.settings['api_settings'].copy()
        
    def save_api_settings(self, new_settings):
        # Assumes new_settings contains all keys from _get_default_api_settings
        with self._data_lock: # FIX: Acquire lock
            self.settings['api_settings'].update(new_settings)
            self._save_all_settings()

    def get_all_compressor_protection_settings(self):
        with self._data_lock: # FIX: Acquire lock
            return self.settings['compressor_protection_settings'].copy()
        
    def save_compressor_protection_settings(self, new_settings):
        with self._data_lock: # FIX: Acquire lock
            self.settings['compressor_protection_settings'].update(new_settings)
            self._save_all_settings()
        
    def set_controlled_shutdown(self, is_controlled):
        with self._data_lock: # FIX: Acquire lock
            self.settings['system_settings']['controlled_shutdown'] = is_controlled
            self._save_all_settings()

    def set_temp_for_mode_override(self, key, value):
        """Used by Ramp-Up logic to update the PID target temporarily without saving."""
        with self._data_lock: # FIX: Acquire lock
            if key in self.settings['control_settings']:
                 self.settings['control_settings'][key] = value
            # Note: No save to disk is performed here.
