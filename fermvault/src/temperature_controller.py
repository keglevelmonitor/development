"""
fermvault app
temperature_controller.py
"""

import requests
import json
import threading
import time
from datetime import datetime
import glob
import os
import csv

# --- PID CLASS DEFINITION ---
class PID:
    def __init__(self, Kp, Ki, Kd, setpoint):
        self.Kp = Kp; self.Ki = Ki; self.Kd = Kd; self.setpoint = setpoint
        self._last_error = 0; self._integral = 0

    def update(self, process_variable, dt):
        error = self.setpoint - process_variable
        self._integral += error * dt
        i_term = self.Ki * self._integral
        derivative = (error - self._last_error) / dt
        p_term = self.Kp * error
        d_term = self.Kd * derivative
        self._last_error = error
        return p_term + i_term + d_term

    def set_setpoint(self, setpoint):
        self.setpoint = setpoint
        self._integral = 0
        self._last_error = 0
# --- END PID CLASS DEFINITION ---
        
class TemperatureController:
    
    def __init__(self, settings_manager, relay_control):
        self.settings_manager = settings_manager
        self.relay_control = relay_control
        self.notification_manager = None
        
        # --- MODIFICATION: Read PID values from settings ---
        kp = self.settings_manager.get("pid_kp", 2.0)
        ki = self.settings_manager.get("pid_ki", 0.03)
        kd = self.settings_manager.get("pid_kd", 20.0)
        
        self.pid = PID(Kp=kp, Ki=ki, Kd=kd, setpoint=0.0) 
        print(f"[TempController] PID initialized with Kp={kp}, Ki={ki}, Kd={kd}")
        # --- END MODIFICATION ---
        
        self.last_pid_update_time = time.time()
        
        self._monitoring = False
        self._monitor_thread = None
        self._stop_event = threading.Event()
        
        # --- NEW: Sensor state tracking for latched logging ---
        self._beer_sensor_ok = True
        self._amb_sensor_ok = True
        self._fail_safe_logged = False
        # --- END NEW ---
        
        # --- MODIFICATION: Expanded ramp_state for pre-condition ---
        self.ramp_state = {
            "current_target": 0.0, 
            "last_step_time": 0.0, 
            "start_time": 0.0, 
            "is_finished": False,
            "is_in_pre_ramp": True,     # NEW: Flag for pre-condition state
            "ramp_logging_done": False  # NEW: Flag to log messages only once
        }
        # --------------------------------------------------------
        
        # --- MODIFICATION: Define the data directory for logging ---
        self.data_dir = os.path.join(os.path.expanduser('~'), 'fermvault-data')
        # --- END MODIFICATION ---

    # --- MODIFICATION: Added _log_pid_data function ---
    def _log_pid_data(self, setpoint, measured_temp, pid_output, amb_min, amb_max):
        """Logs PID tuning data to a CSV file if enabled in settings."""
        
        # Guard clause: Check if logging is enabled
        if not self.settings_manager.get("pid_logging_enabled", False):
            return
            
        try:
            # 1. Ensure data directory exists
            os.makedirs(self.data_dir, exist_ok=True)
            
            # 2. Define the log file path
            log_file_path = os.path.join(self.data_dir, "pid_tuning_log.csv")

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file_exists = os.path.isfile(log_file_path)
            
            # Get relay states and control mode
            cool_state = "ON" if "COOLING" in self.settings_manager.get("cool_state") else "OFF"
            heat_state = "ON" if "HEATING" in self.settings_manager.get("heat_state") else "OFF"
            control_mode = self.settings_manager.get("control_mode", "Unknown")

            # 3. CRITICAL: File Writing Block
            with open(log_file_path, 'a', newline='') as csvfile:
                # Use csv.DictWriter
                fieldnames = ['Timestamp', 'ControlMode', 'BeerSetpoint', 'MeasuredBeerTemp', 'PID_Output', 'AmbientSetpoint_Min', 'AmbientSetpoint_Max', 'CoolState', 'HeatState']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                if not file_exists:
                    writer.writeheader()
                
                writer.writerow({
                    'Timestamp': timestamp,
                    'ControlMode': control_mode,
                    'BeerSetpoint': f"{setpoint:.2f}",
                    'MeasuredBeerTemp': f"{measured_temp:.3f}",
                    'PID_Output': f"{pid_output:.4f}",
                    'AmbientSetpoint_Min': f"{amb_min:.2f}",
                    'AmbientSetpoint_Max': f"{amb_max:.2f}",
                    'CoolState': cool_state,
                    'HeatState': heat_state
                })
        
        # 4. CRITICAL: Error Handling Block (Catches I/O errors and reports to UI)
        except (PermissionError, IOError) as e:
            # This handles failed folder creation, file writing, or permission issues
            log_msg = f"[CRITICAL ERROR] Failed to write PID log. Check permissions for: {self.data_dir}. Error: {e}"
            print(log_msg)
            
            # Log to UI on the main thread
            if self.notification_manager and self.notification_manager.ui:
                self.notification_manager.ui.log_system_message(log_msg)
                
        except Exception as e:
            # Handle any other unexpected errors
            log_msg = f"[ERROR] Failed to write to PID log file: {e}"
            print(log_msg)
            if self.notification_manager and self.notification_manager.ui:
                self.notification_manager.ui.log_system_message(log_msg)
                
    # --- SENSOR READING ---
    def _read_temp_from_id(self, sensor_id):
        """Reads the temperature from a DS18B20 sensor given its ID (in Fahrenheit)."""
        # Removed the 'is_hardware_available' check, assuming hardware is present.
        if not sensor_id or sensor_id == 'unassigned':
            return None 

        device_file = f'/sys/bus/w1/devices/{sensor_id}/w1_slave'
        if not os.path.exists(device_file): return None
        
        try:
            with open(device_file, 'r') as f: lines = f.readlines()
            if lines[0].strip()[-3:] != 'YES': return None
            
            equals_pos = lines[1].find('t=')
            if equals_pos != -1:
                temp_string = lines[1][equals_pos+2:]
                temp_c = float(temp_string) / 1000.0
                temp_f = temp_c * 9.0 / 5.0 + 32.0
                return temp_f
            
        except Exception as e:
            print(f"TemperatureController: Error reading sensor {sensor_id}: {e}")
        return None

    def read_ambient_temperature(self):
        """Reads the ambient temperature (F) from the assigned sensor."""
        sensor_id = self.settings_manager.get("ds18b20_ambient_sensor", "unassigned")
        # --- FIX: Return None if unassigned, not a mock value ---
        if sensor_id == 'unassigned': return None 
        # --- END FIX ---
        return self._read_temp_from_id(sensor_id)

    def read_beer_temperature(self):
        """Reads the beer temperature (F) from the assigned sensor."""
        sensor_id = self.settings_manager.get("ds18b20_beer_sensor", "unassigned") 
        # --- FIX: Return None if unassigned, not a mock value ---
        if sensor_id == 'unassigned': return None 
        # --- END FIX ---
        return self._read_temp_from_id(sensor_id)

    def detect_ds18b20_sensors(self):
        """Finds all available DS18B20 sensors (for settings popup)."""
        # Removed 'is_hardware_available' check
        base_dir = '/sys/bus/w1/devices/'
        device_folders = glob.glob(base_dir + '28-*')
        return [os.path.basename(f) for f in device_folders]

    # --- CONTROL MODES (Logic only, no GPIO or Safety enforcement) ---

    def reset_ramp_state(self):
        """Resets the internal ramp state variables."""
        print("Ramp state reset by UI.")
        # --- MODIFICATION: Reset the new, full ramp state ---
        self.ramp_state = {
            "current_target": 0.0, 
            "last_step_time": 0.0, 
            "start_time": 0.0, 
            "is_finished": False,
            "is_in_pre_ramp": True,
            "ramp_logging_done": False
        }
        # ----------------------------------------------------

    def ambient_hold_logic(self, amb_temp):
        """Controls Ambient Temp to the Ambient Hold Setpoint (Simple Thermostat)."""
        target_amb_temp = self.settings_manager.get("ambient_hold_f", 37.0) 
        DEADBAND = self.settings_manager.get("ambient_deadband", 1.0) # <-- MODIFIED
        amb_min = target_amb_temp - DEADBAND
        amb_max = target_amb_temp + DEADBAND
        return amb_min, amb_max

    def beer_hold_logic(self, beer_temp, amb_temp):
        """Controls Beer Temp to the Beer Hold Setpoint (PID-Assisted)."""
        target_beer_temp = self.settings_manager.get("beer_hold_f", 55.0)
        self.pid.set_setpoint(target_beer_temp)
        dt = time.time() - self.last_pid_update_time
        self.last_pid_update_time = time.time()
        
        IDLE_ZONE = self.settings_manager.get("pid_idle_zone", 0.5) # <-- MODIFIED
        if abs(beer_temp - target_beer_temp) <= IDLE_ZONE:
            self.pid._integral = 0

        pid_output = self.pid.update(beer_temp, dt)
        
        ambient_setpoint = target_beer_temp + pid_output
        
        ENVELOPE_WIDTH = self.settings_manager.get("beer_pid_envelope_width", 1.0) # <-- MODIFIED
        amb_min = ambient_setpoint - ENVELOPE_WIDTH
        amb_max = ambient_setpoint + ENVELOPE_WIDTH
        
        amb_min = max(-10.0, min(100.0, amb_min))
        amb_max = max(-10.0, min(100.0, amb_max))
        
        # --- MODIFICATION: Call logging function ---
        self._log_pid_data(target_beer_temp, beer_temp, pid_output, amb_min, amb_max)
        # --- END MODIFICATION ---

        return amb_min, amb_max
        
    def ramp_up_logic(self, beer_temp, amb_temp):
        """
        Controls beer temp in three stages:
        1. [Pre-Ramp]: Holds at start_temp until beer is stable (PID).
        2. [Main Ramp]: Thermostatically forces beer to follow the moving target.
        3. [PID Landing]: Switches back to PID to "soft land" at the end_temp.
        """
        start_temp = self.settings_manager.get("beer_hold_f", 55.0)
        end_temp = self.settings_manager.get("ramp_up_hold_f", 68.0)
        duration_hours = self.settings_manager.get("ramp_up_duration_hours", 30.0)
        
        # --- NEW: Define the new tolerance zones ---
        PRE_RAMP_TOLERANCE = self.settings_manager.get("ramp_pre_ramp_tolerance", 0.2) # <-- MODIFIED
        END_RAMP_PID_ZONE = self.settings_manager.get("ramp_pid_landing_zone", 0.5)  # <-- MODIFIED
        # --- END NEW ---

        # --- Ramp Increment Logic (Moved to top) ---
        current_time = time.time()
        
        # Check if ramp is finished
        if self.ramp_state["is_finished"]:
             self.ramp_state["current_target"] = end_temp
        
        # Check if ramp is in progress and duration is valid
        elif duration_hours > 0:
            time_elapsed_seconds = current_time - self.ramp_state["start_time"]
            total_duration_seconds = duration_hours * 3600
            
            if time_elapsed_seconds >= total_duration_seconds:
                # Ramp is finished
                self.ramp_state["current_target"] = end_temp
                self.ramp_state["is_finished"] = True
            else:
                # Ramp is in progress, calculate new target
                total_rise = end_temp - start_temp
                fraction_complete = time_elapsed_seconds / total_duration_seconds
                increment = total_rise * fraction_complete
                self.ramp_state["current_target"] = start_temp + increment
        
        else: # duration_hours is 0 or less, just hold at end_temp
             self.ramp_state["current_target"] = end_temp
             self.ramp_state["is_finished"] = True
             
        # Get the continuously updating moving target
        target_beer_temp = self.ramp_state["current_target"]
        
        # --- STATE 1: Pre-Ramp (Waiting to hit start temp) ---
        if self.ramp_state["is_in_pre_ramp"]:
            
            # Log the pre-condition message (once)
            if not self.ramp_state["ramp_logging_done"]:
                if self.notification_manager and self.notification_manager.ui:
                    self.notification_manager.ui.log_system_message("Ramp pre-condition: bringing beer to setpoint before starting ramp.")
                self.ramp_state["ramp_logging_done"] = True # Mark as logged

            # Calculate PID for a simple hold at the start_temp
            self.pid.set_setpoint(start_temp) # Hold at START temp
            
            dt = current_time - self.last_pid_update_time
            self.last_pid_update_time = current_time
            IDLE_ZONE = self.settings_manager.get("pid_idle_zone", 0.5) # <-- MODIFIED
            if abs(beer_temp - start_temp) <= IDLE_ZONE: self.pid._integral = 0
            pid_output = self.pid.update(beer_temp, dt)
            
            ambient_setpoint = start_temp + pid_output
            ENVELOPE_WIDTH = self.settings_manager.get("beer_pid_envelope_width", 1.0) # <-- MODIFIED
            amb_min = ambient_setpoint - ENVELOPE_WIDTH
            amb_max = ambient_setpoint + ENVELOPE_WIDTH
            
            amb_min = max(-10.0, min(100.0, amb_min))
            amb_max = max(-10.0, min(100.0, amb_max))
            
            # Set the beer message area
            ramp_target_message = "Ramp pre-condition"
            
            # Check for transition to Ramping state
            if abs(beer_temp - start_temp) <= PRE_RAMP_TOLERANCE:
                print("[TempController] Ramp pre-condition met. Starting ramp.")
                self.ramp_state["is_in_pre_ramp"] = False
                self.ramp_state["ramp_logging_done"] = False # Reset logging flag for the *real* ramp
                self.ramp_state["current_target"] = start_temp
                self.ramp_state["last_step_time"] = current_time
                self.ramp_state["start_time"] = current_time
                self.ramp_state["is_finished"] = False
            
            # Return PID-controlled ambient range
            return amb_min, amb_max, ramp_target_message

        # --- Calculate the continuous message for the beer message area ---
        # (Do this after Pre-Ramp so it's available for all other states)
        ramp_target_message = ""
        if self.ramp_state["is_finished"]:
            ramp_target_message = "Ramp Finished"
        else:
            try:
                units = self.settings_manager.get("temp_units", "F")
                ramp_duration_s = duration_hours * 3600
                end_timestamp = self.ramp_state["start_time"] + ramp_duration_s
                end_dt = datetime.fromtimestamp(end_timestamp)
                end_time_str = end_dt.strftime("%m-%d %H:%M:%S")
                
                end_temp_f = end_temp
                display_end_target = end_temp_f if units == "F" else ((end_temp_f - 32) * 5/9)
                display_end_target_str = f"{display_end_target:.1f}"
                
                ramp_target_message = f"Target {display_end_target_str} {units} at {end_time_str}"
            except Exception:
                ramp_target_message = "Ramping..." # Fallback
                
        # --- STATE 3: PID Landing (Close to end_temp) ---
        # Check if we are in the "soft landing" zone
        if not self.ramp_state["is_finished"] and (end_temp - target_beer_temp) < END_RAMP_PID_ZONE:
            
            # Log ramp landing (once)
            if not self.ramp_state["ramp_logging_done"]:
                if self.notification_manager and self.notification_manager.ui:
                    self.notification_manager.ui.log_system_message("Ramp-Up: Entering final PID landing zone.")
                self.ramp_state["ramp_logging_done"] = True # Mark as logged

            # Use PID to hold the *final* end_temp
            self.pid.set_setpoint(end_temp) 

            dt = current_time - self.last_pid_update_time
            if dt == 0: dt = 1.0 
            self.last_pid_update_time = current_time
            
            IDLE_ZONE = self.settings_manager.get("pid_idle_zone", 0.5) # <-- MODIFIED
            if abs(beer_temp - end_temp) <= IDLE_ZONE:
                self.pid._integral = 0
            
            pid_output = self.pid.update(beer_temp, dt)
            ambient_setpoint = end_temp + pid_output
            
            ENVELOPE_WIDTH = self.settings_manager.get("beer_pid_envelope_width", 1.0) # <-- MODIFIED
            amb_min = ambient_setpoint - ENVELOPE_WIDTH
            amb_max = ambient_setpoint + ENVELOPE_WIDTH

            amb_min = max(-10.0, min(100.0, amb_min))
            amb_max = max(-10.0, min(100.0, amb_max))
            
            self._log_pid_data(end_temp, beer_temp, pid_output, amb_min, amb_max)
            
            # --- MODIFICATION: Override the beer message ---
            ramp_target_message = "Ramp Landing..."
            # --- END MODIFICATION ---
            
            # Return PID-controlled ambient range
            return amb_min, amb_max, ramp_target_message
            
        # --- STATE 2: Main Ramp (Thermostatic) ---
        # This is the default state if not in Pre-Ramp or PID Landing
        
        # Log ramp start (once)
        if not self.ramp_state["ramp_logging_done"]:
            try:
                if self.notification_manager and self.notification_manager.ui:
                    units = self.settings_manager.get("temp_units", "F")
                    
                    # 1. Log Message 1 (Ramp Rate Message)
                    total_rise_f = end_temp - start_temp
                    if duration_hours > 0:
                        total_rise_display = total_rise_f if units == "F" else (total_rise_f * 5/9)
                        rate_per_hour = total_rise_display / duration_hours
                        message_2 = f"Ramp started (Thermostatic): {rate_per_hour:.2f} {units} degree change every hour."
                        self.notification_manager.ui.log_system_message(message_2)
                    
            except Exception as e:
                print(f"[ERROR] Failed to log ramp-up start messages: {e}")
            
            self.ramp_state["ramp_logging_done"] = True # Mark as logged

        # --- CRITICAL: Return (None, None) ---
        # This signals the _monitor_loop to use thermostatic logic.
        return None, None, ramp_target_message
        
    def fast_crash_logic(self, beer_temp, amb_temp):
        """Controls Beer Temp aggressively to the Fast Crash Hold Setpoint (Aggressive PID)."""
        target_crash_temp = self.settings_manager.get("fast_crash_hold_f", 34.0)
        
        self.pid.set_setpoint(target_crash_temp)
        
        dt = time.time() - self.last_pid_update_time
        self.last_pid_update_time = time.time()
        
        IDLE_ZONE = self.settings_manager.get("pid_idle_zone", 0.5) # <-- MODIFIED
        if abs(beer_temp - target_crash_temp) <= IDLE_ZONE:
            self.pid._integral = 0
        
        pid_output = self.pid.update(beer_temp, dt)

        ambient_setpoint = target_crash_temp + pid_output

        ENVELOPE_WIDTH = self.settings_manager.get("crash_pid_envelope_width", 2.0) # <-- MODIFIED
        amb_min = ambient_setpoint - ENVELOPE_WIDTH
        amb_max = ambient_setpoint + ENVELOPE_WIDTH

        amb_min = max(-10.0, min(100.0, amb_min))
        amb_max = max(-10.0, min(100.0, amb_max))
        
        # --- MODIFICATION: Call logging function ---
        self._log_pid_data(target_crash_temp, beer_temp, pid_output, amb_min, amb_max)
        # --- END MODIFICATION ---

        return amb_min, amb_max
        
    # --- MONITORING HELPER (FOR IMMEDIATE UI/Setpoint Update) ---
    def update_control_logic_and_ui_data(self):
        """Forces a single pass of control logic calculation, saves settings, 
        and PUSHES ALL DATA to the UI.
        
        This function is now stateful and includes latched logging.
        It does NOT control relays.
        """
        
        # --- 1. READ SENSORS AND MANAGE LATCHED LOGGING ---
        beer_temp = self.read_beer_temperature()
        amb_temp = self.read_ambient_temperature()
        
        current_beer_ok = (beer_temp is not None)
        current_amb_ok = (amb_temp is not None)
        
        # --- Latching Log Logic (with specific messages) ---
        if self.notification_manager and self.notification_manager.ui:
            # Beer Sensor State Change
            if current_beer_ok and not self._beer_sensor_ok:
                self.notification_manager.ui.log_system_message("Beer sensor re-connected.")
            elif not current_beer_ok and self._beer_sensor_ok:
                if self.settings_manager.get("ds18b20_beer_sensor") == "unassigned":
                    self.notification_manager.ui.log_system_message("Beer sensor is unassigned. Please set in System Settings.")
                else:
                    self.notification_manager.ui.log_system_message("Beer sensor reading failed. Check connection.")
            
            # Ambient Sensor State Change
            if current_amb_ok and not self._amb_sensor_ok:
                self.notification_manager.ui.log_system_message("Ambient sensor re-connected.")
            elif not current_amb_ok and self._amb_sensor_ok:
                if self.settings_manager.get("ds18b20_ambient_sensor") == "unassigned":
                    self.notification_manager.ui.log_system_message("Ambient sensor is unassigned. Please set in System Settings.")
                else:
                    self.notification_manager.ui.log_system_message("Ambient sensor reading failed. Check connection.")
        
        # Update the stored state
        self._beer_sensor_ok = current_beer_ok
        self._amb_sensor_ok = current_amb_ok
        
        # --- Update timestamps in settings ---
        current_time_str = datetime.now().strftime("%H:%M:%S")
        if current_beer_ok:
             self.settings_manager.set("beer_temp_timestamp", current_time_str)
        if current_amb_ok:
             self.settings_manager.set("amb_temp_timestamp", current_time_str)
        
        # --- 2. VALIDATE SENSORS BASED ON CONTROL MODE (with specific messages) ---
        current_mode = self.settings_manager.get("control_mode")
        sensor_error_message = ""
        
        if current_mode == "Ambient Hold":
            if not current_amb_ok:
                if self.settings_manager.get("ds18b20_ambient_sensor") == "unassigned":
                    sensor_error_message = "FAIL: Ambient Sensor Unassigned"
                else:
                    sensor_error_message = "FAIL: Ambient Sensor Missing"
            # Note: A missing beer sensor is logged above, but is not a critical error here.
        
        elif current_mode in ["Beer Hold", "Ramp-Up", "Fast Crash"]:
            if not current_beer_ok and not current_amb_ok:
                sensor_error_message = "FAIL: Both Sensors Failed" # Generic, as this is a total failure
            elif not current_beer_ok:
                if self.settings_manager.get("ds18b20_beer_sensor") == "unassigned":
                    sensor_error_message = "FAIL: Beer Sensor Unassigned"
                else:
                    sensor_error_message = "FAIL: Beer Sensor Missing"
            elif not current_amb_ok:
                if self.settings_manager.get("ds18b20_ambient_sensor") == "unassigned":
                    sensor_error_message = "FAIL: Ambient Sensor Unassigned"
                else:
                    sensor_error_message = "FAIL: Ambient Sensor Missing"
        
        self.settings_manager.set("sensor_error_message", sensor_error_message)

        # --- 3. CALCULATE SETPOINTS (Even if sensors failed) ---
        # These are needed to populate the UI correctly
        
        amb_min, amb_max = 0.0, 0.0
        ambient_target_setpoint = self.settings_manager.get("ambient_hold_f")
        ramp_target_message = ""
        ramp_end_target = 0.0
        ramp_start_time = 0.0
        ramp_is_finished = False

        if current_mode == "Ramp-Up":
            if self._monitoring: # Use live moving target
                beer_setpoint_current = self.ramp_state["current_target"]
            else: # Use starting temp
                beer_setpoint_current = self.settings_manager.get("beer_hold_f")
                
            ramp_end_target = self.settings_manager.get("ramp_up_hold_f")
            ramp_start_time = self.ramp_state["start_time"]
            ramp_is_finished = self.ramp_state["is_finished"]
            # Call ramp_up_logic just to get the correct message
            if current_beer_ok and current_amb_ok:
                 _, _, ramp_target_message = self.ramp_up_logic(beer_temp, amb_temp)
            
        elif current_mode == "Fast Crash":
            beer_setpoint_current = self.settings_manager.get("fast_crash_hold_f")
        else: # Beer Hold, Ambient Hold, or Off
            beer_setpoint_current = self.settings_manager.get("beer_hold_f")

        # --- 4. CHECK FOR FAIL-SAFE AMBIENT MODE ---
        # This condition is (Beer Sensor Failed/Unassigned) AND (Ambient Sensor OK) AND (Mode is "Beer")
        fail_safe_active = ("FAIL: Beer Sensor" in sensor_error_message) and current_amb_ok
        
        if fail_safe_active:
            # We are in fail-safe. Calculate ambient envelope to hold beer setpoint
            target_amb_temp = beer_setpoint_current
            DEADBAND = 1.0 
            amb_min = target_amb_temp - DEADBAND
            amb_max = target_amb_temp + DEADBAND
            
            if not self._fail_safe_logged:
                if self.notification_manager and self.notification_manager.ui:
                    self.notification_manager.ui.log_system_message(f"FAIL-SAFE: Beer sensor failed. Holding chamber at {target_amb_temp:.1f} F.")
                self._fail_safe_logged = True
        
        elif not sensor_error_message:
            # No errors. Calculate logic normally.
            if self._fail_safe_logged:
                if self.notification_manager and self.notification_manager.ui:
                    self.notification_manager.ui.log_system_message("FAIL-SAFE: Beer sensor re-connected. Resuming normal control.")
                self._fail_safe_logged = False
            
            if current_mode == "Ambient Hold": amb_min, amb_max = self.ambient_hold_logic(amb_temp)
            elif current_mode == "Beer Hold": amb_min, amb_max = self.beer_hold_logic(beer_temp, amb_temp)
            elif current_mode == "Ramp-Up": amb_min, amb_max, ramp_target_message = self.ramp_up_logic(beer_temp, amb_temp)
            elif current_mode == "Fast Crash": amb_min, amb_max = self.fast_crash_logic(beer_temp, amb_temp)
        
        else:
            # A different, critical error is active (e.g., Ambient sensor missing/unassigned)
            if self._fail_safe_logged:
                if self.notification_manager and self.notification_manager.ui:
                    self.notification_manager.ui.log_system_message("FAIL-SAFE: Resuming normal shutdown (other sensor failed).")
                self._fail_safe_logged = False
            
            # amb_min/max are already 0.0 (shutdown state)
            pass 

        # --- 5. UPDATE UI (No relay control) ---
        self.relay_control.update_ui_data(
            beer_temp if current_beer_ok else "--.-", 
            amb_temp if current_amb_ok else "--.-", 
            amb_min if amb_min is not None else 0.0, 
            amb_max if amb_max is not None else 0.0,
            current_mode, beer_setpoint_current,
            ambient_target_setpoint 
        )
        
        if self.notification_manager and self.notification_manager.ui:
            self.notification_manager.ui.push_data_update( 
                beer_temp=beer_temp if current_beer_ok else "--.-",
                amb_temp=amb_temp if current_amb_ok else "--.-",
                amb_min=amb_min if amb_min is not None else 0.0, 
                amb_max=amb_max if amb_max is not None else 0.0,
                beer_setpoint=beer_setpoint_current,
                amb_target=ambient_target_setpoint,
                current_mode=current_mode,
                ramp_end_target=ramp_end_target,
                ramp_start_time=ramp_start_time,
                ramp_is_finished=ramp_is_finished,
                ramp_target_message=ramp_target_message,
                sensor_error_message=sensor_error_message
            )
        
    # --- MONITORING THREAD ---
    def start_monitoring(self):
        if not self._monitoring:
            self._monitoring = True
            self.settings_manager.set("monitoring_state", "ON")
            
            # --- MODIFICATION: Removed explicit fan ON call ---
            # self.relay_control.turn_on_fan() 
            # -------------------------------------------------
            
            if self._monitor_thread is None or not self._monitor_thread.is_alive():
                self._stop_event.clear() # Ensure event is cleared on start
                self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
                self._monitor_thread.start()
                
                if self.notification_manager and self.notification_manager.ui:
                    self.notification_manager.ui.monitoring_var.set("ON") 
                
                print("TemperatureController: Monitoring thread started.")

    def stop_monitoring(self):
        if self._monitoring:
            print("TemperatureController: Initiating graceful shutdown of monitor loop...")
            # Just set the flag. The loop will see this and enter shutdown mode.
            self._monitoring = False
            self.settings_manager.set("monitoring_state", "OFF")
            
            if self.notification_manager and self.notification_manager.ui:
                self.notification_manager.ui.monitoring_var.set("OFF") 

    def _monitor_loop(self):
        while True:
            # --- 1. READ SENSORS AND MANAGE LATCHED LOGGING ---
            beer_temp = self.read_beer_temperature()
            amb_temp = self.read_ambient_temperature()
            
            current_beer_ok = (beer_temp is not None)
            current_amb_ok = (amb_temp is not None)
            
            # --- Latching Log Logic (with specific messages) ---
            if self.notification_manager and self.notification_manager.ui:
                # Beer Sensor State Change
                if current_beer_ok and not self._beer_sensor_ok:
                    self.notification_manager.ui.log_system_message("Beer sensor re-connected.")
                elif not current_beer_ok and self._beer_sensor_ok:
                    if self.settings_manager.get("ds18b20_beer_sensor") == "unassigned":
                        self.notification_manager.ui.log_system_message("Beer sensor is unassigned. Please set in System Settings.")
                    else:
                        self.notification_manager.ui.log_system_message("Beer sensor reading failed. Check connection.")

                # Ambient Sensor State Change
                if current_amb_ok and not self._amb_sensor_ok:
                    self.notification_manager.ui.log_system_message("Ambient sensor re-connected.")
                elif not current_amb_ok and self._amb_sensor_ok:
                    if self.settings_manager.get("ds18b20_ambient_sensor") == "unassigned":
                        self.notification_manager.ui.log_system_message("Ambient sensor is unassigned. Please set in System Settings.")
                    else:
                        self.notification_manager.ui.log_system_message("Ambient sensor reading failed. Check connection.")
            
            # Update the stored state
            self._beer_sensor_ok = current_beer_ok
            self._amb_sensor_ok = current_amb_ok
            
            # --- Update timestamps in settings ---
            current_time_str = datetime.now().strftime("%H:%M:%S")
            if current_beer_ok:
                 self.settings_manager.set("beer_temp_timestamp", current_time_str)
            if current_amb_ok:
                 self.settings_manager.set("amb_temp_timestamp", current_time_str)
            
            # --- 2. VALIDATE SENSORS BASED ON CONTROL MODE (with specific messages) ---
            current_mode = self.settings_manager.get("control_mode")
            sensor_error_message = ""
            
            if current_mode == "Ambient Hold":
                if not current_amb_ok:
                    if self.settings_manager.get("ds18b20_ambient_sensor") == "unassigned":
                        sensor_error_message = "FAIL: Ambient Sensor Unassigned"
                    else:
                        sensor_error_message = "FAIL: Ambient Sensor Missing"
            
            elif current_mode in ["Beer Hold", "Ramp-Up", "Fast Crash"]:
                if not current_beer_ok and not current_amb_ok:
                    sensor_error_message = "FAIL: Both Sensors Failed" # Generic, as this is a total failure
                elif not current_beer_ok:
                    if self.settings_manager.get("ds18b20_beer_sensor") == "unassigned":
                        sensor_error_message = "FAIL: Beer Sensor Unassigned"
                    else:
                        sensor_error_message = "FAIL: Beer Sensor Missing"
                elif not current_amb_ok:
                    if self.settings_manager.get("ds18b20_ambient_sensor") == "unassigned":
                        sensor_error_message = "FAIL: Ambient Sensor Unassigned"
                    else:
                        sensor_error_message = "FAIL: Ambient Sensor Missing"
            
            self.settings_manager.set("sensor_error_message", sensor_error_message)

            # --- 3. DETERMINE LOGIC & SETPOINTS ---
            desired_heat = False
            desired_cool = False
            amb_min, amb_max = 0.0, 0.0
            ambient_target_setpoint = self.settings_manager.get("ambient_hold_f")
            ramp_target_message = ""
            ramp_end_target = 0.0
            ramp_start_time = 0.0
            ramp_is_finished = False

            # --- Calculate Beer Setpoint (always needed for UI) ---
            if current_mode == "Ramp-Up":
                if self.ramp_state["is_in_pre_ramp"]:
                    beer_setpoint_current = self.settings_manager.get("beer_hold_f")
                else:
                    beer_setpoint_current = self.ramp_state["current_target"]
                    
                ramp_end_target = self.settings_manager.get("ramp_up_hold_f")
                ramp_start_time = self.ramp_state["start_time"]
                ramp_is_finished = self.ramp_state["is_finished"]
            elif current_mode == "Fast Crash":
                beer_setpoint_current = self.settings_manager.get("fast_crash_hold_f")
            else: # Beer Hold, Ambient Hold, or Off
                beer_setpoint_current = self.settings_manager.get("beer_hold_f")

            # --- 4. CHECK FOR FAIL-SAFE OR ERROR CONDITIONS ---
            
            # Condition 1: "Limp-Home" Mode (Beer Sensor Failed/Unassigned, Ambient OK)
            fail_safe_active = ("FAIL: Beer Sensor" in sensor_error_message) and current_amb_ok
            
            if fail_safe_active:
                if not self._fail_safe_logged:
                    if self.notification_manager and self.notification_manager.ui:
                        self.notification_manager.ui.log_system_message(f"FAIL-SAFE: Beer sensor failed. Holding chamber at {beer_setpoint_current:.1f} F.")
                    self._fail_safe_logged = True
                
                # Override: Use simple thermostatic control on AMBIENT
                target_amb_temp = beer_setpoint_current
                DEADBAND = self.settings_manager.get("ambient_deadband", 1.0) 
                amb_min = target_amb_temp - DEADBAND
                amb_max = target_amb_temp + DEADBAND
                
                desired_heat = amb_temp < amb_min
                desired_cool = amb_temp > amb_max

            # Condition 2: Other Critical Sensor Error (Shutdown)
            elif sensor_error_message:
                if self._fail_safe_logged:
                    if self.notification_manager and self.notification_manager.ui:
                        self.notification_manager.ui.log_system_message("FAIL-SAFE: Resuming normal shutdown (other sensor failed).")
                    self._fail_safe_logged = False
                
                desired_heat = False
                desired_cool = False
            
            # Condition 3: No Errors (Normal Operation)
            else:
                if self._fail_safe_logged:
                    if self.notification_manager and self.notification_manager.ui:
                        self.notification_manager.ui.log_system_message("FAIL-SAFE: Beer sensor re-connected. Resuming normal control.")
                    self._fail_safe_logged = False
                
                # --- RUN NORMAL LOGIC FUNCTION ---
                if current_mode == "Ambient Hold": amb_min, amb_max = self.ambient_hold_logic(amb_temp)
                elif current_mode == "Beer Hold": amb_min, amb_max = self.beer_hold_logic(beer_temp, amb_temp)
                elif current_mode == "Ramp-Up": amb_min, amb_max, ramp_target_message = self.ramp_up_logic(beer_temp, amb_temp)
                elif current_mode == "Fast Crash": amb_min, amb_max = self.fast_crash_logic(beer_temp, amb_temp)

                # --- DETERMINE RELAY ACTIONS ---
                if current_mode == "Ramp-Up" and amb_min is None:
                    # STATE 2: We are in the Main Ramp (Thermostatic) phase
                    THERMOSTAT_DEADBAND = self.settings_manager.get("ramp_thermo_deadband", 0.1) 
                    target = beer_setpoint_current # The moving target
                    
                    if beer_temp < (target - THERMOSTAT_DEADBAND):
                        desired_heat = True
                        desired_cool = False
                    elif beer_temp > (target + THERMOSTAT_DEADBAND):
                        desired_heat = False
                        desired_cool = True
                
                else:
                    # All other modes (PID-driven ambient envelope)
                    desired_heat = amb_temp < amb_min
                    desired_cool = amb_temp > amb_max
            
            # --- 5. CHECK MONITORING STATE (THE SHUTDOWN OVERRIDE) ---
            if not self._monitoring:
                print("[Monitor Loop] Shutdown requested. Sending OFF commands.")
                desired_heat = False
                desired_cool = False
                current_mode = "OFF" # Set mode to off for relay_control (This triggers Aux OFF too)
                sensor_error_message = "" 
                if self._fail_safe_logged:
                    if self.notification_manager and self.notification_manager.ui:
                        self.notification_manager.ui.log_system_message("FAIL-SAFE: Monitoring stopped. Resuming normal shutdown.")
                    self._fail_safe_logged = False
            
            # --- 6. APPLY STATES (This section runs in ALL modes) ---
            # The relay_control now handles the Aux relay automatically here
            final_heat, final_cool = self.relay_control.set_desired_states(
                desired_heat, desired_cool, current_mode
            )

            self.relay_control.update_ui_data(
                beer_temp if current_beer_ok else "--.-",
                amb_temp if current_amb_ok else "--.-",
                amb_min if amb_min is not None else 0.0, 
                amb_max if amb_max is not None else 0.0, 
                current_mode, beer_setpoint_current,
                ambient_target_setpoint
            )
            
            # --- 7. PUSH DATA TO UI (ALWAYS) ---
            if self.notification_manager and self.notification_manager.ui:
                 self.notification_manager.ui.push_data_update(
                    beer_temp=beer_temp if current_beer_ok else "--.-",
                    amb_temp=amb_temp if current_amb_ok else "--.-",
                    amb_min=amb_min if amb_min is not None else 0.0, 
                    amb_max=amb_max if amb_max is not None else 0.0,
                    beer_setpoint=beer_setpoint_current,
                    heat_state=self.settings_manager.get("heat_state"),
                    cool_state=self.settings_manager.get("cool_state"),
                    amb_target=ambient_target_setpoint,
                    current_mode=current_mode,
                    ramp_end_target=ramp_end_target,
                    ramp_start_time=ramp_start_time,
                    ramp_is_finished=ramp_is_finished,
                    ramp_target_message=ramp_target_message,
                    sensor_error_message=sensor_error_message
                 )

            # --- 8. CHECK FOR SAFE EXIT ---
            if not self._monitoring:
                if not final_cool and not final_heat:
                    print("[Monitor Loop] Relays are safely OFF. Shutting down fan.")
                    # --- MODIFICATION: Explicit call removed; Aux handled by set_desired_states("OFF") above ---
                    # self.relay_control.turn_off_fan()
                    
                    # Ensure final OFF state is sent to UI
                    if self.notification_manager and self.notification_manager.ui:
                         self.notification_manager.ui.push_data_update(
                            beer_temp=beer_temp if current_beer_ok else "--.-",
                            amb_temp=amb_temp if current_amb_ok else "--.-",
                            amb_min=amb_min if amb_min is not None else 0.0,
                            amb_max=amb_max if amb_max is not None else 0.0,
                            beer_setpoint=beer_setpoint_current,
                            heat_state="Heating OFF",
                            cool_state="Cooling OFF",
                            amb_target=ambient_target_setpoint,
                            current_mode="OFF",
                            ramp_end_target=ramp_end_target,
                            ramp_start_time=ramp_start_time,
                            ramp_is_finished=ramp_is_finished,
                            ramp_target_message="",
                            sensor_error_message=""
                         )
                    
                    break # Exit the "while True" loop
                else:
                    print("[Monitor Loop] Shutdown pending, waiting for compressor dwell time to expire...")

            # The loop wait
            self._stop_event.wait(5)
            if self._stop_event.is_set():
                break
                
        print("TemperatureController: Monitoring thread stopped.")
