# keglevel app
#
# sensor_logic.py
import time
import threading
import math

''' GPIO PINOUT FOR REFERENCE
Label ------------ Pin - Pin ------------ Label
3V3 power---------  1     2  ------------ 5V power
GPIO 2 (SDA) -----  3     4  ------------ 5V power
GPIO 3 (SCL) -----  5     6  ------------ Ground
GPIO 4 (GPCLK0) --  7     8  ------------ GPIO 14 (TXD)
Ground -----------  9    10  ------------ GPIO 15 (RXD)
GPIO 17 ---------- 11    12  ------------ GPIO 18 (PCM_CLK)
GPIO 27 ---------- 13    14  ------------ Ground
GPIO 22 ---------- 15    16  ------------ GPIO 23
3V3 power -------- 17    18  ------------ GPIO 24
GPIO 10 (MOSI) --- 19    20  ------------ Ground
GPIO 9 (MISO) ---- 21    22  ------------ GPIO 25
GPIO 11 (SCLK) --- 23    24  ------------ GPIO 8 (CE0)
Ground ----------- 25    26  ------------ GPIO 7 (CE1)
GPIO 0 (ID_SD) --- 27    28  ------------ GPIO 1 (ID_SC)
GPIO 5 ----------- 29    30  ------------ Ground
GPIO 6 ----------- 31    32  ------------ GPIO 12 (PWM0)
GPIO 13 (PWM1) --- 33    34  ------------ Ground
GPIO 19 (PCM_FS) - 35    36  ------------ GPIO 16
GPIO 26 ---------- 37    38  ------------ GPIO 20 (PCM_DIN)
Ground ----------- 39    40  ------------ GPIO 21 (PCM_DOUT)
'''

# --- REFACTOR: SAFE IMPORT FOR CROSS-PLATFORM COMPATIBILITY ---

try:
    # Direct import for Raspberry Pi hardware
    import RPi.GPIO as GPIO

    # FIX: Check if RPi.GPIO or lgpio is used by reading the startup print statement
    if GPIO.getmode() != GPIO.BCM: # Check if mode is set by a previous run or a fresh start
        GPIO.setmode(GPIO.BCM)
    print("Running on RPi hardware (RPi.GPIO mode).")
    IS_RASPBERRY_PI_MODE = True

except (ImportError, RuntimeError):
    print("WARNING: RPi.GPIO not found. Running in simulation/mock mode (Windows/Non-Pi).")
    IS_RASPBERRY_PI_MODE = False
    
    # Mock GPIO class prevents crashes when code tries to access GPIO.BCM etc.
    class MockGPIO:
        BCM = "BCM"
        IN = "IN"
        PUD_DOWN = "PUD_DOWN"
        RISING = "RISING"
        
        @staticmethod
        def setmode(mode): pass
        @staticmethod
        def setup(pin, mode, pull_up_down=None): pass
        @staticmethod
        def add_event_detect(pin, edge, callback, bouncetime=None): pass
        @staticmethod
        def remove_event_detect(pin): pass
        @staticmethod
        def cleanup(): pass
    
    GPIO = MockGPIO

# --- NEW: Helper function expected by main.py ---
def is_raspberry_pi():
    """Returns True if running on Raspberry Pi hardware."""
    return IS_RASPBERRY_PI_MODE
# ------------------------------------------------

# --- END REFACTOR ---

# --- Sensor Configuration Constants (Flow Meter) ---
# Define GPIO pins to use on the Raspberry Pi for each sensor (BCM numbering).
# 10K external pull-down resistor supplied between GPIO pin and ground (cleans up signal)

# CRITICAL FIX: Restored the working pin set from sensor_logic_working.py
FLOW_SENSOR_PINS = [
    5,  # Tap 1 physical pin 29
    6,  # Tap 2 physical pin 31
    12, # Tap 3 Physical pin 32
    13, # Tap 4 Physical pin 33
    16, # Tap 5 Physical pin 36
    25, # Tap 6 Physical pin 22
    26, # Tap 7 Physical pin 37
    7,  # Tap 8 Physical pin 26
    20, # Tap 9 Physical pin 38
    21, # Tap 10 Physical pin 40
]

