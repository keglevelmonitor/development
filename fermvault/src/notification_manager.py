"""
fermvault app
notification_manager.py
"""

import threading
import time
import math
import smtplib
import imaplib
import email
import email.header
from datetime import datetime, timedelta, timezone # <-- MODIFIED LINE
from email.mime.text import MIMEText

# Constants
MINUTES_TO_SECONDS = 60
HOURS_TO_SECONDS = 3600
STATUS_REQUEST_SUBJECT = "STATUS"
ERROR_DEBOUNCE_INTERVAL_SECONDS = 3600

class NotificationManager:
    def __init__(self, settings_manager, ui_manager):
        self.settings_manager = settings_manager
        self.ui = ui_manager  
        
        # --- SCHEDULER STATE ---
        self._scheduler_running = False
        self._scheduler_thread = None
        self._scheduler_event = threading.Event()
        self.last_notification_sent_time = 0
        
        # --- MODIFICATION: Added independent timers ---
        self.last_api_fetch_time = 0
        self.last_fg_calc_time = 0
        # --- END MODIFICATION ---
        
        # --- STATUS REQUEST STATE (IMAP Listener) ---
        self._status_request_listener_thread = None
        self._status_request_running = False
        self._status_request_interval_seconds = 60 
        
        self._last_error_time = {"push": 0.0, "request": 0.0, "fg": 0.0}

        # --- NEW: Conditional Alert State Tracking ---
        self.last_conditional_check_time = 0
        self._fg_alert_sent = False # Latch for FG Stable alert
        
        # Cooldown trackers (timestamp of last email sent)
        self._alert_cooldowns = {
            "ambient_temp": 0.0,
            "beer_temp": 0.0,
            "sensor_amb": 0.0,
            "sensor_beer": 0.0
        }
        self.ALERT_COOLDOWN_SECONDS = 7200 # 2 Hours
        # --- END NEW ---

    def _get_command_help_text(self):
        """Returns a list of strings for the email command help text."""
        return [
            "",
            "",
            "To issue commands via email:",
            "Subject: command",
            "Body: one or more of the following commands, each on its own line:",
            "",
            "control mode ambient",
            "control mode beer",
            "control mode ramp",
            "control mode crash",
            "setpoint ambient [nn]",
            "setpoint beer [nn]",
            "setpoint ramp [nn]",
            "setpoint duration [nn] (ramp up duration in hours)",
            "setpoint crash [nn]",
            "notification frequency [nn] (report frequency in hours)",
        ]
        
    def _parse_setpoint_value(self, value_str):
        """Safely converts input string to float. Raises ValueError if invalid."""
        temp_str = value_str.strip()
        if not temp_str:
            raise ValueError("Value cannot be empty.")
        try:
            value = float(temp_str)
            # Add some reasonable safety bounds for temps and duration
            if value < -20 or value > 200:
                raise ValueError(f"Value {value} out of safe range (-20 to 200).")
            return value
        except ValueError:
            raise ValueError(f"'{temp_str}' is not a valid number.")

    def _process_command_email(self, email_body):
        """Parses commands from an email body and applies them via SettingsManager."""
        results = []
        commands_processed = 0
        
        # Get current temp units for C-to-F conversion if needed
        current_units = self.settings_manager.get("temp_units", "F")

        lines = [line.strip().lower() for line in email_body.splitlines() if line.strip()]
        
        if not lines:
            return "No commands found in email body."

        for line in lines:
            parts = line.split()
            if not parts:
                continue

            command_key = " ".join(parts[:-1])
            value_str = parts[-1] if len(parts) > 1 else None

            try:
                # --- Control Mode Commands ---
                if line == "control mode ambient":
                    self.settings_manager.set("control_mode", "Ambient Hold")
                    if self.ui: self.ui.root.after(0, self.ui.control_mode_var.set, "Ambient")
                    results.append(f"OK: Control Mode set to Ambient.")
                    commands_processed += 1
                elif line == "control mode beer":
                    self.settings_manager.set("control_mode", "Beer Hold")
                    if self.ui: self.ui.root.after(0, self.ui.control_mode_var.set, "Beer")
                    results.append(f"OK: Control Mode set to Beer.")
                    commands_processed += 1
                elif line == "control mode ramp":
                    self.settings_manager.set("control_mode", "Ramp-Up")
                    if self.ui: self.ui.root.after(0, self.ui.control_mode_var.set, "Ramp")
                    results.append(f"OK: Control Mode set to Ramp.")
                    commands_processed += 1
                elif line == "control mode crash":
                    self.settings_manager.set("control_mode", "Fast Crash")
                    if self.ui: self.ui.root.after(0, self.ui.control_mode_var.set, "Crash")
                    results.append(f"OK: Control Mode set to Crash.")
                    commands_processed += 1
                
                # --- Setpoint & Configuration Commands ---
                elif command_key in ["setpoint ambient", "setpoint beer", "setpoint ramp", "setpoint crash", "setpoint duration", "notification frequency"]:
                    if not value_str:
                        raise ValueError("missing value")
                    
                    value_f = self._parse_setpoint_value(value_str) # Validates and returns float
                    
                    # Convert to Fahrenheit if input is C 
                    # (Skip conversion for Duration and Frequency as they are Time, not Temp)
                    if command_key not in ["setpoint duration", "notification frequency"] and current_units == "C":
                        value_f = (value_f * 9/5) + 32

                    if command_key == "setpoint ambient":
                        self.settings_manager.set("ambient_hold_f", value_f)
                        results.append(f"OK: Ambient Hold set to {value_f:.1f} F.")
                    elif command_key == "setpoint beer":
                        self.settings_manager.set("beer_hold_f", value_f)
                        results.append(f"OK: Beer Hold set to {value_f:.1f} F.")
                    elif command_key == "setpoint ramp":
                        self.settings_manager.set("ramp_up_hold_f", value_f)
                        results.append(f"OK: Ramp-Up Hold set to {value_f:.1f} F.")
                    elif command_key == "setpoint crash":
                        self.settings_manager.set("fast_crash_hold_f", value_f)
                        results.append(f"OK: Fast Crash Hold set to {value_f:.1f} F.")
                    elif command_key == "setpoint duration":
                        self.settings_manager.set("ramp_up_duration_hours", value_f)
                        results.append(f"OK: Ramp Duration set to {value_f:.1f} hours.")
                    
                    # --- NEW COMMAND LOGIC (Renamed) ---
                    elif command_key == "notification frequency":
                        # 1. Get old frequency
                        old_freq = self.settings_manager.get("frequency_hours", 0)
                        # 2. Convert new value to int
                        new_freq = int(value_f)
                        
                        if new_freq < 0:
                            raise ValueError("Frequency cannot be negative.")
                            
                        # 3. Save setting
                        self.settings_manager.set("frequency_hours", new_freq)
                        
                        # 4. Force Scheduler Update
                        self.force_reschedule(old_freq, new_freq)
                        
                        results.append(f"OK: Notification Frequency set to {new_freq} hours.")
                    # -----------------------------------

                    commands_processed += 1

                else:
                    results.append(f"Error: Unknown command '{line}'.")

            except ValueError as e:
                results.append(f"Error parsing '{line}': {e}.")
            except Exception as e:
                results.append(f"Error processing '{line}': {e}.")

        if commands_processed > 0:
            # Force the controller to re-read the setpoints
            if self.ui and self.ui.temp_controller:
                self.ui.root.after(0, self.ui.temp_controller.update_control_logic_and_ui_data)
        
        return "\n".join(results)
        
    def _send_command_reply(self, recipient_email, smtp_config, results_body):
        """Generates and sends the command execution reply."""
        subject = "Fermentation Vault Command Reply"
        
        # Prepend a header to the results
        body = f"Command execution results:\n\n{results_body}"
        
        # --- MODIFICATION: Add the help text to the reply email ---
        help_text_list = self._get_command_help_text()
        body += "\n" + "\n".join(help_text_list)
        # --- END MODIFICATION ---
        
        return self._send_email_or_sms(
            subject, 
            body, 
            recipient_email, 
            smtp_config, 
            "Command Reply"
        )

    def start_scheduler(self):
        """Starts the scheduler and the IMAP listener thread."""
        if not self._scheduler_running:
            self._scheduler_running = True
            self._scheduler_event.clear()
            
            # --- MODIFICATION: Handle both startup logging and initial send delay ---
            freq_h = self.settings_manager.get("frequency_hours", 0)
            
            if freq_h > 0:
                # Part 1: Log "enabled" status at startup
                if self.ui:
                    # --- MODIFICATION: Changed log text ---
                    self.ui.log_system_message(f"Push notifications enabled every {freq_h} hours.")
                    # --- END MODIFICATION ---
                
                # Part 2a: Schedule initial notification in ~60s
                # We do this by "time-traveling" the last_sent_time.
                # (now + 60s) - interval = the time to make the check pass in 60s.
                interval_seconds = self._get_interval_seconds(freq_h)
                self.last_notification_sent_time = time.time() + 60 - interval_seconds
                print("[NotificationManager] Scheduling initial notification in 60s.")
            else:
                # Part 1: Log "disabled" status at startup
                if self.ui:
                    # --- MODIFICATION: Changed log text ---
                    self.ui.log_system_message("Push notifications disabled (Frequency is 'None').")
                    # --- END MODIFICATION ---
                # Set timer normally for when it's turned on later
                self.last_notification_sent_time = time.time()
            # --- END MODIFICATION ---

            # --- NEW: Log Conditional Notification Status at Startup ---
            cond_enabled = self.settings_manager.get("conditional_enabled", False)
            if self.ui:
                if cond_enabled:
                    self.ui.log_system_message("Conditional notifications enabled.")
                else:
                    self.ui.log_system_message("Conditional notifications disabled.")
            # --- END NEW ---
            
            # --- MODIFICATION: Set all timers ---
            self.last_api_fetch_time = time.time()
            self.last_fg_calc_time = time.time()
            # --- END MODIFICATION ---

            # Start main scheduler loop
            if self._scheduler_thread is None or not self._scheduler_thread.is_alive():
                self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
                self._scheduler_thread.start()
            print("[NotificationManager] Scheduler started.")
            
        # Always start IMAP listener
        self.start_status_request_listener()

    def stop_scheduler(self):
        """Stops both the scheduler and IMAP listener threads gracefully."""
        if self._scheduler_running:
            print("[NotificationManager] Stopping scheduler...")
            self._scheduler_running = False
            self._scheduler_event.set() 
            
            self.stop_status_request_listener()
            
            if self._scheduler_thread and self._scheduler_thread.is_alive():
                self._scheduler_thread.join(timeout=2)
            print("[NotificationManager] Scheduler stopped.")

    def force_reschedule(self, old_freq, new_freq):
        """Forces the scheduler to re-evaluate timings and restarts IMAP listener."""
        if self._scheduler_running:
            print("[NotificationManager] Settings changed. Forcing reschedule.")
            
            # --- MODIFICATION: Check if notifications were just turned ON ---
            if (new_freq > 0 and new_freq != "None") and (old_freq == 0 or old_freq == "None"):
                # Part 2b: Schedule initial notification in ~60s
                interval_seconds = self._get_interval_seconds(new_freq)
                self.last_notification_sent_time = time.time() + 60 - interval_seconds
                print("[NotificationManager] Scheduling initial notification in 60s.")
            else:
                # Otherwise, just reset the timer normally (applies to freq change or turning off)
                self.last_notification_sent_time = time.time()
            # --- END MODIFICATION ---
            
            # --- MODIFICATION: Reset all timers ---
            self.last_api_fetch_time = time.time()
            self.last_fg_calc_time = time.time()
            # --- END MODIFICATION ---

            self._last_error_time = {"push": 0.0, "request": 0.0, "fg": 0.0}
            self._scheduler_event.set() # Wake up scheduler
            
            self.stop_status_request_listener()
            self.start_status_request_listener()

    # --- NEW METHOD ---
    def reset_api_timers(self):
        """Resets the timers for API and FG tasks when settings change."""
        if self._scheduler_running:
            print("[NotificationManager] API/FG timers reset by settings change.")
            self.last_api_fetch_time = time.time()
            self.last_fg_calc_time = time.time()
            self._scheduler_event.set() # Wake up scheduler
            if self.ui:
                self.ui.log_system_message("API/FG schedule reset and updated.")
    # --- END NEW METHOD ---

    def _get_interval_seconds(self, frequency_hours):
        """Converts frequency hours (1, 2, 4, 8, 12, 24) to seconds."""
        try:
            return int(frequency_hours) * HOURS_TO_SECONDS
        except (ValueError, TypeError):
            return 24 * HOURS_TO_SECONDS # Default to 24 hours
            
    def _scheduler_loop(self):
        """The main loop for periodic data fetching, FG calcs, and notifications."""
        while self._scheduler_running:
            now = time.time()
            
            # --- 1. API DATA FETCH LOGIC ---
            api_freq_s = self.settings_manager.get("api_call_frequency_s", 1200)
            if self.settings_manager.get("active_api_service") != "OFF" and api_freq_s > 0:
                if now >= self.last_api_fetch_time + api_freq_s:
                    print(f"[NotificationManager] Scheduled time reached. Fetching API data.")
                    current_id = self.settings_manager.get("current_brew_session_id")
                    self.fetch_api_data_now(current_id, is_scheduled=True)
                    self.last_api_fetch_time = now
            
            # --- 2. FG CALCULATION LOGIC ---
            fg_freq_h = self.settings_manager.get("fg_check_frequency_h", 24)
            fg_freq_s = fg_freq_h * 3600 
            if self.settings_manager.get("active_api_service") != "OFF" and fg_freq_s > 0:
                if now >= self.last_fg_calc_time + fg_freq_s:
                    print(f"[NotificationManager] Scheduled time reached. Running FG Calc.")
                    self._run_scheduled_fg_calc()
                    self.last_fg_calc_time = now

            # --- 3. PUSH NOTIFICATION LOGIC ---
            notif_freq_h = self.settings_manager.get("frequency_hours", 0)
            notif_freq_s = self._get_interval_seconds(notif_freq_h)
            
            if notif_freq_s > 0:
                if now >= self.last_notification_sent_time + notif_freq_s:
                    print(f"[NotificationManager] Scheduled time reached. Sending status report.")
                    if self._send_status_message(is_scheduled=True):
                        self.last_notification_sent_time = now

            # --- 4. NEW: CONDITIONAL ALERT LOGIC (Every 60 seconds) ---
            if now >= self.last_conditional_check_time + 60:
                self._check_conditional_alerts()
                self.last_conditional_check_time = now
            # ----------------------------------------------------------
            
            # --- 5. WAIT LOGIC ---
            self._scheduler_event.wait(timeout=10.0) 
            
            if not self._scheduler_running: break
        print("[NotificationManager] Scheduler loop stopped.")
        
    def _check_conditional_alerts(self):
        """Checks current conditions against thresholds and sends alerts if needed."""
        
        # FIX: Retrieve "conditional_enabled" directly using get()
        if not self.settings_manager.get("conditional_enabled", False):
            return

        now = time.time()
        
        # Helper to parse temps safely (returns float or None)
        def get_temp(val):
            try: return float(val)
            except (ValueError, TypeError): return None

        # --- A. TEMPERATURE CHECKS ---
        # 1. Ambient Temp
        amb_actual = get_temp(self.settings_manager.get("amb_temp_actual"))
        # FIX: Retrieve thresholds directly
        amb_min = self.settings_manager.get("conditional_amb_min")
        amb_max = self.settings_manager.get("conditional_amb_max")
        
        if amb_actual is not None and amb_min is not None and amb_max is not None:
            if amb_actual < amb_min or amb_actual > amb_max:
                if now - self._alert_cooldowns["ambient_temp"] > self.ALERT_COOLDOWN_SECONDS:
                    msg = f"Ambient Temp ({amb_actual:.1f}F) is outside range ({amb_min:.1f}-{amb_max:.1f}F)."
                    if self._send_alert_email("Ambient Temp Alert", msg):
                        self._alert_cooldowns["ambient_temp"] = now

        # 2. Beer Temp
        beer_actual = get_temp(self.settings_manager.get("beer_temp_actual"))
        # FIX: Retrieve thresholds directly
        beer_min = self.settings_manager.get("conditional_beer_min")
        beer_max = self.settings_manager.get("conditional_beer_max")
        
        if beer_actual is not None and beer_min is not None and beer_max is not None:
            if beer_actual < beer_min or beer_actual > beer_max:
                if now - self._alert_cooldowns["beer_temp"] > self.ALERT_COOLDOWN_SECONDS:
                    msg = f"Beer Temp ({beer_actual:.1f}F) is outside range ({beer_min:.1f}-{beer_max:.1f}F)."
                    if self._send_alert_email("Beer Temp Alert", msg):
                        self._alert_cooldowns["beer_temp"] = now

        # --- B. SENSOR ERROR CHECKS ---
        error_msg = self.settings_manager.get("sensor_error_message", "")
        
        # Ambient Sensor Lost
        # FIX: Retrieve setting directly
        if self.settings_manager.get("conditional_amb_sensor_lost", False):
            if "Ambient Sensor" in error_msg:
                if now - self._alert_cooldowns["sensor_amb"] > self.ALERT_COOLDOWN_SECONDS:
                    if self._send_alert_email("Sensor Failure", f"Critical: {error_msg}"):
                        self._alert_cooldowns["sensor_amb"] = now

        # Beer Sensor Lost
        # FIX: Retrieve setting directly
        if self.settings_manager.get("conditional_beer_sensor_lost", False):
            if "Beer Sensor" in error_msg:
                if now - self._alert_cooldowns["sensor_beer"] > self.ALERT_COOLDOWN_SECONDS:
                    if self._send_alert_email("Sensor Failure", f"Critical: {error_msg}"):
                         self._alert_cooldowns["sensor_beer"] = now

        # --- C. FG STABLE CHECK ---
        # FIX: Retrieve setting directly
        if self.settings_manager.get("conditional_fg_stable", False):
            fg_status = self.settings_manager.get("fg_status_var", "")
            fg_value = self.settings_manager.get("fg_value_var", "")
            
            if fg_status == "Stable":
                if not self._fg_alert_sent:
                    # Send One-Time Alert
                    msg = f"Fermentation Gravity is STABLE at {fg_value}."
                    if self._send_alert_email("Fermentation Complete", msg):
                        self._fg_alert_sent = True # Latch
                        
            elif fg_status == "" or fg_status == "Pending":
                # Reset latch if we go back to unstable/calculating (e.g. new brew started)
                self._fg_alert_sent = False

    def _send_alert_email(self, subject_prefix, message_body):
        """Sends a high-priority conditional alert email."""
        smtp_cfg = self.settings_manager.get_all_smtp_settings()
        
        # Config Validation
        if not all([smtp_cfg['smtp_server'], smtp_cfg['smtp_port'], smtp_cfg['server_email'], smtp_cfg['server_password']]):
            self._report_error("push", "SMTP details incomplete for Conditional Alert.")
            return False
            
        recipient = smtp_cfg.get('email_recipient')
        if not recipient:
            self._report_error("push", "No recipient email configured for Conditional Alert.")
            return False

        full_subject = f"FermVault ALERT: {subject_prefix}"
        
        # Construct Full Body with Timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        full_body = f"ALERT TRIGGERED AT: {timestamp}\n\n{message_body}\n\n--\nFermVault Monitoring System"

        try:
            success = self._send_email_or_sms(full_subject, full_body, recipient, smtp_cfg, "Conditional Alert")
            if success and self.ui:
                self.ui.log_system_message(f"Conditional Alert Sent: {subject_prefix}")
            return success
        except Exception as e:
            print(f"[NotificationManager] Alert send failed: {e}")
            return False
    
    # --- NEW ACTION IMPLEMENTATIONS ---
    def send_manual_status_message(self):
        """Action handler to send a single status message immediately."""
        def send_task():
            if self._send_status_message(is_scheduled=False):
                self.ui.log_system_message("Manual status message sent successfully.")
            else:
                 self.ui.log_system_message("WARNING: Manual status message failed to send.")
        
        # Run on a new thread to avoid blocking the UI
        threading.Thread(target=send_task, daemon=True).start()
        
    def fetch_api_data_now(self, brew_session_id, is_scheduled=False):
        """Action handler to fetch current API data on demand."""
        if self.settings_manager.get("active_api_service") == "OFF":
            if not is_scheduled: self.ui.log_system_message("API service is OFF. Cannot fetch data.")
            return

        # --- MODIFICATION: Helper function was moved to class level ---
        # def parse_api_timestamp(timestamp_str): ...
        # --- END MODIFICATION ---

        def fetch_task():
            # --- MODIFICATION: Get API logging toggle state ---
            api_logging_enabled = self.settings_manager.get("api_logging_enabled", False)
            # --- END MODIFICATION ---
            
            # --- MODIFICATION: Add logging for scheduled tasks ---
            if not is_scheduled:
                self.ui.log_system_message("Fetching API data...")
            # --- MODIFICATION: Check toggle for scheduled logging ---
            elif is_scheduled and api_logging_enabled:
                self.ui.log_system_message("Scheduled API data fetch running...")
            # --- END MODIFICATION ---
                
            data = self.ui.api_manager.get_api_data("session_data", session_id=brew_session_id)
            
            if data:
                self.settings_manager.set("og_display_var", data.get("og_actual", "-.---"))
                self.settings_manager.set("sg_display_var", data.get("sg_actual", "-.---"))
                
                # Get the two different timestamps
                # --- MODIFICATION: Call the new class method ---
                og_time_str = self._parse_api_timestamp(data.get("og_timestamp"), is_scheduled=is_scheduled)
                sg_time_str = self._parse_api_timestamp(data.get("sg_timestamp"), is_scheduled=is_scheduled)
                # --- END MODIFICATION ---

                # --- FIX: Always set the timestamps. ---
                # The parser will return a blank string if data is None,
                # correctly clearing the UI.
                self.settings_manager.set("og_timestamp_var", og_time_str)
                self.settings_manager.set("sg_timestamp_var", sg_time_str)
                # ----------------------------------------

                # --- MODIFICATION: Add logging for scheduled tasks ---
                if not is_scheduled:
                    self.ui.log_system_message("API data updated.")
                # --- MODIFICATION: Check toggle for scheduled logging ---
                elif is_scheduled and api_logging_enabled:
                    self.ui.log_system_message("Scheduled API data updated.")
                # --- END MODIFICATION ---
                    
                self.ui.root.after(0, self.ui._update_data_display) # Force UI refresh
                
            else:
                # --- MODIFICATION: Add logging for scheduled tasks ---
                if not is_scheduled:
                    self.ui.log_system_message("API data fetch failed.")
                # --- MODIFICATION: Check toggle for scheduled logging ---
                elif is_scheduled and api_logging_enabled:
                    self.ui.log_system_message("Scheduled API data fetch failed.")
                # --- END MODIFICATION ---

        if is_scheduled:
            fetch_task() # Run synchronously if called from scheduler
        else:
            threading.Thread(target=fetch_task, daemon=True).start() # Run in thread if called from UI

    # --- NEW HELPER METHOD (Moved from fetch_api_data_now) ---
    def _parse_api_timestamp(self, timestamp_str, is_scheduled=False):
        """Helper to parse API timestamps and format them."""
        if not timestamp_str:
            return "----/--/-- --:--:--"
            
        # --- MODIFICATION: Manually calculate the system's offset from UTC ---
        try:
            # This calculates the exact offset (e.g., -6 hours)
            # by comparing the Pi's local time (naive) to UTC time (naive).
            LOCAL_OFFSET = datetime.now() - datetime.utcnow()
        except Exception:
            # Fallback in case of any error
            LOCAL_OFFSET = timedelta(hours=0)
        # --- END MODIFICATION ---

        try:
            # Try to parse ISO format (e.g., 2025-11-06T21:55:00Z or ...+00:00)
            # This creates an "aware" datetime object in UTC
            dt_utc = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            
            # --- MODIFICATION: Apply the calculated offset ---
            # We add the offset (e.g., -6 hours) to the UTC time
            dt_local = dt_utc + LOCAL_OFFSET 
            return dt_local.strftime("%Y-%m-%d %H:%M:%S")
            # --- END MODIFICATION ---
        except ValueError:
            try:
                # Try to parse 'YYYY-MM-DD HH:MM:SS' format (assume UTC)
                # This creates a "naive" datetime object
                dt_naive_utc = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                
                # --- MODIFICATION: Apply the calculated offset ---
                dt_local = dt_naive_utc + LOCAL_OFFSET
                return dt_local.strftime("%Y-%m-%d %H:%M:%S")
                # --- END MODIFICATION ---
            except ValueError:
                try:
                    # Try to parse date-only format 'YYYY-MM-DD' (assume UTC)
                    dt_naive_utc = datetime.strptime(timestamp_str, "%Y-%m-%d")
                    # --- MODIFICATION: Apply the calculated offset ---
                    dt_local = dt_naive_utc + LOCAL_OFFSET
                    # We only want the date part, but the offset might change the day
                    return dt_local.strftime("%Y-%m-%d 00:00:00") 
                    # --- END MODIFICATION ---
                except ValueError:
                    # If all parsing fails
                    if not is_scheduled and self.ui: 
                        self.ui.log_system_message(f"Error: Could not parse API timestamp '{timestamp_str}'.")
                    return "Invalid Timestamp"

    def run_fg_calc_and_update_ui(self):
        """Action handler to run FG calculation and update UI status."""
        
        if self.settings_manager.get("active_api_service") == "OFF":
            # --- MODIFICATION: Use new error message ---
            self.ui.log_system_message("FG calculation requires an active API service.")
            self.settings_manager.set("fg_status_var", "")
            # --- END MODIFICATION ---
            self.settings_manager.set("fg_value_var", "-.---")
            self.ui.root.after(0, self.ui._update_data_display)
            return
            
        def fg_task():
            self.ui.log_system_message("Running Final Gravity stability analysis...")
            # FGCalculator must be instantiated here or passed in __init__
            fg_calc = self.ui.fg_calculator_instance 
            if not fg_calc: 
                 self.ui.log_system_message("FG Calculator not initialized.")
                 return

            results = fg_calc.calculate_fg()
            
            # --- MODIFICATION: Simplified Logic for FG Vars and Logging ---
            params = results.get('settings', {})
            tol = params.get('tolerance', 'N/A')
            win = params.get('window_size', 'N/A')
            out = params.get('max_outliers', 'N/A')
            
            value_msg = "-.---"
            status_msg = "" # --- FIX: Default to blank
            log_msg = ""
            has_error = False

            if results.get("stable"):
                value_msg = f"{results['results']['average_sg']:.3f}"
                status_msg = "Stable"
                
                # --- MODIFICATION: Use parser for timestamps ---
                first_ts = self._parse_api_timestamp(results['results']['first_timestamp'], is_scheduled=True)
                last_ts = self._parse_api_timestamp(results['results']['last_timestamp'], is_scheduled=True)
                log_msg = f"FG Calculation: Stable: {value_msg}. Range: {first_ts} to {last_ts}. (Range Tolerance: {tol}, Records Window: {win}, Max Outliers: {out})"
                # --- END MODIFICATION ---
            else:
                value_msg = "-.---"
                status_msg = "" # --- FIX: Set to blank on error/pending
                
                # Check for errors to log them
                if results.get("error"): 
                    log_msg = f"FG Calculation: Pending ({results['error']})"
                    has_error = True
                elif results.get('results') and results['results'].get("error"): 
                    log_msg = f"FG Calculation: Pending ({results['results']['error']})"
                    has_error = True
                
                if not has_error:
                    # No error, just pending: Log with params
                    log_msg = f"FG Calculation: Pending. Params: (Tol: {tol}, Win: {win}, Out: {out})"
            # --- END MODIFICATION ---
            
            self.settings_manager.set("fg_status_var", status_msg)
            self.settings_manager.set("fg_value_var", value_msg)
            
            self.ui.log_system_message(log_msg) # Log the detailed message
            
            self.ui.root.after(0, self.ui._update_data_display)

        threading.Thread(target=fg_task, daemon=True).start()

    # --- IMAP STATUS REQUEST LISTENER ---
    
    def _status_request_listener_loop(self):
        """Dedicated thread loop for checking the status request email every minute."""
        print("[NotificationManager] Status Request Listener loop started.")
        while self._status_request_running:
            self._check_for_status_requests()
            # Use the event to wait, but make sure it's not the main scheduler event if they have different timings
            # For simplicity, we'll use a simple sleep here
            time.sleep(self._status_request_interval_seconds)
            if not self._status_request_running:
                break 

    def start_status_request_listener(self):
        # --- MODIFICATION: Added 'enable_status_request' check ---
        if not self._status_request_running:
            
            # --- NEW GUARD CLAUSE ---
            if not self.settings_manager.get("enable_status_request", False):
                # --- MODIFICATION: Log to UI ---
                # --- MODIFICATION: Update log message text ---
                log_msg = "Email Control (Status & Commands) disabled."
                # --- END MODIFICATION ---
                print(f"[NotificationManager] {log_msg}")
                if self.ui:
                    self.ui.log_system_message(log_msg)
                # --- END MODIFICATION ---
                return
            # --- END NEW GUARD CLAUSE ---
            
            self._status_request_running = True
            if self._status_request_listener_thread is None or not self._status_request_listener_thread.is_alive():
                self._status_request_listener_thread = threading.Thread(target=self._status_request_listener_loop, daemon=True)
                self._status_request_listener_thread.start()
                
                # --- MODIFICATION: Log to UI ---
                log_msg = "Email Control (Status & Commands) listener activated."
                print(f"[NotificationManager] {log_msg}")
                if self.ui:
                    self.ui.log_system_message(log_msg)
                # --- END MODIFICATION ---
        # --- END MODIFICATION ---
        
    def stop_status_request_listener(self):
        if self._status_request_running:
            print("[NotificationManager] Stopping Status Request Listener...")
            self._status_request_running = False
            if self._status_request_listener_thread and self._status_request_listener_thread.is_alive():
                self._status_request_listener_thread.join(timeout=2)
            print("[NotificationManager] Status Request Listener stopped.")

    def _check_for_status_requests(self):
        """Connects to IMAP and checks for 'STATUS' or 'COMMAND' emails."""
        status_settings = self.settings_manager.get_all_status_request_settings()
        
        # --- MODIFICATION: Removed 'enable_status_request' check ---
        
        rpi_email = status_settings['rpi_email_address']
        rpi_password = status_settings['rpi_email_password']
        imap_server = status_settings['imap_server']
        imap_port = status_settings['imap_port']
        authorized_senders = [s.strip() for s in status_settings.get('authorized_sender', '').split(',') if s.strip()]
        
        required_config = all([rpi_email, rpi_password, imap_server, imap_port, authorized_senders])
        if not required_config:
            self._report_error("request", "IMAP/SMTP configuration incomplete for Status Request.")
            return

        try:
            mail = imaplib.IMAP4_SSL(imap_server, imap_port)
            mail.login(rpi_email, rpi_password)
            mail.select('inbox')
            
            smtp_config = self.settings_manager.get_all_smtp_settings()

            for sender in authorized_senders:
                # Search for all unseen emails from this sender
                search_query = f'(UNSEEN FROM "{sender}")'
                status, data = mail.search(None, search_query)
                email_ids = data[0].split()

                if not email_ids:
                    continue

                for email_id in email_ids:
                    # Fetch the full email
                    status, msg_data = mail.fetch(email_id, '(RFC822)')
                    if status != 'OK':
                        continue
                        
                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)
                    
                    # Decode the subject
                    subject_header = msg['subject']
                    subject_tuple = email.header.decode_header(subject_header)[0]
                    subject = subject_tuple[0]
                    if isinstance(subject, bytes):
                        # use the encoding provided, or 'utf-8' as a fallback
                        subject = subject.decode(subject_tuple[1] or 'utf-8')
                    
                    subject = subject.upper().strip()
                    
                    # --- 1. Process STATUS request ---
                    if subject == "STATUS":
                        send_ok = self._send_status_report(sender, smtp_config)
                        
                        if send_ok:
                            mail.store(email_id, '+FLAGS', '\\Seen')
                            self.ui.log_system_message(f"STATUS request from {sender} processed and reply sent.")
                        else:
                            self.ui.log_system_message(f"WARNING: Reply to {sender} failed. STATUS email not marked as read.")
                    
                    # --- 2. Process COMMAND request ---
                    elif subject == "COMMAND":
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    body = part.get_payload(decode=True).decode('utf-8')
                                    break
                        else:
                            body = msg.get_payload(decode=True).decode('utf-8')

                        if not body:
                            results = "Error: Could not find plain text body in command email."
                        else:
                            results = self._process_command_email(body)
                        
                        # Send the reply with the results
                        send_ok = self._send_command_reply(sender, smtp_config, results)

                        if send_ok:
                            mail.store(email_id, '+FLAGS', '\\Seen')
                            self.ui.log_system_message(f"COMMAND from {sender} processed. Results sent.")
                        else:
                             self.ui.log_system_message(f"WARNING: COMMAND reply to {sender} failed. Email not marked as read.")
                    
                    # --- 3. (Else) Ignore other subjects ---
                    else:
                        print(f"Ignoring email from {sender} with subject: {subject}")


            mail.logout()

        except imaplib.IMAP4.error as e:
            self._report_error("request", f"IMAP Error: Check IMAP/Port/Password/App Password. Error: {e}")
        except Exception as e:
            self._report_error("request", f"Unexpected Status Request Error: {e}")


    # --- MESSAGE GENERATION ---
    
    def _format_message_body(self, is_status_request=False):
        """Generates a structured status body for email/text."""
        
        # NOTE: Using F for internal control logic, so display in F or C based on settings
        units = self.settings_manager.get("temp_units", "F")
        
        # Get data from settings manager (updated by controller)
        beer_set = self.settings_manager.get("beer_setpoint_current", "--.-")
        amb_min = self.settings_manager.get("amb_min_setpoint", "--.-")
        amb_max = self.settings_manager.get("amb_max_setpoint", "--.-")
        
        beer_actual = self.settings_manager.get("beer_temp_actual", "--.-")
        amb_actual = self.settings_manager.get("amb_temp_actual", "--.-")

        # Conversion helper (from F)
        def convert(temp_f):
             try:
                 temp = float(temp_f)
                 return f"{temp:.1f}" if units == "F" else f"{((temp - 32) * 5/9):.1f}"
             except:
                 return "--.-"
        
        # Fetch status variables
        brew_session_title = self.settings_manager.get("brew_session_title", "N/A")
        
        # --- MODIFICATION: Translate internal mode name to display name ---
        INTERNAL_TO_DISPLAY_MAP = {
            "Ambient Hold": "Ambient",
            "Beer Hold": "Beer",
            "Ramp-Up": "Ramp",
            "Fast Crash": "Crash",
        }
        internal_mode = self.settings_manager.get('control_mode')
        display_mode = INTERNAL_TO_DISPLAY_MAP.get(internal_mode, "Beer")
        # --- END MODIFICATION ---
        
        # --- NEW: Get Relay and Restriction Status ---
        heat_state = self.settings_manager.get("heat_state", "Heating OFF")
        cool_state = self.settings_manager.get("cool_state", "Cooling OFF")
        cool_restriction = self.settings_manager.get("cool_restriction_status", "")
        # --- END NEW ---
        
        body_lines = [
            f"Fermentation Vault Status Report ({units})",
            f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"Mode: {display_mode}",
            f"Brew: {brew_session_title}",
            "",
            "--- Setpoints ---",
            f"Beer Target: {convert(beer_set)} {units}",
            f"Ambient Envelope: {convert(amb_min)} - {convert(amb_max)} {units}",
            "",
            "--- Actual Temps ---",
            f"Beer Actual: {convert(beer_actual)} {units}",
            f"Ambient Actual: {convert(amb_actual)} {units}",
            "",
            "--- Relay Status ---",
            f"Heating: {heat_state}",
            f"Cooling: {cool_state}",
        ]
        
        # --- NEW: Conditionally add restriction message if it exists ---
        if cool_restriction:
            body_lines.append(f"Cooling Status: {cool_restriction}")
        # --- END NEW ---

        body_lines.extend([
            "",
            "--- Gravity Status ---",
            f"OG: {self.settings_manager.get('og_display_var', '-.---')}",
            f"SG: {self.settings_manager.get('sg_display_var', '-.---')}",
            f"FG Status: {self.settings_manager.get('fg_status_var', 'Pending')}",
        ])
        
        # --- MODIFICATION: Call the new helper function ---
        body_lines.extend(self._get_command_help_text())
        # --- END MODIFICATION ---
        
        return "\n".join(body_lines)
    
    def _run_scheduled_fg_calc(self):
        """Internal, blocking version of FG calc for the scheduler."""
        log_prefix = "[NotificationManager]"
        
        if not (self.ui and self.ui.fg_calculator_instance):
            print(f"{log_prefix} FG Calculator not available for scheduled run.")
            return
            
        if self.settings_manager.get("active_api_service") == "OFF":
            print(f"{log_prefix} API service is OFF. Skipping scheduled FG calc.")
            # --- MODIFICATION: Use new error message ---
            self.settings_manager.set("fg_status_var", "")
            # --- END MODIFICATION ---
            self.settings_manager.set("fg_value_var", "-.---")
            if self.ui: self.ui.root.after(0, self.ui._update_data_display)
            return
            
        print(f"{log_prefix} Running scheduled Final Gravity stability analysis...")
        fg_calc = self.ui.fg_calculator_instance 
        results = fg_calc.calculate_fg()

        # --- MODIFICATION: Simplified Logic for FG Vars and Logging ---
        params = results.get('settings', {})
        tol = params.get('tolerance', 'N/A')
        win = params.get('window_size', 'N/A')
        out = params.get('max_outliers', 'N/A')
        
        value_msg = "-.---"
        status_msg = "" # --- FIX: Default to blank
        log_msg = ""
        has_error = False

        if results.get("stable"):
            value_msg = f"{results['results']['average_sg']:.3f}"
            status_msg = "Stable"
            
            # --- MODIFICATION: Use parser for timestamps ---
            first_ts = self._parse_api_timestamp(results['results']['first_timestamp'], is_scheduled=True)
            last_ts = self._parse_api_timestamp(results['results']['last_timestamp'], is_scheduled=True)
            log_msg = f"FG Calculation: Stable: {value_msg}. Range: {first_ts} to {last_ts}. (Range Tolerance: {tol}, Records Window: {win}, Max Outliers: {out})"
            # --- END MODIFICATION ---
        else:
            value_msg = "-.---"
            status_msg = "" # --- FIX: Set to blank on error/pending
            
            # Check for errors to log them
            if results.get("error"): 
                log_msg = f"FG Calculation: Pending ({results['error']})"
                has_error = True
            elif results.get('results') and results['results'].get("error"): 
                log_msg = f"FG Calculation: Pending ({results['results']['error']})"
                has_error = True
            
            if not has_error:
                # No error, just pending
                log_msg = f"FG Calculation: Pending. Params: (Tol: {tol}, Win: {win}, Out: {out})"
        # --- END MODIFICATION ---
        
        self.settings_manager.set("fg_status_var", status_msg)
        self.settings_manager.set("fg_value_var", value_msg)
        
        print(f"{log_prefix} Scheduled FG Calc complete. Status: {status_msg}")
        
        # We must also force the main UI thread to update its display
        if self.ui:
            self.ui.log_system_message(log_msg) # Log detailed message to UI
            self.ui.root.after(0, self.ui._update_data_display)
            
    def _send_email_or_sms(self, subject, body, recipient_address, smtp_cfg, message_type_for_log):
        """Generic email sending function (adapted from KegLevel)."""
        status_message = f"Sending {message_type_for_log} to {recipient_address}..."
        if self.ui: self.ui.log_system_message(status_message)
        
        try:
            with smtplib.SMTP(smtp_cfg['smtp_server'], int(smtp_cfg['smtp_port'])) as server:
                server.starttls()
                server.login(smtp_cfg['server_email'], smtp_cfg['server_password'])
                
                msg = MIMEText(body)
                msg['Subject'] = subject
                msg['From'] = smtp_cfg['server_email']
                msg['To'] = recipient_address

                server.sendmail(smtp_cfg['server_email'], [recipient_address], msg.as_string())
                
            status_message = f"{message_type_for_log} sent successfully to {recipient_address}."
            if self.ui: self.ui.log_system_message(status_message)
            return True
        except Exception as e:
            error_msg = f"Error sending {message_type_for_log}: {e}"
            self._report_error("push", error_msg) # Use the error reporting function
            return False

    def _send_status_report(self, recipient_email, smtp_config):
        """Generates and sends the detailed status report email."""
        subject = "Fermentation Vault Status Reply"
        body = self._format_message_body(is_status_request=True)
        
        return self._send_email_or_sms(
            subject, 
            body, 
            recipient_email, 
            smtp_config, 
            "Status Request Reply"
        )

    def _send_status_message(self, is_scheduled=False):
        """Sends the periodic push notification. (SIMPLIFIED)"""
        
        # --- MODIFICATION: Frequency check is now the main guard ---
        notif_freq_h = self.settings_manager.get("frequency_hours", 0)
        if notif_freq_h == 0:
            if not is_scheduled:
                self.ui.log_system_message("Notifications are disabled (Frequency is 'None').")
            return False

        smtp_cfg = self.settings_manager.get_all_smtp_settings()
        subject = f"Fermentation Vault Scheduled Report"
        if not is_scheduled:
            subject = f"Fermentation Vault Manual Report"
            
        body = self._format_message_body()
        
        config_ok = all([smtp_cfg['smtp_server'], smtp_cfg['smtp_port'], smtp_cfg['server_email'], smtp_cfg['server_password']])
        if not config_ok:
            self._report_error("push", "SMTP/sender details incomplete.")
            return False

        # --- MODIFICATION: Removed all SMS and notif_method logic ---
        email_ok = False
        recipient_email = smtp_cfg.get('email_recipient')
        
        if recipient_email:
            # Send to all recipients in the email_recipient field
            all_recipients = [s.strip() for s in recipient_email.split(',') if s.strip()]
            for r in all_recipients:
                # Set email_ok to True if *any* send succeeds
                if self._send_email_or_sms(subject, body, r, smtp_cfg, "Scheduled Email"):
                    email_ok = True
        
        if not email_ok and not is_scheduled:
             self.ui.log_system_message("No valid recipients found or send failed.")
             return False
             
        return email_ok

    def _report_error(self, error_type, message):
        """Reports a configuration error once per hour."""
        now = time.time()
        last_reported = self._last_error_time.get(error_type, 0.0)
        
        if now - last_reported > ERROR_DEBOUNCE_INTERVAL_SECONDS:
            error_msg = f"{error_type.capitalize()} Notification Error: {message}"
            if self.ui: self.ui.log_system_message(error_msg)
            self._last_error_time[error_type] = now
            return True
        return False
