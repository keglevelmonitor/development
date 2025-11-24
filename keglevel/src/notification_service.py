# keglevel app
# 
# notification_service.py
import smtplib
import threading
import time
import math
import sys
from datetime import datetime
import imaplib
from email.mime.text import MIMEText
import email
import json
import os

LITERS_TO_GALLONS = 0.264172
OZ_TO_LITERS = 0.0295735 # Added constant for oz to liter conversion
ERROR_DEBOUNCE_INTERVAL_SECONDS = 3600
STATUS_REQUEST_SUBJECT = "STATUS"

class NotificationService:
    def __init__(self, settings_manager, ui_manager):
        self.settings_manager = settings_manager
        self.ui_manager = ui_manager
        self.ui_manager_status_update_cb = None 

        self._scheduler_running = False
        self._scheduler_thread = None
        self._scheduler_event = threading.Event()
        self.last_notification_sent_time = 0
        
        # --- NEW: Status Request Variables ---
        self._status_request_listener_thread = None
        self._status_request_running = False
        self._status_request_interval_seconds = 60 # Check every minute
        # --- END NEW ---
        
        self._last_error_time = {
            "push": 0.0,
            "volume": 0.0,
            "temperature": 0.0
        }

    def _get_interval_seconds(self, frequency_str):
        if frequency_str == "Hourly": return 3600
        elif frequency_str == "Daily": return 3600 * 24
        elif frequency_str == "Weekly": return 3600 * 24 * 7
        elif frequency_str == "Monthly": return 3600 * 24 * 30
        print(f"NotificationService: Unknown frequency '{frequency_str}', defaulting to Daily.")
        return 3600 * 24
        
    def _get_formatted_temp(self, temp_f, display_units):
        """Converts F to C if metric is selected and returns formatted value and unit."""
        if temp_f is None:
            return "--.-", "F" if display_units == "imperial" else "C"

        if display_units == "imperial":
            return f"{temp_f:.1f}", "F"
        else:
            temp_c = (temp_f - 32) * (5/9)
            return f"{temp_c:.1f}", "C"
        
    def _report_config_error(self, error_type, message, is_push_notification):
        """Reports a configuration error once per ERROR_DEBOUNCE_INTERVAL_SECONDS."""
        
        now = time.time()
        last_reported = self._last_error_time.get(error_type, 0.0)
        
        if now - last_reported > ERROR_DEBOUNCE_INTERVAL_SECONDS:
            error_msg = f"{error_type.capitalize()} Notification Error: {message}"
            print(f"NotificationService: {error_msg}")
            
            if is_push_notification and self.ui_manager_status_update_cb: 
                 self.ui_manager_status_update_cb(error_msg)
            
            self._last_error_time[error_type] = now
            return True
        return False
        
    # --- NEW HELPER: Load workflow data from disk directly ---
    def _get_workflow_data_from_disk(self):
        """
        Loads the process flow data and beverage names directly from JSON files,
        without relying on the ProcessFlowApp being open.
        """
        base_dir = self.settings_manager.get_base_dir()
        workflow_file = os.path.join(base_dir, "process_flow.json")
        beverage_library = self.settings_manager.get_beverage_library()
        beverage_map = {b['id']: b['name'] for b in beverage_library.get('beverages', []) if 'id' in b and 'name' in b}
        
        if os.path.exists(workflow_file):
            try:
                with open(workflow_file, 'r') as f:
                    data = json.load(f)
                    return data.get('columns', {}), beverage_map
            except Exception:
                return {}, beverage_map
        return {}, beverage_map
    # --- END NEW HELPER ---

    def _format_message_body(self, tap_index=None, is_conditional=False, trigger_type="volume"):
        display_units = self.settings_manager.get_display_units()
        displayed_taps_count = self.settings_manager.get_displayed_taps()
        sensor_labels = self.settings_manager.get_sensor_labels()
        # --- NEW: Get configurable pour settings ---
        pour_settings = self.settings_manager.get_pour_volume_settings() 
        # ------------------------------------------
        
        current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        temp_logic = self.ui_manager.temp_logic
        current_temp_f = temp_logic.last_known_temp_f if temp_logic else None
        
        # --- CONDITIONAL NOTIFICATIONS: TAP VOLUME ---
        if is_conditional and trigger_type == "volume":
            cond_notif_settings = self.settings_manager.get_conditional_notification_settings()
            threshold_liters = cond_notif_settings.get('threshold_liters')
            actual_liters = self.ui_manager.last_known_remaining_liters[tap_index]
            
            body_lines = [f"Timestamp: {current_time_str}"]
            
            if display_units == "imperial":
                unit = "gallons"
                threshold_val = threshold_liters * LITERS_TO_GALLONS if threshold_liters is not None else None
                actual_val = actual_liters * LITERS_TO_GALLONS if actual_liters is not None else None
            else: # metric
                unit = "liters"
                threshold_val = threshold_liters
                actual_val = actual_liters

            body_lines.append(f"Threshold: {threshold_val:.2f} {unit}" if threshold_val is not None and threshold_val >= 0 else f"Threshold: -- {unit}")
            body_lines.append(f"Actual: {actual_val:.2f} {unit}" if actual_val is not None and actual_val >= 0 else f"Actual: -- {unit}")

            # Append current temperature
            current_temp_display, current_temp_unit = self._get_formatted_temp(current_temp_f, display_units)
            body_lines.append(f"Current kegerator temp: {current_temp_display} {current_temp_unit}")
            
            return "\n".join(body_lines)

        # --- CONDITIONAL NOTIFICATIONS: TEMPERATURE RANGE ---
        elif is_conditional and trigger_type == "temperature":
            cond_notif_settings = self.settings_manager.get_conditional_notification_settings()
            low_temp_f = cond_notif_settings.get('low_temp_f')
            high_temp_f = cond_notif_settings.get('high_temp_f')
            
            body_lines = [f"Timestamp: {current_time_str}"]

            low_temp_display, _ = self._get_formatted_temp(low_temp_f, display_units)
            high_temp_display, _ = self._get_formatted_temp(high_temp_f, display_units)
            current_temp_display, current_temp_unit = self._get_formatted_temp(current_temp_f, display_units)

            threshold_line = f"Threshold: {low_temp_display} - {high_temp_display} {current_temp_unit}"
            body_lines.append(threshold_line)
            
            body_lines.append(f"Actual: {current_temp_display} {current_temp_unit}")
            
            return "\n".join(body_lines)
            
        # --- STATUS REQUEST NOTIFICATIONS ---
        elif is_conditional and trigger_type == "status_request":
            
            body_lines = [
                f"Timestamp: {current_time_str}", 
                "",
                "--- Tap Status ---"
            ]
            
            for i in range(displayed_taps_count):
                tap_label = sensor_labels[i] if i < len(sensor_labels) else f"Tap {i+1}"
                
                remaining_liters = None
                if self.ui_manager and i < self.ui_manager.num_sensors:
                    remaining_liters = self.ui_manager.last_known_remaining_liters[i]

                body_lines.append(f"Tap {i+1} ({tap_label}):")

                if remaining_liters is not None and remaining_liters >= 0:
                    liters_remaining = remaining_liters
                    
                    # Use configured metric pour size (ml)
                    pour_ml = pour_settings['metric_pour_ml']
                    liters_per_pour = pour_ml / 1000.0
                    servings_remaining = math.floor(liters_remaining / liters_per_pour) if liters_per_pour > 0 else 0
                    
                    body_lines.append(f"  Liters remaining: {liters_remaining:.2f}")
                    body_lines.append(f"  {pour_ml} ml pours: {int(servings_remaining)}")
                else:
                    body_lines.append(f"  Liters remaining: --")
                    body_lines.append(f"  {pour_settings['metric_pour_ml']} ml pours: --")
                
                body_lines.append("")
                        
            # --- Current Temperature (RENAMED) ---
            body_lines.append("--- Current Temperature ---")
            current_temp_display, current_temp_unit = self._get_formatted_temp(current_temp_f, display_units)
            body_lines.append(f"Temperature: {current_temp_display} {current_temp_unit}")

            # --- Temperature Records ---
            body_lines.append("")
            body_lines.append("--- Temperature Records ---")
            
            temp_log = self.ui_manager.temp_logic.get_temperature_log() if self.ui_manager.temp_logic else {}
            
            # Header
            body_lines.append("Period | High | Low | Average")
            body_lines.append("------|-----|----|---------")

            for period in ["day", "week", "month"]:
                data = temp_log.get(period, {})
                
                # Format to nn.n (or "--")
                high_val = f"{data.get('high'):.1f}" if data.get('high') is not None else "--"
                low_val = f"{data.get('low'):.1f}" if data.get('low') is not None else "--"
                avg_val = f"{data.get('avg'):.1f}" if data.get('avg') is not None else "--"
                
                period_name = period.capitalize()
                
                body_lines.append(f"{period_name.ljust(6)}| {high_val.center(4)} | {low_val.center(3)} | {avg_val.center(7)}")

            # --- Workflow Status ---
            body_lines.append("")
            body_lines.append("--- KegLevel Workflow Status ---")
            
            workflow_data, beverage_map = self._get_workflow_data_from_disk()
            
            workflow_columns = {
                "lagering_or_finishing": "Lagering or Finishing",
                "fermenting": "Fermenting",
                "on_deck": "On Deck",
                "on_rotation": "On Rotation"
            }
            
            for col_key, col_title in workflow_columns.items():
                
                beer_ids = workflow_data.get(col_key, [])
                body_lines.append(f"{col_title}:")
                
                if not beer_ids:
                    body_lines.append("  -- empty --")
                else:
                    for beer_id in beer_ids:
                        beer_name = beverage_map.get(beer_id, f"Unknown ID ({beer_id[:4]})")
                        body_lines.append(f"  {beer_name}")
                body_lines.append("")
            
            return "\n".join(body_lines)


        # --- PUSH NOTIFICATIONS (DEFAULT) ---
        else: 
            body_lines = [f"Timestamp: {current_time_str}", ""] 
            
            for i in range(displayed_taps_count):
                tap_label = sensor_labels[i] if i < len(sensor_labels) else f"Tap {i+1}"
                
                remaining_liters = None
                if self.ui_manager and i < self.ui_manager.num_sensors:
                    remaining_liters = self.ui_manager.last_known_remaining_liters[i]

                body_lines.append(f"Tap {i+1}: {tap_label}")

                if remaining_liters is not None and remaining_liters >= 0:
                    if display_units == "imperial":
                        gallons = remaining_liters * LITERS_TO_GALLONS
                        
                        # Use configured imperial pour size (oz)
                        pour_oz = pour_settings['imperial_pour_oz']
                        liters_per_pour = pour_oz * OZ_TO_LITERS
                        servings_remaining = math.floor(remaining_liters / liters_per_pour) if liters_per_pour > 0 else 0
                        
                        body_lines.append(f"Gallons remaining: {gallons:.2f}")
                        body_lines.append(f"{pour_oz} oz pours: {int(servings_remaining)}")
                    else: # metric
                        liters = remaining_liters
                        
                        # Use configured metric pour size (ml)
                        pour_ml = pour_settings['metric_pour_ml']
                        liters_per_pour = pour_ml / 1000.0
                        servings_remaining = math.floor(liters / liters_per_pour) if liters_per_pour > 0 else 0
                        
                        body_lines.append(f"Liters remaining: {liters:.2f}")
                        body_lines.append(f"{pour_ml} ml pours: {int(servings_remaining)}")
                else:
                    unit1 = "Gallons remaining" if display_units == "imperial" else "Liters remaining"
                    
                    if display_units == "imperial":
                        unit2 = f"{pour_settings['imperial_pour_oz']} oz pours"
                    else:
                        unit2 = f"{pour_settings['metric_pour_ml']} ml pours"
                        
                    body_lines.append(f"{unit1}: --")
                    body_lines.append(f"{unit2}: --")
                
                if i < displayed_taps_count - 1:
                    body_lines.append("")
                        
            return "\n".join(body_lines)


    def _send_email_or_sms(self, subject, body, recipient_address, smtp_cfg, message_type_for_log):
        status_message = f"Sending {message_type_for_log} to {recipient_address}..."
        print(f"NotificationService: {status_message}")
        if self.ui_manager_status_update_cb: self.ui_manager_status_update_cb(status_message)
        try:
            with smtplib.SMTP(smtp_cfg['server'], int(smtp_cfg['port'])) as server:
                server.starttls(); server.login(smtp_cfg['email'], smtp_cfg['password'])
                message = f"Subject: {subject}\n\n{body}"; server.sendmail(smtp_cfg['email'], recipient_address, message.encode('utf-8'))
            status_message = f"{message_type_for_log} sent successfully to {recipient_address}."
            print(f"NotificationService: {status_message}")
            if self.ui_manager_status_update_cb: self.ui_manager_status_update_cb(status_message)
            return True
        except smtplib.SMTPAuthenticationError as e:
            error_msg = "SMTP Auth Error (check email/password/app password)."
            print(f"NotificationService: {error_msg} Details: {e}")
            if self.ui_manager_status_update_cb: self.ui_manager_status_update_cb(f"Error {message_type_for_log}: Auth Failed")
        except Exception as e:
            error_msg = f"Error sending {message_type_for_log}: {e}"
            print(f"NotificationService: {error_msg}")
            if self.ui_manager_status_update_cb: self.ui_manager_status_update_cb(error_msg)
        return False

    def send_push_notification(self, is_initial_send=False):
        notif_settings = self.settings_manager.get_push_notification_settings()
        notification_type = notif_settings.get('notification_type', 'None')
        if notification_type == 'None':
            if is_initial_send:
                print("NotificationService: Initial check: Push notification type is 'None'. No message sent.")
                if self.ui_manager_status_update_cb:
                    self.ui_manager_status_update_cb("Push Notifications: Off (Initial Check)")
            return False

        subject = "KegLevel Report"
        body = self._format_message_body()
        smtp_config = {
            'server': notif_settings.get('smtp_server'), 'port': notif_settings.get('smtp_port'),
            'email': notif_settings.get('server_email'), 'password': notif_settings.get('server_password')
        }
        
        config_ok = all([smtp_config['server'], smtp_config['port'], smtp_config['email'], smtp_config['password']])
        if not config_ok:
            self._report_config_error("push", "SMTP/sender details incomplete.", True)
            return False

        email_ok, sms_ok = None, None
        
        if notification_type in ["Email", "Both"]:
            recipient_email = notif_settings.get('email_recipient')
            if recipient_email:
                email_ok = self._send_email_or_sms(subject, body, recipient_email, smtp_config, "Email")
            else:
                self._report_config_error("push", "Email recipient not configured.", True)
                
        if notification_type in ["Text", "Both"]:
            sms_number, carrier_gateway = notif_settings.get('sms_number'), notif_settings.get('sms_carrier_gateway')
            if sms_number and carrier_gateway:
                sms_ok = self._send_email_or_sms(subject, body, f"{sms_number}{carrier_gateway}", smtp_config, "Text")
            else:
                self._report_config_error("push", "SMS details not configured.", True)

        final_status_parts = []
        if email_ok is not None: final_status_parts.append(f"Email {'OK' if email_ok else 'Failed'}")
        if sms_ok is not None: final_status_parts.append(f"Text {'OK' if sms_ok else 'Failed'}")

        if final_status_parts:
            summary_message = f"Last send: {'; '.join(final_status_parts)}"
            if self.ui_manager_status_update_cb: self.ui_manager_status_update_cb(summary_message)
            return email_ok or sms_ok
        elif notification_type != "None":
            if self.ui_manager_status_update_cb:
                self.ui_manager_status_update_cb("Push notification configured but no valid recipients/details.")
        return False
        
    def send_conditional_notification(self, tap_index, current_liters, threshold_liters):
        cond_notif_settings = self.settings_manager.get_conditional_notification_settings()
        notification_type = cond_notif_settings.get('notification_type', 'None')
        if notification_type == 'None':
            return False

        tap_name = self.settings_manager.get_sensor_labels()[tap_index]
        
        subject = f"KegLevel Alert: Tap {tap_index + 1}: {tap_name} is Low!"
        
        body = self._format_message_body(tap_index, is_conditional=True, trigger_type="volume")
        
        push_notif_settings = self.settings_manager.get_push_notification_settings()
        smtp_config = {
            'server': push_notif_settings.get('smtp_server'), 'port': push_notif_settings.get('smtp_port'),
            'email': push_notif_settings.get('server_email'), 'password': push_notif_settings.get('server_password')
        }
        
        config_ok = all([smtp_config['server'], smtp_config['port'], smtp_config['email'], smtp_config['password']])
        if not config_ok:
            self._report_config_error("volume", "SMTP/sender details incomplete for Conditional Volume Notification.", False)
            return False

        email_ok, sms_ok = None, None
        if notification_type in ["Email", "Both"]:
            recipient_email = push_notif_settings.get('email_recipient')
            if recipient_email:
                email_ok = self._send_email_or_sms(subject, body, recipient_email, smtp_config, f"Conditional Email for {tap_name}")
            else:
                self._report_config_error("volume", "Email recipient not configured for conditional notification.", False)
                
        if notification_type in ["Text", "Both"]:
            sms_number, carrier_gateway = push_notif_settings.get('sms_number'), push_notif_settings.get('sms_carrier_gateway')
            if sms_number and carrier_gateway:
                sms_ok = self._send_email_or_sms(subject, body, f"{sms_number}{carrier_gateway}", smtp_config, f"Conditional Text for {tap_name}")
            else:
                self._report_config_error("volume", "SMS details not configured for conditional notification.", False)

        if email_ok or sms_ok:
            self.settings_manager.update_conditional_sent_status(tap_index, True)
            print(f"NotificationService: Conditional notification sent successfully for tap {tap_index+1}.")
            return True
        else:
            print(f"NotificationService: Failed to send conditional notification for tap {tap_index+1}.")
            return False

    def check_and_send_temp_notification(self):
        cond_notif_settings = self.settings_manager.get_conditional_notification_settings()
        notification_type = cond_notif_settings.get('notification_type', 'None')

        if notification_type == 'None': return

        low_temp_f = cond_notif_settings.get('low_temp_f')
        high_temp_f = cond_notif_settings.get('high_temp_f')
        temp_sent_timestamps = cond_notif_settings.get('temp_sent_timestamps', [])

        current_temp_f = self.ui_manager.temp_logic.last_known_temp_f

        if current_temp_f is None or low_temp_f is None or high_temp_f is None:
            return

        is_outside_range = current_temp_f < low_temp_f or current_temp_f > high_temp_f

        if is_outside_range:
            cool_down_period_seconds = 2 * 3600 # 2 hours
            last_sent_time = temp_sent_timestamps[0] if temp_sent_timestamps else 0

            if (time.time() - last_sent_time) >= cool_down_period_seconds:
                subject = "KegLevel Alert: Temperature Out Of Range!"
                
                body = self._format_message_body(is_conditional=True, trigger_type="temperature")

                push_notif_settings = self.settings_manager.get_push_notification_settings()
                smtp_config = {
                    'server': push_notif_settings.get('smtp_server'), 'port': push_notif_settings.get('smtp_port'),
                    'email': push_notif_settings.get('server_email'), 'password': push_notif_settings.get('server_password')
                }
                
                config_ok = all([smtp_config['server'], smtp_config['port'], smtp_config['email'], smtp_config['password']])
                if not config_ok:
                    self._report_config_error("temperature", "SMTP/sender details incomplete for Conditional Temp Notification.", False)
                    return

                email_ok, sms_ok = None, None
                if notification_type in ["Email", "Both"]:
                    recipient_email = push_notif_settings.get('email_recipient')
                    if recipient_email:
                        email_ok = self._send_email_or_sms(subject, body, recipient_email, smtp_config, "Conditional Temperature Email")
                    else:
                         self._report_config_error("temperature", "Email recipient not configured for conditional notification.", False)
                
                if notification_type in ["Text", "Both"]:
                    sms_number, carrier_gateway = push_notif_settings.get('sms_number'), push_notif_settings.get('sms_carrier_gateway')
                    if sms_number and carrier_gateway:
                        sms_ok = self._send_email_or_sms(subject, body, f"{sms_number}{carrier_gateway}", smtp_config, "Conditional Temperature Text")
                    else:
                        self._report_config_error("temperature", "SMS details not configured for conditional notification.", False)


                if email_ok or sms_ok:
                    self.settings_manager.update_temp_sent_timestamp()
                    print("NotificationService: Conditional temperature notification sent successfully.")

    # --- NEW: Status Request Logic ---
    
    def _send_status_report(self, recipient_email, sender_email, smtp_config):
        """Generates and sends the detailed status report email."""
        subject = "KegLevel Monitor Status"
        body = self._format_message_body(is_conditional=True, trigger_type="status_request")
        
        return self._send_email_or_sms(
            subject, 
            body, 
            recipient_email, 
            smtp_config, 
            "Status Request Reply"
        )
        
    def _check_for_status_requests(self):
        """Connects to IMAP and checks for the 'STATUS' command email."""
        status_settings = self.settings_manager.get_status_request_settings()
        
        if not status_settings['enable_status_request']:
            # Log only on the first check to reduce console spam
            if self._status_request_running:
                 print("NotificationService: Status Request Listener is disabled.")
            return

        rpi_email = status_settings['rpi_email_address']
        rpi_password = status_settings['rpi_email_password']
        imap_server = status_settings['imap_server']
        imap_port = status_settings['imap_port']
        authorized_sender = status_settings['authorized_sender']
        
        required_config = all([rpi_email, rpi_password, imap_server, imap_port, authorized_sender])
        if not required_config:
            self._report_config_error("status_request", "IMAP/SMTP configuration incomplete for Status Request.", False)
            return

        try:
            # Connect to IMAP server
            mail = imaplib.IMAP4_SSL(imap_server, int(imap_port))
            mail.login(rpi_email, rpi_password)
            mail.select('inbox')

            # Search for: UNSEEN messages, sent FROM the authorized sender, AND containing the STATUS string anywhere (TEXT).
            search_query = f'(UNSEEN FROM "{authorized_sender}" TEXT "{STATUS_REQUEST_SUBJECT}")'
            status, data = mail.search(None, search_query)
            email_ids = data[0].split()

            if email_ids:
                print(f"NotificationService: Found {len(email_ids)} unread STATUS request emails. Replying...")
                
                # Process only the latest email
                latest_email_id = email_ids[-1]
                
                smtp_config = {
                    'server': status_settings['smtp_server'], 
                    'port': status_settings['smtp_port'],
                    'email': rpi_email, 
                    'password': rpi_password
                }

                # Send the reply
                send_ok = self._send_status_report(authorized_sender, rpi_email, smtp_config)
                
                if send_ok:
                    # Mark the email as seen to prevent endless loops.
                    mail.store(latest_email_id, '+FLAGS', '\\Seen')
                    print("NotificationService: STATUS request processed and email marked as read.")
                else:
                    # Do NOT mark as read if reply failed.
                    print("NotificationService: WARNING: Reply failed. STATUS email not marked as read.")

            mail.logout()

        except imaplib.IMAP4.error as e:
            self._report_config_error("status_request", f"IMAP Error: Check IMAP/Port/Password/App Password. Error: {e}", False)
        except Exception as e:
            self._report_config_error("status_request", f"Unexpected Status Request Error: {e}", False)

    def _status_request_listener_loop(self):
        """Dedicated thread loop for checking the status request email every minute."""
        print("NotificationService: Status Request Listener loop started (1 minute interval).")
        while self._status_request_running:
            self._check_for_status_requests()
            # Use event.wait for non-blocking sleep (allows quick shutdown)
            self._scheduler_event.wait(self._status_request_interval_seconds) 
            
    def start_status_request_listener(self):
        """Starts the dedicated listener thread if enabled in settings."""
        if not self._status_request_running:
            status_settings = self.settings_manager.get_status_request_settings()
            if status_settings['enable_status_request']:
                self._status_request_running = True
                self._status_request_listener_thread = threading.Thread(target=self._status_request_listener_loop, daemon=True)
                self._status_request_listener_thread.start()
                print("NotificationService: Status Request Listener activated.")
        
    def stop_status_request_listener(self):
        """Stops the dedicated listener thread."""
        if self._status_request_running:
            print("NotificationService: Stopping Status Request Listener...")
            self._status_request_running = False
            self._scheduler_event.set()
            if self._status_request_listener_thread and self._status_request_listener_thread.is_alive():
                self._status_request_listener_thread.join(timeout=2)
                print("NotificationService: Status Request Listener stopped.")
    
    # --- END NEW: Status Request Logic ---

    # --- MISSING FUNCTION: Initial Notification Delay ---
    def _send_initial_notification_after_delay(self):
        if not self._scheduler_running: return

        print("NotificationService: Initial notification delay started (1 minute)...")
        woke_early = self._scheduler_event.wait(timeout=60)

        if not self._scheduler_running or (woke_early and not self._scheduler_running):
            print("NotificationService: Initial notification cancelled; scheduler stopped during delay.")
            return

        if self._scheduler_running:
            print("NotificationService: Initial notification delay complete. Attempting send...")
            if self.send_push_notification(is_initial_send=True):
                self.last_notification_sent_time = time.time()
                print("NotificationService: Initial push notification attempt processed, last_sent_time updated.")
    # --- END MISSING FUNCTION ---

    def start_scheduler(self):
        if not self._scheduler_running:
            self._scheduler_running = True
            self._scheduler_event.clear()
            self.last_notification_sent_time = time.time()

            initial_send_thread = threading.Thread(target=self._send_initial_notification_after_delay, daemon=True)
            initial_send_thread.start()

            if self._scheduler_thread is None or not self._scheduler_thread.is_alive():
                self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
                self._scheduler_thread.start()
            print("NotificationService: Scheduler started. Initial notification attempt will be after 1 min if configured.")
        else:
            print("NotificationService: Scheduler already running.")
            self.force_reschedule()
            
        # --- NEW: Start Status Request Listener when Scheduler starts ---
        self.start_status_request_listener()
        # --- END NEW ---

    def _scheduler_loop(self):
        print("NotificationService: Scheduler loop started.")
        current_settings = {} 
        notification_type = 'None'
        frequency_str = 'Daily'
        
        while self._scheduler_running:
            current_settings = self.settings_manager.get_push_notification_settings() 
            notification_type = current_settings.get('notification_type', 'None')
            frequency_str = current_settings.get('frequency', 'Daily')
            
            if notification_type == 'None':
                wait_time = 600
            else:
                now = time.time()
                interval_seconds = self._get_interval_seconds(frequency_str)

                if now >= self.last_notification_sent_time + interval_seconds:
                    print(f"NotificationService: Scheduled time to send push notification (Frequency: {frequency_str}).")
                    if self.send_push_notification():
                        self.last_notification_sent_time = now

                time_to_next_scheduled = (self.last_notification_sent_time + interval_seconds) - time.time()
                wait_time = max(10.0, min(time_to_next_scheduled if time_to_next_scheduled > 0 else interval_seconds, 600.0))

            woke_early = self._scheduler_event.wait(timeout=wait_time)
            
            if woke_early:
                if not self._scheduler_running: break
                self._scheduler_event.clear()
                continue 
                
        print("NotificationService: Scheduler loop stopped.")

    def stop_scheduler(self):
        if self._scheduler_running:
            print("NotificationService: Stopping scheduler...")
            self._scheduler_running = False
            self._scheduler_event.set()
            
            # --- NEW: Stop Status Request Listener when Scheduler stops ---
            self.stop_status_request_listener()
            # --- END NEW ---
            
            if self._scheduler_thread and self._scheduler_thread.is_alive():
                self._scheduler_thread.join(timeout=5)
                if self._scheduler_thread.is_alive(): print("NotificationService: Scheduler thread did not stop gracefully.")
            print("NotificationService: Scheduler stopped.")
        else: print("NotificationService: Scheduler not running.")

    def force_reschedule(self):
        self._last_error_time = {
            "push": 0.0,
            "volume": 0.0,
            "temperature": 0.0
        }
        if self._scheduler_running:
            print("NotificationService: Settings changed. Forcing scheduler to re-evaluate timings.")
            self.last_notification_sent_time = time.time()
            self._scheduler_event.set()
            
            # --- FIX: Do NOT restart the listener here. ---
            # The listener's state should be managed ONLY by
            # start_scheduler() and stop_scheduler().
            # ---
            # self.stop_status_request_listener()
            # self.start_status_request_listener()
            # --- END FIX ---