READING_INTERVAL_SECONDS = 0.5 

# --- FLOW SENSOR LOGIC CONSTANTS ---
FLOW_DEBOUNCE_MS = 5            # Debounce time for pulse detection (ms)
FLOW_PULSES_FOR_ACTIVITY = 10   # Pulses in the interval needed to be considered 'active'
FLOW_PULSES_FOR_STOPPED = 3     # Pulses in the interval or less to be considered 'stopped'

# Note: FLOW_CALIBRATION_FACTORS is now loaded from settings_manager on startup/force_recalculation.
# --- CRITICAL FIX: Set a more realistic default K-Factor (Pulses/Liter) ---
DEFAULT_K_FACTOR = 5100.0
# ---------------------------------

GPIO_LIB = GPIO 
HARDWARE_AVAILABLE = IS_RASPBERRY_PI_MODE    # IS_RASPBERRY_PI_MODE is for runtime, set to False for testing to elimiate GPIO issues

# Global pulse counter list (must be non-local for the interrupt handler)
global_pulse_counts = [0] * len(FLOW_SENSOR_PINS)
last_check_time = [0.0] * len(FLOW_SENSOR_PINS) 

def count_pulse(channel):
    """Interrupt handler: Increments the pulse count for the active channel."""
    try:
        # Map the GPIO pin number back to the sensor index
        sensor_index = FLOW_SENSOR_PINS.index(channel)
        global_pulse_counts[sensor_index] += 1
    except ValueError:
        pass # Ignore pulses on pins not in the list


