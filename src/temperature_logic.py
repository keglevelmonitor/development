# keglevel app
#
# temperature_logic.py
import time
import threading
import json
import os
import glob
from datetime import datetime, timedelta

class TemperatureLogic:
    
    def __init__(self, ui_callbacks, settings_manager):
        self.ui_callbacks = ui_callbacks
        self.settings_manager = settings_manager

        self.ambient_sensor = None
        self._temp_thread = None
        self._running = False
        self._stop_event = threading.Event()
        self.last_known_temp_f = None
        self.last_update_time = None
        
        # --- CRITICAL PATH FIX: Use SettingsManager's resolved data_dir ---
        base_dir = self.settings_manager.get_data_dir()
        self.log_file = os.path.join(base_dir, "temperature_log.json")
        # --- END FIX ---
        
        self.log_data = {
            "daily_log": [],      
            "weekly_log": [],     
            "monthly_log": [],    
            "high_low_avg": {
                "day": {"high": None, "low": None, "avg": None, "last_updated": None},
                "week": {"high": None, "low": None, "avg": None, "last_updated": None},
                "month": {"high": None, "low": None, "avg": None, "last_updated": None},
            }
        }
        self._load_log_data()

    def reset_log(self):
        """Clears all in-memory log data and saves the reset log to file."""
        self.log_data = {
            "daily_log": [],
            "weekly_log": [],
            "monthly_log": [],
            "high_low_avg": {
                "day": {"high": None, "low": None, "avg": None, "last_updated": None},
                "week": {"high": None, "low": None, "avg": None, "last_updated": None},
                "month": {"high": None, "low": None, "avg": None, "last_updated": None},
            }
        }
        self._save_log_data()
        print("TemperatureLogic: Temperature log has been reset.")


    def _find_sensor(self):
        pass

    def get_assigned_sensor(self):
        """Gets the assigned ambient sensor ID based on settings."""
        self.ambient_sensor = self.settings_manager.get_system_settings().get('ds18b20_ambient_sensor', None)
        
        if not self.ambient_sensor or self.ambient_sensor == 'unassigned':
            print("TemperatureLogic: No ambient sensor assigned or found.")
            
    def detect_ds18b20_sensors(self):
        """Finds all available DS18B20 sensors and returns their IDs by reading the filesystem."""
        base_dir = '/sys/bus/w1/devices/'
        device_folders = glob.glob(base_dir + '28-*')
        return [os.path.basename(f) for f in device_folders]

    def _read_temp_from_id(self, sensor_id):
        """Reads the temperature from a sensor given its ID."""
        if not sensor_id or sensor_id == 'unassigned':
            return None

        device_folder = f'/sys/bus/w1/devices/{sensor_id}/'
        device_file = device_folder + 'w1_slave'

        if not os.path.exists(device_file):
            print(f"TemperatureLogic: Sensor file not found for ID {sensor_id}.")
            return None

        try:
            with open(device_file, 'r') as f:
                lines = f.readlines()
            
            while lines[0].strip()[-3:] != 'YES':
                time.sleep(0.2)
                with open(device_file, 'r') as f:
                    lines = f.readlines()
            
            equals_pos = lines[1].find('t=')
            if equals_pos != -1:
                temp_string = lines[1][equals_pos+2:]
                temp_c = float(temp_string) / 1000.0
                temp_f = temp_c * 9.0 / 5.0 + 32.0
                return temp_f
            
        except Exception as e:
            print(f"TemperatureLogic: Error reading temperature from sensor {sensor_id}: {e}")
            return None
        
        return None

    def start_monitoring(self):
        if not self._running:
            self._running = True
            self.get_assigned_sensor()
            if self.ambient_sensor:
                self._temp_thread = threading.Thread(target=self._monitor_loop, daemon=True)
                self._temp_thread.start()
                print("TemperatureLogic: Monitoring thread started.")
            else:
                print("TemperatureLogic: Cannot start monitoring, no ambient sensor assigned.")
                self.ui_callbacks.get("update_temp_display_cb")(None, "No Sensor")

    def stop_monitoring(self):
        if self._running:
            self._running = False
            self._stop_event.set()
            if self._temp_thread and self._temp_thread.is_alive():
                print("TemperatureLogic: Waiting for thread to stop...")
                self._temp_thread.join(timeout=2)
                if self._temp_thread.is_alive():
                    print("TemperatureLogic: Thread did not stop gracefully.")
                else:
                    print("TemperatureLogic: Thread stopped.")

    def _monitor_loop(self):
        while self._running:
            try:
                amb_temp_f = self.read_ambient_temperature()
                
                if amb_temp_f is not None:
                    self.last_known_temp_f = amb_temp_f
                    
                    display_units = self.settings_manager.get_display_units()
                    if display_units == "imperial":
                        self.ui_callbacks.get("update_temp_display_cb")(amb_temp_f, "F")
                    else:
                        temp_c = (amb_temp_f - 32) * (5/9)
                        self.ui_callbacks.get("update_temp_display_cb")(temp_c, "C")
                    self._log_temperature_reading(amb_temp_f)
                else:
                    self.last_known_temp_f = None
                    self.ui_callbacks.get("update_temp_display_cb")(None, "No Sensor")
                
                self._stop_event.wait(300)

            except Exception as e:
                print(f"TemperatureLogic: Error in monitor loop: {e}")
                self.last_known_temp_f = None
                self.ui_callbacks.get("update_temp_display_cb")(None, "Error")

        print("TemperatureLogic: Monitor loop ended.")

    def _load_log_data(self):
        """Loads log data from the JSON file."""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r') as f:
                    self.log_data = json.load(f)
                    for key in ["day", "week", "month"]:
                        if self.log_data["high_low_avg"][key]["last_updated"]:
                            self.log_data["high_low_avg"][key]["last_updated"] = datetime.fromisoformat(self.log_data["high_low_avg"][key]["last_updated"])
                print(f"TemperatureLogic: Log data loaded from {self.log_file}.")
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                print(f"TemperatureLogic: Error loading log data from file: {e}. Starting with new log.")

    def _save_log_data(self):
        """Saves log data to the JSON file."""
        try:
            data_to_save = self.log_data.copy()
            for key in ["day", "week", "month"]:
                if data_to_save["high_low_avg"][key]["last_updated"]:
                    data_to_save["high_low_avg"][key]["last_updated"] = data_to_save["high_low_avg"][key]["last_updated"].isoformat()
            
            with open(self.log_file, 'w') as f:
                json.dump(data_to_save, f, indent=4)
            print(f"TemperatureLogic: Log data saved to {self.log_file}.")
        except Exception as e:
            print(f"TemperatureLogic: Error saving log data: {e}")

    def _log_temperature_reading(self, temp_f):
        """Adds a new temperature reading to the in-memory log and triggers a save."""
        now = datetime.now()
        timestamp = now.isoformat()
        
        self.log_data["daily_log"].append({"timestamp": timestamp, "temp_f": temp_f})
        self.log_data["weekly_log"].append({"timestamp": timestamp, "temp_f": temp_f})
        self.log_data["monthly_log"].append({"timestamp": timestamp, "temp_f": temp_f})

        self._prune_logs(now)
        self._calculate_stats_and_update_log()
        self._save_log_data()

    def _prune_logs(self, now):
        """Removes old entries from the in-memory log data."""
        self.log_data["daily_log"] = [
            e for e in self.log_data["daily_log"]
            if datetime.fromisoformat(e["timestamp"]) >= now - timedelta(days=1)
        ]
        self.log_data["weekly_log"] = [
            e for e in self.log_data["weekly_log"]
            if datetime.fromisoformat(e["timestamp"]) >= now - timedelta(weeks=1)
        ]
        self.log_data["monthly_log"] = [
            e for e in self.log_data["monthly_log"]
            if datetime.fromisoformat(e["timestamp"]) >= now - timedelta(days=30)
        ]

    def _calculate_stats(self, log_list):
        """Calculates high, low, and average from a list of readings."""
        if not log_list:
            return None, None, None
        
        temps = [e["temp_f"] for e in log_list]
        return max(temps), min(temps), sum(temps) / len(temps)

    def _calculate_stats_and_update_log(self):
        """Calculates and updates stats for day, week, and month."""
        now = datetime.now()
        
        high_day, low_day, avg_day = self._calculate_stats(self.log_data["daily_log"])
        self.log_data["high_low_avg"]["day"] = {"high": high_day, "low": low_day, "avg": avg_day, "last_updated": now}
        
        high_week, low_week, avg_week = self._calculate_stats(self.log_data["weekly_log"])
        self.log_data["high_low_avg"]["week"] = {"high": high_week, "low": low_week, "avg": avg_week, "last_updated": now}
        
        high_month, low_month, avg_month = self._calculate_stats(self.log_data["monthly_log"])
        self.log_data["high_low_avg"]["month"] = {"high": high_month, "low": low_month, "avg": avg_month, "last_updated": now}

    def get_temperature_log(self):
        """Returns the current log data for display."""
        display_units = self.settings_manager.get_display_units()
        log_data_copy = {
            "day": self.log_data["high_low_avg"]["day"].copy(),
            "week": self.log_data["high_low_avg"]["week"].copy(),
            "month": self.log_data["high_low_avg"]["month"].copy(),
        }

        if display_units == "metric":
            for period in ["day", "week", "month"]:
                for stat in ["high", "low", "avg"]:
                    if log_data_copy[period][stat] is not None:
                        temp_f = log_data_copy[period][stat]
                        log_data_copy[period][stat] = (temp_f - 32) * (5/9)
        
        return log_data_copy

    def read_ambient_temperature(self):
        """Reads the temperature from the assigned ambient sensor."""
        if self.ambient_sensor:
            temp_f = self._read_temp_from_id(self.ambient_sensor)
            return temp_f
        return None