class SensorLogic:
    def __init__(self, num_sensors_from_config, ui_callbacks, settings_manager, notification_service):
        self.num_sensors = num_sensors_from_config
        self.ui_callbacks = ui_callbacks
        self.settings_manager = settings_manager
        self.notification_service = notification_service

        if self.num_sensors > len(FLOW_SENSOR_PINS):
            self.num_sensors = len(FLOW_SENSOR_PINS)
            print(f"Warning: Number of sensors requested ({num_sensors_from_config}) is more than available pins. Using {self.num_sensors} sensors.")

        self.sensor_pins = FLOW_SENSOR_PINS[:self.num_sensors]

        # --- Flow Sensor Specific State ---
        self.keg_ids_assigned = [None] * self.num_sensors 
        self.keg_dispensed_liters = [0.0] * self.num_sensors 
        self.current_flow_rate_lpm = [0.0] * self.num_sensors
        self.tap_is_active = [False] * self.num_sensors
        self.active_sensor_index = -1 
        self.last_pulse_count = [0] * self.num_sensors
        
        # --- NEW: Smart Flow & Last Pour Tracking ---
        self.last_pour_averages = self.settings_manager.get_last_pour_averages()
        self.last_pour_volumes = self.settings_manager.get_last_pour_volumes() # NEW
        
        self.current_pour_volume = [0.0] * self.num_sensors
        self.current_pour_duration = [0.0] * self.num_sensors
        
        self.sim_deduct_disabled = [False] * self.num_sensors
        
        self._is_calibrating = False
        self._cal_target_tap = -1
        self._cal_start_pulse_count = 0
        self._cal_current_session_liters = 0.0 
        self._cal_target_volume_user_unit = 0.0 
        
        self.raw_readings_buffer = [[] for _ in range(self.num_sensors)] 
        self.loop_count = 0
        self._running = False
        self.is_paused = False
        self.last_known_remaining_liters = [None] * self.num_sensors
        
        self.sensor_thread = None 

        self._load_initial_volumes()
        
    def _calculate_flow_metrics(self, sensor_index, pulses, time_interval, k_factor, status_override="Nominal", update_ui=True, persist_data=True):
        
        if k_factor == 0 or time_interval == 0:
            flow_rate_lpm = 0.0
            dispensed_liters_interval = 0.0
        else:
            flow_rate_lpm = (pulses / k_factor) / (time_interval / 60.0)
            dispensed_liters_interval = pulses / k_factor 

        self.keg_dispensed_liters[sensor_index] += dispensed_liters_interval
        
        if status_override == "Pouring":
            self.current_pour_volume[sensor_index] += dispensed_liters_interval
        
        if persist_data:
            keg_id = self.keg_ids_assigned[sensor_index]
            if keg_id:
                self.settings_manager.update_keg_dispensed_volume(keg_id, self.keg_dispensed_liters[sensor_index], pulses=pulses)
        
        keg = self.settings_manager.get_keg_by_id(self.keg_ids_assigned[sensor_index])
        starting_volume = keg.get('calculated_starting_volume_liters', 0.0) if keg else 0.0 
        remaining_liters = starting_volume - self.keg_dispensed_liters[sensor_index]
        self.last_known_remaining_liters[sensor_index] = remaining_liters

        if update_ui:
            # --- DETERMINE DISPLAY VOLUME ---
            if status_override == "Pouring":
                # Show live counting up
                vol_to_show = self.current_pour_volume[sensor_index]
            else:
                # Show last finished pour
                vol_to_show = self.last_pour_volumes[sensor_index]
                
            self._update_ui_data(sensor_index, flow_rate_lpm, remaining_liters, status_override, vol_to_show)
        
        return flow_rate_lpm, dispensed_liters_interval, remaining_liters
    # --- NEW: Flow Calibration Methods ---
    def start_flow_calibration(self, tap_index, target_volume_user_unit_str):
        global global_pulse_counts
        if self._running and 0 <= tap_index < self.num_sensors:
            try:
                target_volume = float(target_volume_user_unit_str)
            except ValueError:
                print("SensorLogic Cal Error: Invalid target volume.")
                return False

            self._is_calibrating = True
            self._cal_target_tap = tap_index
            self._cal_target_volume_user_unit = target_volume
            
            # --- CRITICAL FIX: Reset session data ---
            self._cal_start_pulse_count = global_pulse_counts[tap_index]
            self._cal_current_session_liters = 0.0
            # ----------------------------------------
            
            # Immediately force the tap to be considered active for flow data processing
            self.active_sensor_index = tap_index 
            self.tap_is_active[tap_index] = True
            
            print(f"SensorLogic Cal: Started for tap {tap_index+1} at pulse {self._cal_start_pulse_count}")
            return True
        return False

    def stop_flow_calibration(self, tap_index):
        global global_pulse_counts
        
        # Ensure only the active tap can stop calibration
        if not self._is_calibrating or self._cal_target_tap != tap_index:
            return 0, 0.0

        current_time = time.time()
        time_interval = current_time - last_check_time[tap_index]
        k_factors = self.settings_manager.get_flow_calibration_factors()
        k_factor = k_factors[tap_index]

        # Process the final interval of pulses
        pulses_in_interval = global_pulse_counts[tap_index] - self.last_pulse_count[tap_index]
        
        # NOTE: This call updates self._cal_current_session_liters one last time
        flow_rate_lpm, dispensed_liters_interval = self._calculate_calibration_metrics(tap_index, pulses_in_interval, time_interval, k_factor)
        
        # Calculate final dispensed volume using the CURRENT K-factor (Liters)
        total_pulses = global_pulse_counts[tap_index] - self._cal_start_pulse_count
        final_dispensed_liters = self._cal_current_session_liters
        
        # Update the UI one last time with calculated values before exiting cal mode
        self.ui_callbacks.get("update_cal_data_cb")(0.0, final_dispensed_liters) # Flow rate is now 0
        
        # Reset state variables
        self._is_calibrating = False
        self._cal_target_tap = -1
        self.active_sensor_index = -1
        self.tap_is_active[tap_index] = False
        
        print(f"SensorLogic Cal: Stopped for tap {tap_index+1}. Total Pulses: {total_pulses}")
        
        # Return total pulses and the final measured pour in Liters for the UI to use in the Set Cal button
        return total_pulses, final_dispensed_liters

    def _calculate_calibration_metrics(self, tap_index, pulses, time_interval, k_factor):
        """Calculates flow metrics only for the calibration session, without impacting main keg levels."""
        
        if k_factor == 0 or time_interval == 0:
            flow_rate_lpm = 0.0
            dispensed_liters_interval = 0.0
        else:
            flow_rate_lpm = (pulses / k_factor) / (time_interval / 60.0)
            dispensed_liters_interval = pulses / k_factor 
            
        # Accumulate volume for this calibration session only
        self._cal_current_session_liters += dispensed_liters_interval
        
        # Send live data to the open calibration popup
        if self._is_calibrating and self._cal_target_tap == tap_index and self.ui_callbacks.get("update_cal_data_cb"):
             self.ui_callbacks.get("update_cal_data_cb")(flow_rate_lpm, self._cal_current_session_liters)
        
        return flow_rate_lpm, dispensed_liters_interval


    # --- END NEW: Flow Calibration Methods ---
    def deduct_volume_from_keg(self, tap_index, dispensed_liters):
        """
        Manually deducts a volume (in Liters) from the keg assigned to the tap.
        Used after a calibration pour when the user confirms deduction.
        """
        if not (0 <= tap_index < self.num_sensors): return False
        
        keg_id = self.keg_ids_assigned[tap_index]
        if not keg_id: return False
        
        # 1. Update local dispensed volume
        self.keg_dispensed_liters[tap_index] += dispensed_liters
        
        # 2. Update memory and disk storage
        new_dispensed_total = self.keg_dispensed_liters[tap_index]
        
        # Update SettingsManager in MEMORY
        self.settings_manager.update_keg_dispensed_volume(keg_id, new_dispensed_total)
        
        # Save to DISK immediately
        self.settings_manager.save_all_keg_dispensed_volumes()
        
        # 3. Recalculate and update the remaining liters (and UI will refresh with force_recalculation)
        keg = self.settings_manager.get_keg_by_id(keg_id)
        starting_volume = keg.get('calculated_starting_volume_liters', 0.0) if keg else 0.0 
        remaining_liters = starting_volume - new_dispensed_total
        self.last_known_remaining_liters[tap_index] = max(0.0, remaining_liters)
        
        print(f"SensorLogic: Manually deducted {dispensed_liters:.2f}L from Tap {tap_index + 1} (Keg ID: {keg_id}).")
        return True
    # --- END NEW: Deduction Method ---

    def _load_initial_volumes(self):
        """Loads the dispensed volume and total starting volume from the Keg Library."""
        assignments = self.settings_manager.get_sensor_keg_assignments()

        for i in range(self.num_sensors):
             keg_id = assignments[i]
             keg = self.settings_manager.get_keg_by_id(keg_id)
             
             # FIX: Store the assigned keg ID from the settings manager
             self.keg_ids_assigned[i] = keg_id
             
             if keg:
                 # Load dispensed volume from the KEG (persistent)
                 dispensed = keg.get('current_dispensed_liters', 0.0)
                 # FIX: Use the new calculated_starting_volume_liters key
                 starting_vol = keg.get('calculated_starting_volume_liters', 0.0)
                 
                 # Set local dispensed volume to the persistent value
                 self.keg_dispensed_liters[i] = dispensed
                 
                 # Calculate and set remaining for UI display
                 remaining_liters = max(0.0, starting_vol - dispensed)
                 self.last_known_remaining_liters[i] = remaining_liters
             else:
                 # If keg not found (e.g., assignment is corrupted), zero out
                 self.keg_dispensed_liters[i] = 0.0
                 self.last_known_remaining_liters[i] = 0.0

    def start_monitoring(self):
        if not HARDWARE_AVAILABLE:
            # Simulate initial UI update with the starting volume
            for i in range(self.num_sensors):
                self._update_ui_data(i, 0.0, self.last_known_remaining_liters[i], "Nominal")
            return

        self._setup_gpios()
        self._running = True
        self.is_paused = False

        if self.sensor_thread is None or not self.sensor_thread.is_alive():
            self.sensor_thread = threading.Thread(target=self._sensor_loop, daemon=True)
            self.sensor_thread.start()

    def stop_monitoring(self):
        self._running = False
        if self.sensor_thread and self.sensor_thread.is_alive():
            self.sensor_thread.join(timeout=READING_INTERVAL_SECONDS + 2)
        
        # --- FIX: Use the new public cleanup method ---
        self.cleanup_gpio()
        # --- END FIX ---
        
        print("SensorLogic: Monitoring stopped and resources released.")

    def _setup_gpios(self):
        print("SensorLogic: Setting up GPIO pins for flow meters...")
        
        # FIX: Attempt a cleanup FIRST to clear any stale state from THIS process.
        # NOTE: This clears the BCM/BOARD mode setting, so we must set it again after.
        try:
            GPIO_LIB.cleanup()
        except Exception:
            pass

        # FIX: Set Mode AFTER cleanup, so it persists for the setup loop
        GPIO_LIB.setmode(GPIO_LIB.BCM)

        for pin in self.sensor_pins:
            try:
                # Setup as input with PULL_DOWN per requirements.
                GPIO_LIB.setup(pin, GPIO_LIB.IN, pull_up_down=GPIO_LIB.PUD_DOWN) 
                # Add the event detect for rising edge, calling the global pulse counter
                GPIO_LIB.add_event_detect(pin, GPIO_LIB.RISING,
                                          callback=count_pulse,
                                          bouncetime=FLOW_DEBOUNCE_MS)
            except Exception as e:
                # --- NEW: Error Trap for Busy Pins ---
                if "busy" in str(e).lower():
                    print(f"\n[CRITICAL ERROR] GPIO Pin {pin} is BUSY.")
                    print(f"This pin might be in use by another app (like FermVault) or a previous instance of KegLevel.")
                    print(f"Conflict Pins: 26 (Tap 7/Heat), 20 (Tap 9/Cool), 21 (Tap 10/Fan).")
                    print("Please stop the other application or change the pin assignments.\n")
                raise e
                
        print("SensorLogic: GPIO setup complete.")

    def pause_acquisition(self):
        self.is_paused = True
        print("SensorLogic: Monitoring paused.")

    def resume_acquisition(self):
        self.is_paused = False
        self._load_initial_volumes() # Reload volumes
        print("SensorLogic: Resuming. Initial volumes reloaded.")
            
    def force_recalculation(self):
        """Forces the logic to reload all initial volumes."""
        print("SensorLogic: Forcing recalculation/reload of initial volumes.")
        self._load_initial_volumes()
        
        # --- FIX: Reset debounce state so the UI gets a fresh update ---
        # This ensures that if the UI was reset to "Acquiring...", the next 
        # sensor loop update will be sent and will clear the gray status.
        if hasattr(self, 'last_sent_ui_state'):
            self.last_sent_ui_state = [None] * self.num_sensors

    def _update_ui_data(self, sensor_index, flow_rate_lpm, remaining_liters, status_string, last_pour_vol=None):
        """Helper to send updates to the UI's queue. Includes debouncing to prevent UI flood."""
        
        if not hasattr(self, 'last_sent_ui_state'):
            self.last_sent_ui_state = [None] * self.num_sensors

        # Check if this exact data was already sent last time (added last_pour_vol to snapshot)
        current_state = (sensor_index, flow_rate_lpm, remaining_liters, status_string, last_pour_vol)

        if self.last_sent_ui_state[sensor_index] == current_state:
            return 
            
        self.last_sent_ui_state[sensor_index] = current_state

        if self.ui_callbacks.get("update_sensor_data_cb"):
            self.ui_callbacks.get("update_sensor_data_cb")(
                sensor_index, flow_rate_lpm, remaining_liters, status_string, last_pour_vol
            )
        if self.ui_callbacks.get("update_sensor_stability_cb"):
            is_stable = status_string in ["Nominal", "Pouring", "Idle"]
            self.ui_callbacks.get("update_sensor_stability_cb")(
                sensor_index, "Data stable" if is_stable else "Acquiring data..."
            )

    def _get_default_system_settings(self):
        return {
            "display_units": "metric", "displayed_taps": 5, "ds18b20_ambient_sensor": "unassigned", 
            "ui_mode": "lite", "autostart_enabled": False, 
            "launch_workflow_on_start": False,
            "flow_calibration_factors": [DEFAULT_K_FACTOR] * self.num_sensors,
            "metric_pour_ml": 355, "imperial_pour_oz": 12,
            "flow_calibration_notes": "", "flow_calibration_to_be_poured": 500.0,
            "last_pour_averages": [0.0] * self.num_sensors,
            
            # --- NEW: Last Pour Volume Persistence ---
            "last_pour_volumes": [0.0] * self.num_sensors,
            # -----------------------------------------
            
            "force_numlock": False,
            "eula_agreed": False,
            "show_eula_on_launch": True,
            "window_geometry": None,
            "check_updates_on_launch": True,
            "notify_on_update": True
        }

    # --- NEW METHODS for Last Pour Volume ---
    def get_last_pour_volumes(self):
        defaults = self._get_default_system_settings().get('last_pour_volumes')
        vols = self.settings.get('system_settings', {}).get('last_pour_volumes', defaults)
        if not isinstance(vols, list) or len(vols) != self.num_sensors:
            return [0.0] * self.num_sensors
        return [float(x) for x in vols]

    def save_last_pour_volumes(self, volumes_list):
        if len(volumes_list) == self.num_sensors:
            self.settings.setdefault('system_settings', self._get_default_system_settings())['last_pour_volumes'] = volumes_list
            self._save_all_settings()

    def _sensor_loop(self):
        global global_pulse_counts
        global last_check_time
        
        if all(t == 0.0 for t in last_check_time):
             current_time = time.time()
             for i in range(len(FLOW_SENSOR_PINS)): last_check_time[i] = current_time

        while self._running:
            if self.is_paused:
                time.sleep(0.5)
                continue
                
            if self._is_calibrating and self._cal_target_tap != -1:
                 self.active_sensor_index = self._cal_target_tap 
                 self.tap_is_active[self._cal_target_tap] = True
                 
            # --- BEGIN STANDARD MONITORING LOGIC ---
            current_time = time.time()
            displayed_taps_count = self.settings_manager.get_displayed_taps()
            k_factors = self.settings_manager.get_flow_calibration_factors()
            
            new_active_sensor_index = -1
            if not self._is_calibrating and self.active_sensor_index == -1:
                for i in range(displayed_taps_count):
                    time_interval = current_time - last_check_time[i]
                    pulses_in_interval = global_pulse_counts[i] - self.last_pulse_count[i]
                    if pulses_in_interval >= FLOW_PULSES_FOR_ACTIVITY and time_interval > 0:
                        new_active_sensor_index = i
                        break
            elif not self._is_calibrating and self.active_sensor_index != -1:
                new_active_sensor_index = self.active_sensor_index
                
            if self._is_calibrating:
                self.active_sensor_index = self._cal_target_tap
            else:
                self.active_sensor_index = new_active_sensor_index
            
            for i in range(displayed_taps_count):
                time_interval = current_time - last_check_time[i]
                pulses_in_interval = global_pulse_counts[i] - self.last_pulse_count[i]
                
                is_currently_active = (i == self.active_sensor_index)
                is_currently_calibrating_target = self._is_calibrating and self._cal_target_tap == i
                
                persist = not self.sim_deduct_disabled[i]

                if is_currently_active and time_interval > 0 and pulses_in_interval > 0:
                    k_factor = k_factors[i]
                    
                    if not self.tap_is_active[i]:
                        self.current_pour_volume[i] = 0.0
                        self.current_pour_duration[i] = 0.0
                    
                    self.current_pour_duration[i] += time_interval

                    if is_currently_calibrating_target:
                        self._calculate_calibration_metrics(i, pulses_in_interval, time_interval, k_factor)
                        self.tap_is_active[i] = True
                    else:
                        self._process_flow_data(i, pulses_in_interval, time_interval, k_factor, status_override="Pouring", persist_data=persist)
                        self.tap_is_active[i] = True
                
                elif self.tap_is_active[i] and not is_currently_calibrating_target: 
                    if pulses_in_interval <= FLOW_PULSES_FOR_STOPPED:
                        
                        k_factor = k_factors[i]
                        flow_rate, liters_interval, _ = self._calculate_flow_metrics(i, pulses_in_interval, time_interval, k_factor, status_override="Idle", persist_data=persist, update_ui=True)
                        
                        self.current_pour_duration[i] += time_interval
                        self.current_pour_volume[i] += liters_interval
                        
                        total_seconds = self.current_pour_duration[i]
                        total_liters = self.current_pour_volume[i]
                        
                        if total_seconds > 0 and total_liters > 0.06:
                            avg_lpm = total_liters / (total_seconds / 60.0)
                            self.last_pour_averages[i] = avg_lpm
                            self.settings_manager.save_last_pour_averages(self.last_pour_averages)
                            
                            # --- NEW: Save Last Pour Volume ---
                            self.last_pour_volumes[i] = total_liters
                            self.settings_manager.save_last_pour_volumes(self.last_pour_volumes)
                            # ----------------------------------
                        
                        # Use Idle update with FINAL saved values
                        self._update_ui_data(i, self.last_pour_averages[i], self.last_known_remaining_liters[i], "Idle", self.last_pour_volumes[i])

                        if not persist:
                            keg_id = self.keg_ids_assigned[i]
                            if keg_id:
                                keg = self.settings_manager.get_keg_by_id(keg_id)
                                if keg:
                                    self.keg_dispensed_liters[i] = keg.get('current_dispensed_liters', 0.0)
                                    start_vol = keg.get('calculated_starting_volume_liters', 0.0)
                                    self.last_known_remaining_liters[i] = start_vol - self.keg_dispensed_liters[i]
                                    # Force UI update with reverted values
                                    self._update_ui_data(i, self.last_pour_averages[i], self.last_known_remaining_liters[i], "Idle", self.last_pour_volumes[i])
                            
                            self.sim_deduct_disabled[i] = False
                        else:
                            self.settings_manager.save_all_keg_dispensed_volumes()

                        self.tap_is_active[i] = False
                        self.active_sensor_index = -1 
                        print(f"SensorLogic: Tap {i+1} stopped. Avg: {self.last_pour_averages[i]:.2f} LPM.")

                    elif not is_currently_active:
                         self.tap_is_active[i] = False
                         self.active_sensor_index = -1
                         self._update_ui_data(i, self.last_pour_averages[i], self.last_known_remaining_liters[i], "Idle", self.last_pour_volumes[i])

                elif is_currently_calibrating_target:
                    pass
                
                elif not self.tap_is_active[i]:
                    # IDLE LOOP: Send stored values
                    self._update_ui_data(i, self.last_pour_averages[i], self.last_known_remaining_liters[i], "Idle", self.last_pour_volumes[i])
                    self._check_conditional_notification(i)

                self.last_pulse_count[i] = global_pulse_counts[i]
                last_check_time[i] = current_time

            self.notification_service.check_and_send_temp_notification()
            time.sleep(READING_INTERVAL_SECONDS)

        print("SensorLogic: Sensor loop ended.")

    def _process_flow_data(self, sensor_index, pulses, time_interval, k_factor, status_override="Nominal", persist_data=True):
        """Wrapper for calculating metrics and checking alerts."""
        flow_rate_lpm, dispensed_liters_interval, remaining_liters = self._calculate_flow_metrics(
            sensor_index, pulses, time_interval, k_factor, status_override=status_override, persist_data=persist_data
        )
        self._check_conditional_notification(sensor_index, force_check=True)

    def _check_conditional_notification(self, sensor_index, force_check=False):
        """Checks if the remaining volume is below the threshold and triggers notification."""
        remaining_liters = self.last_known_remaining_liters[sensor_index]
        if remaining_liters is None: return

        cond_notif_settings = self.settings_manager.get_conditional_notification_settings()
        cond_notif_type = cond_notif_settings.get('notification_type', 'None')
        cond_notif_threshold_liters = cond_notif_settings.get('threshold_liters', 4.0)
        sent_status_list = cond_notif_settings.get('sent_notifications', [])
        
        if cond_notif_type != 'None':
            # Low Volume Notification
            if remaining_liters <= cond_notif_threshold_liters and not sent_status_list[sensor_index] and force_check:
                self.notification_service.send_conditional_notification(sensor_index, remaining_liters, cond_notif_threshold_liters)

            # Refill/Reset Notification Status
            reset_threshold = cond_notif_threshold_liters * 1.25
            if sent_status_list[sensor_index] and remaining_liters > reset_threshold:
                self.settings_manager.update_conditional_sent_status(sensor_index, False)
                
    def simulate_pour(self, sensor_index, volume_liters, flow_rate_lpm, deduct_volume=True):
        """
        Starts a background thread to simulate a pour.
        deduct_volume: If False, the volume will visually drop but revert after the pour.
        """
        if not (0 <= sensor_index < self.num_sensors):
            print(f"Simulation Error: Invalid sensor index {sensor_index}")
            return
            
        # Set the flag for the main loop to see
        self.sim_deduct_disabled[sensor_index] = not deduct_volume
            
        # Launch simulation thread
        threading.Thread(
            target=self._run_simulation,
            args=(sensor_index, volume_liters, flow_rate_lpm),
            daemon=True
        ).start()

    def _run_simulation(self, sensor_index, volume_liters, flow_rate_lpm):
        """
        Internal loop that increments the global pulse count to mimic a real pour.
        """
        global global_pulse_counts
        
        # 1. Calculate parameters
        k_factor = self.settings_manager.get_flow_calibration_factors()[sensor_index]
        if k_factor <= 0:
            print(f"Simulation Error: K-Factor is 0 for tap {sensor_index+1}")
            return

        total_pulses = int(volume_liters * k_factor)
        duration_minutes = volume_liters / flow_rate_lpm
        duration_seconds = duration_minutes * 60
        
        if duration_seconds <= 0: return

        # Pulses per second
        pps = total_pulses / duration_seconds
        # Sleep interval (aim for ~10 updates per second for smoothness)
        update_interval = 0.1 
        pulses_per_step = int(pps * update_interval)
        
        # If flow is very slow, ensure at least 1 pulse per step occasionally
        # but for simplicity, we'll just track float accumulation and add int pulses
        
        print(f"--- STARTING SIMULATION: Tap {sensor_index+1} ---")
        print(f"Target: {volume_liters}L @ {flow_rate_lpm} LPM")
        print(f"Total Pulses: {total_pulses} over {duration_seconds:.1f}s")
        
        current_pulse_accumulation = 0.0
        pulses_added = 0
        start_time = time.time()
        
        while pulses_added < total_pulses and self._running:
            step_start = time.time()
            
            # Calculate how many pulses to add this step
            current_pulse_accumulation += (pps * update_interval)
            
            to_add = int(current_pulse_accumulation)
            if to_add > 0:
                global_pulse_counts[sensor_index] += to_add
                current_pulse_accumulation -= to_add
                pulses_added += to_add
            
            # Sleep remainder of interval
            elapsed = time.time() - step_start
            sleep_time = update_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
            
            # Safety timeout
            if (time.time() - start_time) > (duration_seconds + 5):
                break
                
        print(f"--- SIMULATION COMPLETE: Tap {sensor_index+1} ---")
                
    # --- SAFETY CLEANUP METHOD ---
    def cleanup_gpio(self):
        """Resets all GPIO pins to safe input state. Called on app exit/crash."""
        print("SensorLogic: Performing emergency GPIO cleanup...")
        try:
            # 1. Remove all event detection (critical for interrupts)
            for pin in self.sensor_pins:
                try:
                    GPIO_LIB.remove_event_detect(pin)
                except Exception:
                    pass # Ignore if event wasn't set
            
            # 2. Reset pins to INPUT
            GPIO_LIB.cleanup()
            print("SensorLogic: GPIO resources cleaned up.")
        except Exception as e:
            print(f"SensorLogic Warning: GPIO cleanup failed: {e}")
