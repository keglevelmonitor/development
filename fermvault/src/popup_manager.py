"""
fermvault app
popup_manager.py
"""

import tkinter as tk
from tkinter import ttk, messagebox
import math
import os
import sys
from datetime import datetime
import re
import webbrowser
import tkinter.font as tkfont
import tkinter.scrolledtext as scrolledtext
import subprocess
import shutil
import os

# --- Constants for Conversion (Placeholder) ---
MINUTES_TO_SECONDS = 60
HOURS_TO_SECONDS = 3600
# --- End Constants ---

class PopupManager:
    
# List of popups matching the 'Settings & Info' menu
    # --- MODIFICATION: Renamed "API Settings", added "PID & Tuning", added "Support" ---
    POPUP_LIST = [
        "Temperature Setpoints", "PID & Tuning", "Notification Settings", "API & FG Settings", 
        "Brew Sessions", "System Settings", "Wiring Diagram", "Help", "About",
        "Support this App"
    ]
    # --- END MODIFICATION ---
    
    def __init__(self, ui_instance):
        self.ui = ui_instance
        self.root = ui_instance.root
        self.settings_manager = ui_instance.settings_manager
        self.temp_controller = ui_instance.temp_controller
        self.api_manager = ui_instance.api_manager
        self.notification_manager = ui_instance.notification_manager
        
        # Expose the popup list to the UIBase for the menu creation
        self.ui.popup_list = self.POPUP_LIST
        
        # --- NEW: EULA/Support Popup Variables ---
        self.eula_agreement_var = tk.IntVar(value=0) # 0=unset, 1=agree, 2=disagree
        self.show_eula_checkbox_var = tk.BooleanVar()
        self.support_qr_image = None 
        # --- END NEW ---
        
        # --- NEW: Wiring Diagram Variable ---
        self.wiring_diagram_image = None
        # --- END NEW ---
        
        # --- NEW: Relay LED Image Variable ---
        self.relay_led_image = None 
        # -------------------------------------
        
        # --- Internal StringVars for Popups ---
        # Control Mode
        self.amb_hold_var = tk.StringVar()
        self.beer_hold_var = tk.StringVar()
        self.ramp_hold_var = tk.StringVar()
        self.ramp_duration_var = tk.StringVar()
        self.crash_hold_var = tk.StringVar()
        self.control_units_var = tk.StringVar()
        
        # API Settings
        self.api_key_var = tk.StringVar()
        self.api_freq_min_var = tk.StringVar()
        self.fg_check_freq_h_var = tk.StringVar()
        self.fg_tolerance_var = tk.StringVar()
        self.fg_window_size_var = tk.StringVar()
        self.fg_max_outliers_var = tk.StringVar()
        self.api_logging_var = tk.BooleanVar()
        
        # Compressor Protection
        self.dwell_time_min_var = tk.StringVar()
        self.max_run_time_min_var = tk.StringVar()
        self.fail_safe_shutdown_min_var = tk.StringVar()

        # System Settings (Sensor Assignment)
        self.beer_sensor_var = tk.StringVar()
        self.ambient_sensor_var = tk.StringVar()
        self.pid_logging_var = tk.BooleanVar()
        
        # PID & Tuning Variables
        self.pid_kp_var = tk.StringVar()
        self.pid_ki_var = tk.StringVar()
        self.pid_kd_var = tk.StringVar()
        self.pid_idle_zone_var = tk.StringVar()
        self.ambient_deadband_var = tk.StringVar()
        self.beer_pid_envelope_width_var = tk.StringVar()
        self.ramp_pre_ramp_tolerance_var = tk.StringVar()
        self.ramp_thermo_deadband_var = tk.StringVar()
        self.ramp_pid_landing_zone_var = tk.StringVar()
        self.crash_pid_envelope_width_var = tk.StringVar()
        
        # --- Notification Settings ---
        # Push
        self.push_enable_var = tk.BooleanVar()
        self.notif_freq_h_var = tk.StringVar()
        self.push_recipient_var = tk.StringVar()
        
        # Conditional (NEW)
        self.conditional_enable_var = tk.BooleanVar()
        self.cond_amb_min_var = tk.StringVar()
        self.cond_amb_max_var = tk.StringVar()
        self.cond_beer_min_var = tk.StringVar()
        self.cond_beer_max_var = tk.StringVar()
        self.cond_fg_stable_var = tk.BooleanVar()
        self.cond_amb_lost_var = tk.BooleanVar()
        self.cond_beer_lost_var = tk.BooleanVar()
        self.cond_temp_unit_label = tk.StringVar(value="F")
        
        # Status Request / Email Control
        self.req_enable_var = tk.BooleanVar()
        self.req_sender_var = tk.StringVar()
        
        # RPi Email Configuration (SMTP/IMAP)
        self.req_rpi_email_var = tk.StringVar()
        self.req_rpi_password_var = tk.StringVar()
        self.req_imap_server_var = tk.StringVar()
        self.req_imap_port_var = tk.StringVar()
        self.req_smtp_server_var = tk.StringVar()
        self.req_smtp_port_var = tk.StringVar()
        
        # SMS (Legacy/Unused but kept for safety)
        self.sms_number_var = tk.StringVar()
        self.sms_carrier_gateway_var = tk.StringVar()
        
        # Notification Type Legacy (kept for safety)
        self.notif_type_var = tk.StringVar() 
        self.notif_content_type_var = tk.StringVar() 
        self.notif_content_options = ["None", "Status", "Final Gravity", "Both"]

        # --- Brew Session Variables (Max 10 inputs) ---
        self.brew_session_vars = [tk.StringVar() for _ in range(10)]
        
    def _center_popup(self, popup, popup_width, popup_height):
        """
        Calculates and sets the geometry to center a popup over the main window.
        This function forces the root window to update its geometry first
        and then reveals the popup.
        """
        try:
            # Ensure dimensions are integers
            popup_width = int(popup_width)
            popup_height = int(popup_height)
            
            # --- THIS IS THE FIX ---
            # Force tkinter to process all pending events, including geometry
            # This is stronger than update_idletasks() and ensures
            # the winfo_ commands return the correct, final values.
            self.root.update()
            # --- END FIX ---

            # Get main window's position and size (now reliable)
            root_x = self.root.winfo_x()
            root_y = self.root.winfo_y()
            root_width = self.root.winfo_width()
            root_height = self.root.winfo_height()
            
            # Check for default/un-placed window (e.g., < 100px wide)
            # If so, fall back to screen centering
            if root_width < 100 or root_height < 100:
                print("[_center_popup] Main window not placed, falling back to screen center.")
                root_x = 0
                root_y = 0
                root_width = self.root.winfo_screenwidth()
                root_height = self.root.winfo_screenheight()

            # Calculate center position
            center_x = root_x + (root_width // 2) - (popup_width // 2)
            center_y = root_y + (root_height // 2) - (popup_height // 2)
            
            # Set the geometry
            popup.geometry(f"{popup_width}x{popup_height}+{center_x}+{center_y}")
            
            # --- MODIFICATION: Reveal the popup ---
            popup.deiconify()
            # --- END MODIFICATION ---
        
        except Exception as e:
            # Fallback in case anything fails
            print(f"[ERROR] Failed to center popup: {e}. Using fallback geometry.")
            popup.geometry(f"{popup_width}x{popup_height}+100+100")
            # --- MODIFICATION: Reveal the popup ---
            popup.deiconify()
            # --- END MODIFICATION ---
    
    def _to_float_or_error(self, var_str, is_temp=False):
        """
        Safely converts input string to float. If conversion fails or string is empty, 
        it raises ValueError.
        """
        temp_str = var_str.strip()
        if not temp_str:
            raise ValueError(f"Input cannot be empty.")
            
        # The tkinter input boxes should NOT contain " F" or " C" due to the new layout, 
        # so we revert to strict number conversion.
        try:
            value = float(temp_str)
        except ValueError:
            # This will catch cases where the user enters text or leaves the field partially filled.
            raise ValueError(f"'{temp_str}' is not a valid number.")

        if is_temp:
             is_input_f = self.control_units_var.get() == "F"
             if not is_input_f:
                 # Convert C input to F control unit
                 return (value * 9/5) + 32
        return value

    def _to_int_or_error(self, var_str):
        """
        Safely converts input string to integer. If conversion fails, string is empty,
        or contains a significant decimal part, it raises ValueError.
        We allow integers written as '587' or '587.0' but reject '587.5'.
        """
        temp_str = var_str.strip()
        if not temp_str:
            raise ValueError("Input cannot be empty.")
            
        try:
            value = float(temp_str)
            # Check if the float value is numerically an integer (i.e., difference is zero)
            if value != int(value):
                 raise ValueError("Input must be a whole number (no decimals allowed).")
            
            return int(value)
        except ValueError as e:
            # Catch errors from float() or the custom check above
            raise ValueError(f"'{temp_str}' is not a valid whole number: {e}")
            
    def _open_popup_by_name(self, name):
        # --- MODIFICATION: Reset the menu variable (REMOVED) ---
        # self.ui.settings_menu_var.set("Select...")
        # --- END MODIFICATION ---

        if name == "Temperature Setpoints": self._open_control_mode_settings_popup()
        elif name == "PID & Tuning": self._open_pid_tuning_popup() # <-- NEW
        elif name == "Notification Settings": self._open_notification_settings_popup()
        # --- MODIFICATION: Renamed "API Settings" ---
        elif name == "API & FG Settings": self._open_api_settings_popup()
        # --- END MODIFICATION ---
        elif name == "Brew Sessions": self._open_brew_sessions_popup()
        elif name == "System Settings": self._open_system_settings_popup()
        # --- MODIFICATION: Call new function ---
        elif name == "Wiring Diagram": self._open_wiring_diagram_popup()
        # --- END MODIFICATION ---
        elif name == "Help": self._open_help_popup()
        elif name == "About": self._open_about_popup()
        # --- NEW: Handle Support popup ---
        elif name == "Support this App": 
            self._open_support_popup(is_launch=False)
        # --- END NEW ---
        else: self.ui.log_system_message(f"Error: Popup '{name}' not implemented.")
        
    # --- CONTROL MODE SETTINGS ---
    def _open_control_mode_settings_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Temperature Setpoints")
        popup.transient(self.root); popup.grab_set()
        
        c_settings = self.settings_manager.get_all_control_settings()
        
        is_display_f = c_settings['temp_units'] == "F"
        def to_display(temp_f):
            return temp_f if is_display_f else (temp_f - 32) * 5/9

        self.amb_hold_var.set(f"{to_display(c_settings['ambient_hold_f']):.1f}")
        self.beer_hold_var.set(f"{to_display(c_settings['beer_hold_f']):.1f}")
        self.ramp_hold_var.set(f"{to_display(c_settings['ramp_up_hold_f']):.1f}")
        self.ramp_duration_var.set(f"{c_settings['ramp_up_duration_hours']:.1f}")
        self.crash_hold_var.set(f"{to_display(c_settings['fast_crash_hold_f']):.1f}")
        self.control_units_var.set(c_settings['temp_units'])
        self.popup_display_units = c_settings['temp_units']

        form_frame = ttk.Frame(popup, padding="15"); 
        form_frame.pack(fill="both", expand=True)
        
        ROW_PADDING = 8; LABEL_WIDTH = 20; INPUT_WIDTH = 6

        def add_row(parent, label_text, var, unit_var=None, unit_text=None, is_dropdown=False, options=None):
            row = tk.Frame(parent)
            row.pack(fill='x', pady=(ROW_PADDING, 0))
            ttk.Label(row, text=label_text, width=LABEL_WIDTH, anchor='w').pack(side='left')
            
            widget = None
            if is_dropdown:
                widget = ttk.Combobox(row, textvariable=var, values=options, state="readonly", width=INPUT_WIDTH)
            else:
                widget = ttk.Entry(row, textvariable=var, width=INPUT_WIDTH)
            widget.pack(side='left', padx=(5, 5))
            
            if unit_var: ttk.Label(row, textvariable=unit_var).pack(side='left')
            elif unit_text: ttk.Label(row, text=unit_text).pack(side='left')
            return widget

        add_row(form_frame, "Temperature Units:", self.control_units_var, is_dropdown=True, options=["F", "C"])
        self.control_units_var.trace_add("write", self._on_units_changed)
        
        add_row(form_frame, "Ambient Temp:", self.amb_hold_var, unit_var=self.control_units_var)
        add_row(form_frame, "Beer Temp:", self.beer_hold_var, unit_var=self.control_units_var)
        add_row(form_frame, "Ramp Temp:", self.ramp_hold_var, unit_var=self.control_units_var)
        add_row(form_frame, "Ramp Duration:", self.ramp_duration_var, unit_text="hours")
        add_row(form_frame, "Crash Temp:", self.crash_hold_var, unit_var=self.control_units_var)
        
        btns_frame = ttk.Frame(popup, padding="10"); 
        btns_frame.pack(fill="x", side="bottom")
        ttk.Button(btns_frame, text="Save", command=lambda: self._save_control_mode_settings(popup)).pack(side="right", padx=5)
        ttk.Button(btns_frame, text="Cancel", command=popup.destroy).pack(side="right")
        
        # HELP BUTTON (Linked to 'setpoints' section)
        ttk.Button(btns_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("setpoints")).pack(side="right", padx=5)
        
        popup.update_idletasks()
        popup.withdraw()
        self._center_popup(popup, 380, popup.winfo_height())
        
    def _save_control_mode_settings(self, popup):
        try:
            # 1. Retrieve CURRENT (OLD) settings from disk
            old_settings = self.settings_manager.get_all_control_settings()
            
            # All calls to _to_float_or_error are guaranteed to return a float or raise ValueError.
            new_settings = {
                "temp_units": self.control_units_var.get(),
                "ambient_hold_f": self._to_float_or_error(self.amb_hold_var.get(), is_temp=True),
                "beer_hold_f": self._to_float_or_error(self.beer_hold_var.get(), is_temp=True),
                "ramp_up_hold_f": self._to_float_or_error(self.ramp_hold_var.get(), is_temp=True),
                "ramp_up_duration_hours": self._to_float_or_error(self.ramp_duration_var.get(), is_temp=False),
                "fast_crash_hold_f": self._to_float_or_error(self.crash_hold_var.get(), is_temp=True),
            }
            
            # --- Validation Logic (retained from previous fix) ---
            numeric_temps = [v for k, v in new_settings.items() if k != 'temp_units' and 'temp' in k and 'hold' in k]
            if any(v < -100.0 or v > 300.0 for v in numeric_temps):
                 messagebox.showerror("Input Error", "Temperatures seem unrealistic (-100 to 300 F/C).", parent=popup); return
            if new_settings['ramp_up_duration_hours'] <= 0.0 and self.settings_manager.get("control_mode") == "Ramp-Up":
                 messagebox.showerror("Input Error", "Ramp-Up Duration must be positive when Ramp-Up mode is selected.", parent=popup); return
            
            # Save the new settings to disk
            self.settings_manager.save_control_settings(new_settings)
            
            # --- NEW FIX: Generate descriptive log message showing only changes ---
            display_unit = new_settings['temp_units']
            log_parts = []
            
            def log_convert(temp_f):
                # Utility to convert F value to the chosen unit for the log message
                if display_unit == "F":
                    return f"{temp_f:.1f}"
                else:
                    return f"{((temp_f - 32) * 5/9):.1f}"

            # --- MODIFICATION: Use shorter names to match UI ---
            if new_settings["ambient_hold_f"] != old_settings["ambient_hold_f"]:
                 log_parts.append(f"Ambient Temp changed to {log_convert(new_settings['ambient_hold_f'])} {display_unit}.")
                 
            if new_settings["beer_hold_f"] != old_settings["beer_hold_f"]:
                 log_parts.append(f"Beer Temp changed to {log_convert(new_settings['beer_hold_f'])} {display_unit}.")
                 
            if new_settings["ramp_up_hold_f"] != old_settings["ramp_up_hold_f"]:
                 log_parts.append(f"Ramp Temp changed to {log_convert(new_settings['ramp_up_hold_f'])} {display_unit}.")

            if new_settings["ramp_up_duration_hours"] != old_settings["ramp_up_duration_hours"]:
                 log_parts.append(f"Ramp Duration changed to {new_settings['ramp_up_duration_hours']:.1f} hours.")
                 
            if new_settings["fast_crash_hold_f"] != old_settings["fast_crash_hold_f"]:
                 log_parts.append(f"Crash Temp changed to {log_convert(new_settings['fast_crash_hold_f'])} {display_unit}.")
            # --- END MODIFICATION ---
            
            # If the units themselves changed (string comparison)
            if new_settings["temp_units"] != old_settings["temp_units"]:
                 log_parts.append(f"Units changed to {new_settings['temp_units']}.")

            # --- MODIFICATION: Use new title in log message ---
            if log_parts:
                message = "Temperature Setpoints saved. " + " ".join(log_parts)
            else:
                message = "Temperature Setpoints saved. (No changes detected.)"
            # --- END MODIFICATION ---

            self.ui.log_system_message(message)
            # ------------------------------------------------------------------
            
            # Always trigger UI refresh after saving setpoints
            if hasattr(self, 'refresh_setpoint_display'):
                self.ui.refresh_setpoint_display() 
            
            popup.destroy()
            self.root.update() # <-- FIX: Force UI loop to run
            
        except ValueError as e:
            # This block now correctly catches all invalid numeric input errors
            messagebox.showerror("Input Error", f"Please enter valid numbers for all fields. ({e})", parent=popup)
        except Exception as e:
             messagebox.showerror("Error", f"An unexpected error occurred: {e}", parent=popup)
             
    def _on_units_changed(self, *args):
        """Called when the F/C combobox is changed in the setpoints popup."""
        try:
            new_unit = self.control_units_var.get()
            # popup_display_units was set when the popup was opened
            old_unit = self.popup_display_units
            
            if new_unit == old_unit:
                return # No change

            vars_to_convert = [
                self.amb_hold_var,
                self.beer_hold_var,
                self.ramp_hold_var,
                self.crash_hold_var
            ]

            for var in vars_to_convert:
                try:
                    current_val = float(var.get())
                    if new_unit == 'F':
                        # Convert C to F
                        new_val = (current_val * 9/5) + 32
                    else:
                        # Convert F to C
                        new_val = (current_val - 32) * 5/9
                    
                    var.set(f"{new_val:.1f}")
                except ValueError:
                    # Ignore if the field has invalid text (e.g., "--" or "abc")
                    pass
            
            # Update the state for the next conversion
            self.popup_display_units = new_unit
            
        except Exception as e:
            print(f"Error converting units: {e}")

    # --- NOTIFICATION SETTINGS (Push & Request) ---
    def _open_notification_settings_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Notification Settings")
        popup.transient(self.root)
        popup.grab_set()
        
        push_settings = self.settings_manager.get_all_smtp_settings()
        req_settings = self.settings_manager.get_all_status_request_settings()
        notif_settings = self.settings_manager.settings.get("notification_settings", {})
        
        # 1. Push Vars
        freq_h = self.settings_manager.get("frequency_hours", 24)
        if freq_h == 0 or freq_h == "None":
            self.push_enable_var.set(False)
            self.notif_freq_h_var.set("Every 24 hours")
        else:
            self.push_enable_var.set(True)
            self.notif_freq_h_var.set(f"Every {freq_h} hours")
        
        self.push_recipient_var.set(push_settings.get("email_recipient", ""))
        
        # 2. Conditional Vars
        self.conditional_enable_var.set(notif_settings.get("conditional_enabled", False))
        self.cond_fg_stable_var.set(notif_settings.get("conditional_fg_stable", False))
        self.cond_amb_lost_var.set(notif_settings.get("conditional_amb_sensor_lost", False))
        self.cond_beer_lost_var.set(notif_settings.get("conditional_beer_sensor_lost", False))
        
        control_settings = self.settings_manager.get_all_control_settings()
        units = control_settings.get('temp_units', 'F')
        self.cond_temp_unit_label.set(units)
        
        def to_display(temp_f):
            if temp_f is None: return ""
            return f"{temp_f:.1f}" if units == "F" else f"{((temp_f - 32) * 5/9):.1f}"

        self.cond_amb_min_var.set(to_display(notif_settings.get("conditional_amb_min", 32.0)))
        self.cond_amb_max_var.set(to_display(notif_settings.get("conditional_amb_max", 85.0)))
        self.cond_beer_min_var.set(to_display(notif_settings.get("conditional_beer_min", 32.0)))
        self.cond_beer_max_var.set(to_display(notif_settings.get("conditional_beer_max", 75.0)))

        # 3. Status/Email Control Vars
        self.req_enable_var.set(req_settings.get("enable_status_request", False))
        self.req_sender_var.set(req_settings.get("authorized_sender", ""))
        
        # 4. RPi Config Vars
        self.req_rpi_email_var.set(push_settings.get("server_email", ""))
        self.req_rpi_password_var.set(push_settings.get("server_password", ""))
        self.req_imap_server_var.set(req_settings.get("imap_server", ""))
        self.req_imap_port_var.set(str(req_settings.get("imap_port", 993)))
        self.req_smtp_server_var.set(push_settings.get("smtp_server", ""))
        self.req_smtp_port_var.set(str(push_settings.get("smtp_port", 587)))

        notebook = ttk.Notebook(popup)
        notebook.pack(expand=True, fill='both', padx=5, pady=5)

        tab1 = ttk.Frame(notebook, padding=5); notebook.add(tab1, text='Alerts & Controls')
        tab2 = ttk.Frame(notebook, padding=5); notebook.add(tab2, text='RPi Email Configuration')
        
        outbound_frame = ttk.LabelFrame(tab1, text="Outbound Alerts (Push & Conditional)", padding=5)
        outbound_frame.pack(fill='x', pady=(0, 5))
        
        recip_frame = ttk.Frame(outbound_frame); recip_frame.pack(fill='x', pady=2)
        ttk.Label(recip_frame, text="Recipient Email:", width=20, anchor='w').pack(side='left')
        self.push_recipient_entry = ttk.Entry(recip_frame, textvariable=self.push_recipient_var, width=35)
        self.push_recipient_entry.pack(side='left', fill='x', expand=True)
        
        ttk.Label(outbound_frame, text="(Required if either Push or Conditional notifications are enabled)", font=('TkDefaultFont', 8, 'italic')).pack(anchor='w', padx=20, pady=(0, 5))
        
        self.push_enable_check = ttk.Checkbutton(outbound_frame, text="Enable Push Notifications", variable=self.push_enable_var)
        self.push_enable_check.pack(anchor='w', pady=(0, 2))
        
        ttk.Label(outbound_frame, text="E.g. Daily status reports sent at a fixed interval.", font=('TkDefaultFont', 8, 'italic'), wraplength=500).pack(anchor='w', padx=25, pady=(0, 2))

        freq_frame = ttk.Frame(outbound_frame); freq_frame.pack(fill='x', padx=25, pady=(0, 5))
        ttk.Label(freq_frame, text="Report Frequency:", width=20, anchor='w').pack(side='left')
        freq_options = ["Every 1 hour", "Every 2 hours", "Every 4 hours", "Every 8 hours", "Every 12 hours", "Every 24 hours"]
        self.notif_freq_dropdown = ttk.Combobox(freq_frame, textvariable=self.notif_freq_h_var, values=freq_options, state="readonly", width=20)
        self.notif_freq_dropdown.pack(side='left')
        
        self.cond_enable_check = ttk.Checkbutton(outbound_frame, text="Enable Conditional Notifications", variable=self.conditional_enable_var)
        self.cond_enable_check.pack(anchor='w', pady=(5, 2))
        
        cond_sub_frame = ttk.Frame(outbound_frame); cond_sub_frame.pack(fill='x', padx=25)
        self.cond_temp_entries = [] 
        def add_temp_row(parent, label, var_min, var_max):
            row = ttk.Frame(parent); row.pack(fill='x', pady=1)
            ttk.Label(row, text=label, width=30, anchor='w').pack(side='left')
            self.cond_temp_entries.append(ttk.Entry(row, textvariable=var_min, width=6))
            self.cond_temp_entries[-1].pack(side='left', padx=2)
            ttk.Label(row, text="-").pack(side='left')
            self.cond_temp_entries.append(ttk.Entry(row, textvariable=var_max, width=6))
            self.cond_temp_entries[-1].pack(side='left', padx=2)
            ttk.Label(row, textvariable=self.cond_temp_unit_label).pack(side='left')
            
        add_temp_row(cond_sub_frame, "Ambient temp outside the range:", self.cond_amb_min_var, self.cond_amb_max_var)
        add_temp_row(cond_sub_frame, "Beer temp outside the range:", self.cond_beer_min_var, self.cond_beer_max_var)
        
        self.cond_checks = []
        self.cond_checks.append(ttk.Checkbutton(cond_sub_frame, text="Final Gravity (FG) Stable", variable=self.cond_fg_stable_var))
        self.cond_checks[-1].pack(anchor='w', pady=1)
        self.cond_checks.append(ttk.Checkbutton(cond_sub_frame, text="Ambient temp sensor lost", variable=self.cond_amb_lost_var))
        self.cond_checks[-1].pack(anchor='w', pady=1)
        self.cond_checks.append(ttk.Checkbutton(cond_sub_frame, text="Beer temp sensor lost", variable=self.cond_beer_lost_var))
        self.cond_checks[-1].pack(anchor='w', pady=1)
        
        inbound_frame = ttk.LabelFrame(tab1, text="Inbound Controls (Status & Commands)", padding=5)
        inbound_frame.pack(fill='x', pady=5)
        
        self.req_enable_check = ttk.Checkbutton(inbound_frame, text="Enable Email Control (Status & Commands)", variable=self.req_enable_var)
        self.req_enable_check.pack(anchor='w', pady=(0, 2))
        
        # --- RESTORED ORIGINAL WARNING TEXT ---
        warning_text_tab1 = (
            "WARNING: When enabled, the app checks the 'RPi Email Configuration' account for new messages "
            "from the Authorized Sender. If new messages exist, the app marks them as 'read', and "
            "processes them for 'Status' or 'Command' actions. Only enable this feature if you are using "
            "a dedicated email account set up exclusively for this app, and enter that email account's "
            "configuration settings on the 'RPi Email Configuration' tab."
        )
        ttk.Label(inbound_frame, text=warning_text_tab1, font=('TkDefaultFont', 8, 'italic'), wraplength=600, justify='left').pack(anchor='w', padx=20, pady=(0, 5))
        
        auth_frame = ttk.Frame(inbound_frame); auth_frame.pack(fill='x', padx=20, pady=(0, 5))
        ttk.Label(auth_frame, text="Authorized Sender:", width=20, anchor='w').pack(side='left')
        self.req_sender_entry = ttk.Entry(auth_frame, textvariable=self.req_sender_var, width=35)
        self.req_sender_entry.pack(side='left', fill='x', expand=True)
        
        # --- REPEAT WARNING ON TAB 2 (As in original) ---
        warning_text_tab2 = (
            "WARNING: When Email Control is enabled, the app checks the 'RPi Email Configuration' account for new messages "
            "from the Authorized Sender. If new messages exist, the app marks them as 'read', and "
            "processes them for 'Status' or 'Command' actions. Only enable this feature if you are using "
            "a dedicated email account set up exclusively for this app, and enter that email account's "
            "configuration settings on the 'RPi Email Configuration' tab."
        )
        ttk.Label(tab2, text=warning_text_tab2, font=('TkDefaultFont', 8, 'italic'), wraplength=600, justify='left').pack(anchor='w', pady=(0, 10))

        def add_cfg_row(parent, label, var, show_char=None):
            row = ttk.Frame(parent); row.pack(fill='x', pady=4)
            ttk.Label(row, text=label, width=25, anchor='w').pack(side='left')
            entry = ttk.Entry(row, textvariable=var, width=30, show=show_char)
            entry.pack(side='left', fill='x', expand=True)
            return entry

        self.rpi_email_entry = add_cfg_row(tab2, "RPi email address:", self.req_rpi_email_var)
        self.rpi_password_entry = add_cfg_row(tab2, "RPi email password (2FA pw):", self.req_rpi_password_var, show_char="*")
        ttk.Separator(tab2, orient='horizontal').pack(fill='x', pady=10)
        self.smtp_server_entry = add_cfg_row(tab2, "SMTP (outgoing) server:", self.req_smtp_server_var)
        self.smtp_port_entry = add_cfg_row(tab2, "SMTP (outgoing) port:", self.req_smtp_port_var)
        ttk.Separator(tab2, orient='horizontal').pack(fill='x', pady=10)
        self.imap_server_entry = add_cfg_row(tab2, "IMAP (incoming) server:", self.req_imap_server_var)
        self.imap_port_entry = add_cfg_row(tab2, "IMAP (incoming) port:", self.req_imap_port_var)
        
        btns_frame = ttk.Frame(popup, padding="10"); btns_frame.pack(fill="x", side="bottom")
        ttk.Button(btns_frame, text="Save", command=lambda: self._save_notification_settings(popup)).pack(side="right", padx=5)
        ttk.Button(btns_frame, text="Cancel", command=popup.destroy).pack(side="right")
        
        # HELP BUTTON
        ttk.Button(btns_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("notifications")).pack(side="right", padx=5)
        
        self.push_enable_var.trace_add("write", self._toggle_email_fields_state)
        self.conditional_enable_var.trace_add("write", self._toggle_email_fields_state)
        self.req_enable_var.trace_add("write", self._toggle_email_fields_state)
        self._toggle_email_fields_state()
        
        popup.update_idletasks(); popup.withdraw()
        self._center_popup(popup, 650, 550)
        
    def _save_notification_settings(self, popup):
        try:
            # 1. Input Parsing and Validation (Ports)
            push_enabled = self.push_enable_var.get()
            cond_enabled = self.conditional_enable_var.get()
            req_enabled = self.req_enable_var.get()
            
            push_port = 0
            imap_port = 0
            
            # SMTP Port needed if ANY feature is enabled
            if push_enabled or cond_enabled or req_enabled:
                push_port = self._to_int_or_error(self.req_smtp_port_var.get())
                if push_port <= 0 or push_port > 65535:
                     messagebox.showerror("Input Error", "SMTP Port must be 1-65535.", parent=popup); return
            
            # IMAP Port needed only if Request is enabled
            if req_enabled:
                imap_port = self._to_int_or_error(self.req_imap_port_var.get())
                if imap_port <= 0 or imap_port > 65535:
                     messagebox.showerror("Input Error", "IMAP Port must be 1-65535.", parent=popup); return

            # 2. Push Logic
            notif_freq_h = 0
            freq_str = ""
            if push_enabled:
                freq_str = self.notif_freq_h_var.get()
                # Split string "Every 4 hours" -> "4"
                notif_freq_h = self._to_int_or_error(freq_str.split()[1]) 

            # 3. Conditional Logic & Unit Conversion
            # Settings are stored in Fahrenheit. UI displays user preference.
            units = self.cond_temp_unit_label.get() # Get display units "F" or "C"
            
            def from_display(val_str):
                try:
                    val = float(val_str)
                    if units == "F": return val
                    else: return (val * 9/5) + 32 # Convert C to F
                except ValueError:
                    return 0.0 # Default fallback

            # --- CAPTURE OLD STATE FOR LOGGING ---
            # We need these comparisons to generate specific log messages
            old_freq = int(self.settings_manager.get("frequency_hours", 24))
            
            old_notif_settings = self.settings_manager.settings.get('notification_settings', {})
            old_cond_enabled = old_notif_settings.get("conditional_enabled", False)
            
            old_req_settings = self.settings_manager.get_all_status_request_settings()
            old_req_enabled = old_req_settings.get("enable_status_request", False)

            # 4. Save Settings
            
            # A. Push Frequency
            self.settings_manager.set("frequency_hours", notif_freq_h)
            
            # B. Notification Settings (New Conditional Fields)
            notif_settings = self.settings_manager.settings.get('notification_settings', {})
            notif_settings.update({
                "conditional_enabled": cond_enabled,
                "conditional_amb_min": from_display(self.cond_amb_min_var.get()),
                "conditional_amb_max": from_display(self.cond_amb_max_var.get()),
                "conditional_beer_min": from_display(self.cond_beer_min_var.get()),
                "conditional_beer_max": from_display(self.cond_beer_max_var.get()),
                "conditional_fg_stable": self.cond_fg_stable_var.get(),
                "conditional_amb_sensor_lost": self.cond_amb_lost_var.get(),
                "conditional_beer_sensor_lost": self.cond_beer_lost_var.get()
            })
            self.settings_manager.settings['notification_settings'] = notif_settings
            
            # C. SMTP Settings (Shared)
            new_smtp_settings = {
                "server_email": self.req_rpi_email_var.get().strip(),
                "server_password": self.req_rpi_password_var.get(),
                "email_recipient": self.push_recipient_var.get().strip(),
                "smtp_server": self.req_smtp_server_var.get().strip(),
                "smtp_port": push_port if (push_enabled or cond_enabled or req_enabled) else 587,
            }
            self.settings_manager.settings['smtp_settings'].update(new_smtp_settings) 

            # D. Status Request Settings
            new_req_settings = {
                "enable_status_request": req_enabled,
                "authorized_sender": self.req_sender_var.get().strip(),
                "rpi_email_address": self.req_rpi_email_var.get().strip(),
                "rpi_email_password": self.req_rpi_password_var.get(),
                "imap_server": self.req_imap_server_var.get().strip(),
                "imap_port": imap_port if req_enabled else 993,
            }
            self.settings_manager.save_status_request_settings(new_req_settings)
            
            # Save to disk
            self.settings_manager._save_all_settings()
            
            # 5. Logging
            self.ui.log_system_message("Notification settings saved.")

            # Log Push Status Changes
            if push_enabled and old_freq == 0:
                self.ui.log_system_message(f"Push notifications enabled (Frequency: {freq_str}).")
            elif not push_enabled and old_freq != 0:
                self.ui.log_system_message("Push notifications disabled.")
            elif push_enabled and notif_freq_h != old_freq:
                 self.ui.log_system_message(f"Push Frequency changed to {freq_str}.")
            
            # Log Conditional Status Changes (NEW)
            if cond_enabled and not old_cond_enabled:
                self.ui.log_system_message("Conditional notifications enabled.")
            elif not cond_enabled and old_cond_enabled:
                self.ui.log_system_message("Conditional notifications disabled.")

            # Log Email Control Status Changes
            if req_enabled and not old_req_enabled:
                self.ui.log_system_message("Email Control (Status & Commands) enabled.")
            elif not req_enabled and old_req_enabled:
                self.ui.log_system_message("Email Control (Status & Commands) disabled.")

            # Reschedule services
            self.notification_manager.force_reschedule(old_freq, notif_freq_h)
            
            popup.destroy()
            self.root.update()
            
        except ValueError as e:
            messagebox.showerror("Input Error", f"Numeric field error: {e}", parent=popup)
            
    def _toggle_email_fields_state(self, *args):
        """
        Enables or disables all fields based on the state of the three master checkboxes.
        """
        try:
            push_enabled = self.push_enable_var.get()
            cond_enabled = self.conditional_enable_var.get()
            req_enabled = self.req_enable_var.get()

            # 1. Outbound Alerts Section (Shared Recipient)
            # Enabled if EITHER push or conditional is ON
            outbound_active = push_enabled or cond_enabled
            outbound_state = 'normal' if outbound_active else 'disabled'
            
            if hasattr(self, 'push_recipient_entry'):
                self.push_recipient_entry.config(state=outbound_state)

            # 2. Push Specific
            push_state = 'normal' if push_enabled else 'disabled'
            if hasattr(self, 'notif_freq_dropdown'):
                self.notif_freq_dropdown.config(state=push_state)
                
            # 3. Conditional Specific
            cond_state = 'normal' if cond_enabled else 'disabled'
            if hasattr(self, 'cond_temp_entries'):
                for entry in self.cond_temp_entries:
                    entry.config(state=cond_state)
            if hasattr(self, 'cond_checks'):
                for chk in self.cond_checks:
                    chk.config(state=cond_state)

            # 4. Inbound Control Section
            req_state = 'normal' if req_enabled else 'disabled'
            if hasattr(self, 'req_sender_entry'):
                self.req_sender_entry.config(state=req_state)

            # 5. RPi Config Tab (Dependencies)
            
            # SMTP/Creds needed if ANY feature is ON
            smtp_needed = push_enabled or cond_enabled or req_enabled
            smtp_state = 'normal' if smtp_needed else 'disabled'
            
            if hasattr(self, 'rpi_email_entry'): self.rpi_email_entry.config(state=smtp_state)
            if hasattr(self, 'rpi_password_entry'): self.rpi_password_entry.config(state=smtp_state)
            if hasattr(self, 'smtp_server_entry'): self.smtp_server_entry.config(state=smtp_state)
            if hasattr(self, 'smtp_port_entry'): self.smtp_port_entry.config(state=smtp_state)
            
            # IMAP needed ONLY if Request is ON
            imap_state = 'normal' if req_enabled else 'disabled'
            
            if hasattr(self, 'imap_server_entry'): self.imap_server_entry.config(state=imap_state)
            if hasattr(self, 'imap_port_entry'): self.imap_port_entry.config(state=imap_state)

        except Exception as e:
            print(f"UI Info: State toggle failed (widget not ready?): {e}")

    # --- API SETTINGS ---
    def _open_api_settings_popup(self):
        popup = tk.Toplevel(self.root); popup.title("API & FG Settings"); popup.transient(self.root); popup.grab_set()
        
        api_settings = self.settings_manager.get_all_api_settings()
        self.api_key_var.set(api_settings['api_key'])
        self.api_freq_min_var.set(str(int(api_settings['api_call_frequency_s'] / 60)))
        self.api_logging_var.set(api_settings.get("api_logging_enabled", False))
        self.fg_check_freq_h_var.set(str(api_settings['fg_check_frequency_h']))
        self.fg_tolerance_var.set(str(api_settings['tolerance']))
        self.fg_window_size_var.set(str(api_settings['window_size']))
        self.fg_max_outliers_var.set(str(api_settings['max_outliers']))
        
        form_frame = ttk.Frame(popup, padding="15"); form_frame.pack(fill="both", expand=True)
        
        def add_api_row(parent, label, var, unit=None, notes=None, is_key=False):
            row_frame = ttk.Frame(parent); row_frame.pack(fill="x", pady=5)
            ttk.Label(row_frame, text=label, width=25, anchor='w').pack(side='left')
            entry = ttk.Entry(row_frame, textvariable=var, width=(60 if is_key else 15))
            entry.pack(side='left', padx=(5, 5), fill=('x' if is_key else 'none'), expand=is_key)
            if unit: ttk.Label(row_frame, text=unit).pack(side='left')
            if notes: ttk.Label(parent, text=notes, font=('TkDefaultFont', 8, 'italic'), wraplength=400).pack(anchor='w', padx=(5, 5)) 
        
        add_api_row(form_frame, "API Key:", self.api_key_var, is_key=True)
        add_api_row(form_frame, "API Call Frequency:", self.api_freq_min_var, unit="minutes", notes="Data refresh rate for OG/SG/Temp.")
        ttk.Checkbutton(form_frame, text="Enable API call logging to System Messages", variable=self.api_logging_var).pack(anchor='w', padx=5, pady=(5, 0))
        ttk.Separator(form_frame, orient='horizontal').pack(fill='x', pady=10)
        ttk.Label(form_frame, text="Final Gravity Calculation Parameters", font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 5))
        add_api_row(form_frame, "FG Check Frequency:", self.fg_check_freq_h_var, unit="hours", notes="How often the scheduler runs the FG stability analysis.")
        add_api_row(form_frame, "SG Range Tolerance:", self.fg_tolerance_var, notes="Max allowed change in SG (e.g., 0.0005).")
        add_api_row(form_frame, "SG Records Window:", self.fg_window_size_var, notes="Number of consecutive readings to check (e.g., 450).")
        add_api_row(form_frame, "Max SG Outliers:", self.fg_max_outliers_var, notes="Maximum readings outside tolerance allowed in window.")
        
        btns_frame = ttk.Frame(popup, padding="10"); btns_frame.pack(fill="x", side="bottom")
        
        # HELP BUTTON (Linked to 'api' section)
        ttk.Button(btns_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("api")).pack(side="left", padx=5)
        
        ttk.Button(btns_frame, text="Save", command=lambda: self._save_api_settings(popup)).pack(side="right", padx=5)
        ttk.Button(btns_frame, text="Cancel", command=popup.destroy).pack(side="right")
        
        popup.update_idletasks(); popup.withdraw()
        self._center_popup(popup, 600, popup.winfo_height())
        
    def _save_api_settings(self, popup):
        try:
            # 1. Validation and New Settings Collection
            # Note: _to_float_or_error is suitable for simple float/int validation when is_temp=False
            
            new_api_key = self.api_key_var.get().strip()
            new_api_freq_s = int(self._to_float_or_error(self.api_freq_min_var.get()) * 60)
            
            # --- NEW: Get API logging state ---
            new_api_logging_enabled = self.api_logging_var.get()
            # --- END NEW ---
            
            new_fg_freq_h = self._to_int_or_error(self.fg_check_freq_h_var.get())
            new_tolerance = self._to_float_or_error(self.fg_tolerance_var.get())
            new_window_size = self._to_int_or_error(self.fg_window_size_var.get())
            new_max_outliers = self._to_int_or_error(self.fg_max_outliers_var.get())

            if new_api_freq_s <= 0 or new_fg_freq_h <= 0:
                 messagebox.showerror("Input Error", "Frequencies must be positive.", parent=popup); return
            if new_window_size <= 0:
                 messagebox.showerror("Input Error", "Window Size must be positive.", parent=popup); return

            new_settings = {
                "api_key": new_api_key,
                "api_call_frequency_s": new_api_freq_s,
                "api_logging_enabled": new_api_logging_enabled, # <-- NEW
                "fg_check_frequency_h": new_fg_freq_h,
                "tolerance": new_tolerance,
                "window_size": new_window_size,
                "max_outliers": new_max_outliers,
            }

            # 2. Retrieve Old Settings for Comparison
            old_settings = self.settings_manager.get_all_api_settings()
            
            # 3. Perform Save
            self.settings_manager.save_api_settings(new_settings)

            # 4. Generate Granular Log Message
            log_parts = []
            
            # API Key (Log if key length changes or is initially set)
            if new_api_key != old_settings['api_key'] and new_api_key != "":
                 log_parts.append("API Key updated.")
            elif new_api_key == "" and old_settings['api_key'] != "":
                 log_parts.append("API Key cleared.")

            # API Frequency
            if new_api_freq_s != old_settings['api_call_frequency_s']:
                log_parts.append(f"API Call Freq. set to {new_api_freq_s // 60} min.")

            # --- NEW: Check for API logging change ---
            old_api_logging_enabled = old_settings.get("api_logging_enabled", False)
            if new_api_logging_enabled != old_api_logging_enabled:
                log_parts.append(f"API Call Logging {'enabled' if new_api_logging_enabled else 'disabled'}.")
            # --- END NEW ---

            # FG Check Frequency
            if new_fg_freq_h != old_settings['fg_check_frequency_h']:
                log_parts.append(f"FG Check Freq. set to {new_fg_freq_h} hours.")
                
            # SG Range Tolerance
            if new_tolerance != old_settings['tolerance']:
                log_parts.append(f"Tolerance set to {new_tolerance}.")

            # SG Records Window
            if new_window_size != old_settings['window_size']:
                log_parts.append(f"Window Size set to {new_window_size}.")

            # Max SG Outliers
            if new_max_outliers != old_settings['max_outliers']:
                log_parts.append(f"Max Outliers set to {new_max_outliers}.")

            # Construct the final message
            if log_parts:
                message = "API settings saved. " + " ".join(log_parts)
            else:
                message = "API settings saved. (No changes detected.)"

            self.ui.log_system_message(message)
            
            # --- THIS IS THE FIX ---
            if self.notification_manager:
                self.notification_manager.reset_api_timers()
            # --- END OF THE FIX ---
            
            popup.destroy()
            self.root.update() # <-- FIX: Force UI loop to run
            
        except ValueError as e:
            messagebox.showerror("Input Error", f"Please enter valid positive numbers for all fields. ({e})", parent=popup)

    # --- SYSTEM SETTINGS ---
    def _open_api_settings_popup(self):
        popup = tk.Toplevel(self.root); popup.title("API & FG Settings"); popup.transient(self.root); popup.grab_set()
        
        api_settings = self.settings_manager.get_all_api_settings()
        self.api_key_var.set(api_settings['api_key'])
        self.api_freq_min_var.set(str(int(api_settings['api_call_frequency_s'] / 60)))
        self.api_logging_var.set(api_settings.get("api_logging_enabled", False))
        self.fg_check_freq_h_var.set(str(api_settings['fg_check_frequency_h']))
        self.fg_tolerance_var.set(str(api_settings['tolerance']))
        self.fg_window_size_var.set(str(api_settings['window_size']))
        self.fg_max_outliers_var.set(str(api_settings['max_outliers']))
        
        form_frame = ttk.Frame(popup, padding="15"); form_frame.pack(fill="both", expand=True)
        
        def add_api_row(parent, label, var, unit=None, notes=None, is_key=False):
            row_frame = ttk.Frame(parent); row_frame.pack(fill="x", pady=5)
            ttk.Label(row_frame, text=label, width=25, anchor='w').pack(side='left')
            entry = ttk.Entry(row_frame, textvariable=var, width=(60 if is_key else 15))
            entry.pack(side='left', padx=(5, 5), fill=('x' if is_key else 'none'), expand=is_key)
            if unit: ttk.Label(row_frame, text=unit).pack(side='left')
            if notes: ttk.Label(parent, text=notes, font=('TkDefaultFont', 8, 'italic'), wraplength=400).pack(anchor='w', padx=(5, 5)) 
        
        add_api_row(form_frame, "API Key:", self.api_key_var, is_key=True)
        add_api_row(form_frame, "API Call Frequency:", self.api_freq_min_var, unit="minutes", notes="Data refresh rate for OG/SG/Temp.")
        ttk.Checkbutton(form_frame, text="Enable API call logging to System Messages", variable=self.api_logging_var).pack(anchor='w', padx=5, pady=(5, 0))
        ttk.Separator(form_frame, orient='horizontal').pack(fill='x', pady=10)
        ttk.Label(form_frame, text="Final Gravity Calculation Parameters", font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 5))
        add_api_row(form_frame, "FG Check Frequency:", self.fg_check_freq_h_var, unit="hours", notes="How often the scheduler runs the FG stability analysis.")
        add_api_row(form_frame, "SG Range Tolerance:", self.fg_tolerance_var, notes="Max allowed change in SG (e.g., 0.0005).")
        add_api_row(form_frame, "SG Records Window:", self.fg_window_size_var, notes="Number of consecutive readings to check (e.g., 450).")
        add_api_row(form_frame, "Max SG Outliers:", self.fg_max_outliers_var, notes="Maximum readings outside tolerance allowed in window.")
        
        btns_frame = ttk.Frame(popup, padding="10"); btns_frame.pack(fill="x", side="bottom")
        
        # --- FIX: Updated to use the new centralized help method ---
        ttk.Button(btns_frame, text="Help", command=lambda: self._open_help_popup("api")).pack(side="left", padx=5)
        
        ttk.Button(btns_frame, text="Save", command=lambda: self._save_api_settings(popup)).pack(side="right", padx=5)
        ttk.Button(btns_frame, text="Cancel", command=popup.destroy).pack(side="right")
        
        popup.update_idletasks(); popup.withdraw()
        self._center_popup(popup, 600, popup.winfo_height())
        
    # FIXED
    def _save_system_settings(self, popup):
        try:
            # --- FIX: Get OLD settings *before* saving new ones ---
            old_comp_settings = self.settings_manager.get_all_compressor_protection_settings()
            old_beer_sensor = self.settings_manager.get("ds18b20_beer_sensor", "unassigned")
            old_amb_sensor = self.settings_manager.get("ds18b20_ambient_sensor", "unassigned")

            # 1. Save Compressor Protection (convert minutes to seconds)
            new_dwell_min = int(self._to_float_or_error(self.dwell_time_min_var.get()))
            new_max_run_min = int(self._to_float_or_error(self.max_run_time_min_var.get()))
            new_fail_safe_min = int(self._to_float_or_error(self.fail_safe_shutdown_min_var.get()))
            
            comp_settings = {
                "cooling_dwell_time_s": new_dwell_min * MINUTES_TO_SECONDS,
                "max_cool_runtime_s": new_max_run_min * MINUTES_TO_SECONDS,
                "fail_safe_shutdown_time_s": new_fail_safe_min * MINUTES_TO_SECONDS,
            }
            if any(v <= 0 for v in comp_settings.values()):
                 messagebox.showerror("Input Error", "All protection times must be positive.", parent=popup); return

            self.settings_manager.save_compressor_protection_settings(comp_settings)

            # --- 2. Sensor Assignment Logic ---
            new_beer_sensor = self.beer_sensor_var.get()
            new_amb_sensor = self.ambient_sensor_var.get()
            
            self.settings_manager.set("ds18b20_beer_sensor", new_beer_sensor)
            self.settings_manager.set("ds18b20_ambient_sensor", new_amb_sensor)
            
            # --- 3. Generate "Robust" System Message ---
            log_parts = []

            # Check Compressor settings
            old_dwell_min = int(old_comp_settings['cooling_dwell_time_s'] / MINUTES_TO_SECONDS)
            if new_dwell_min != old_dwell_min:
                log_parts.append(f"Dwell Time changed to {new_dwell_min} min.")

            old_max_run_min = int(old_comp_settings['max_cool_runtime_s'] / MINUTES_TO_SECONDS)
            if new_max_run_min != old_max_run_min:
                log_parts.append(f"Max Run Time changed to {new_max_run_min} min.")
            
            old_fail_safe_min = int(old_comp_settings['fail_safe_shutdown_time_s'] / MINUTES_TO_SECONDS)
            if new_fail_safe_min != old_fail_safe_min:
                log_parts.append(f"Fail-Safe Time changed to {new_fail_safe_min} min.")

            # Check for Beer Sensor change/assignment
            if new_beer_sensor != old_beer_sensor and new_beer_sensor != 'unassigned':
                log_parts.append("Beer sensor assigned.")
            elif new_beer_sensor == 'unassigned' and old_beer_sensor != 'unassigned':
                 log_parts.append("Beer sensor unassigned.")

            # Check for Ambient Sensor change/assignment
            if new_amb_sensor != old_amb_sensor and new_amb_sensor != 'unassigned':
                log_parts.append("Ambient sensor assigned.")
            elif new_amb_sensor == 'unassigned' and old_amb_sensor != 'unassigned':
                 log_parts.append("Ambient sensor unassigned.")
            
            if log_parts:
                message = "System settings saved. " + " ".join(log_parts)
            else:
                message = "System settings saved. (No changes detected.)" 
            
            self.ui.log_system_message(message)
            # ---------------------------------------------------------------------------------
            
            # --- CRITICAL FIX: SAFETY SHUTDOWN ---
            # If we were in Test Mode (Monitoring OFF), we must ensure relays 
            # are turned OFF when the window closes, even if we clicked "Save".
            if self.ui.monitoring_var.get() == "OFF":
                 self.temp_controller.relay_control.turn_off_all_relays()
            # -------------------------------------

            popup.destroy()
            self.root.update() # Force UI loop to run
            
        except ValueError as e:
            messagebox.showerror("Input Error", f"Please enter valid whole numbers for times. ({e})", parent=popup)
            
    def _open_brew_sessions_popup(self):
        popup = tk.Toplevel(self.root); popup.title("Brew Sessions"); popup.transient(self.root); popup.grab_set()
        form_frame = ttk.Frame(popup, padding="15"); form_frame.pack(fill="both", expand=True)
        current_sessions = self.settings_manager.brew_sessions
        
        ttk.Label(form_frame, text="Used when API mode is OFF.", font=('TkDefaultFont', 9, 'italic')).grid(row=0, column=0, sticky='w', pady=(0, 10))

        self.brew_input_widgets = []
        for i in range(10):
            self.brew_session_vars[i].set(current_sessions[i] if i < len(current_sessions) else "")
            entry = ttk.Entry(form_frame, textvariable=self.brew_session_vars[i], width=50)
            entry.grid(row=i+1, column=0, sticky='ew', padx=5, pady=2)
            self.brew_input_widgets.append(entry)

        form_frame.grid_columnconfigure(0, weight=1)
        btns_frame = ttk.Frame(popup, padding="10"); btns_frame.pack(fill="x", side="bottom")
        ttk.Button(btns_frame, text="Save", command=lambda: self._save_brew_sessions(popup)).pack(side="right", padx=5)
        ttk.Button(btns_frame, text="Cancel", command=popup.destroy).pack(side="right")

        # HELP BUTTON (Linked to 'brew_sessions' section)
        ttk.Button(btns_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("brew_sessions")).pack(side="right", padx=5)
        
        popup.update_idletasks(); popup.withdraw()
        self._center_popup(popup, 550, popup.winfo_height())
    
    def _save_brew_sessions(self, popup):
        try:
            # 1. Collect New Titles
            new_sessions = [var.get().strip() for var in self.brew_session_vars]
            
            # 2. Retrieve Old Titles
            old_sessions = self.settings_manager.brew_sessions
            
            # 3. Perform Save
            self.settings_manager.save_brew_sessions(new_sessions)
            
            # 4. Generate Granular Log Message (Logic retained from previous fix)
            log_parts = []
            
            # Pad old list to length 10 for comparison
            padded_old_sessions = old_sessions + [""] * (10 - len(old_sessions))

            for i in range(10):
                old_title = padded_old_sessions[i]
                new_title = new_sessions[i]
                
                # Compare. If an entry title changed (or was cleared/set)
                if old_title != new_title:
                    if new_title:
                        log_parts.append(f"Recipe {i+1} set to '{new_title}'.")
                    else:
                        log_parts.append(f"Recipe {i+1} cleared.")

            # Construct the final message
            if log_parts:
                message = "Brew Sessions settings saved. " + " ".join(log_parts)
            else:
                message = "Brew Sessions settings saved. (No changes detected.)"

            self.ui.log_system_message(message)
            
            # --- FIX: Repopulate the main UI dropdown immediately after saving ---
            if hasattr(self.ui, '_populate_brew_session_dropdown'):
                self.ui._populate_brew_session_dropdown()
            # ---------------------------------------------------------------------
            
            popup.destroy()
            self.root.update() # <-- FIX: Force UI loop to run
            
        except Exception as e:
             messagebox.showerror("Error", f"An unexpected error occurred: {e}", parent=popup)

    # --- STUB POPUPS ---
    
    def _load_wiring_diagram_image(self):
        """Loads the wiring.gif image and stores it."""
        if self.wiring_diagram_image:
            return # Already loaded
            
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            # Path is now relative to the script: <script_dir>/assets/wiring.gif
            image_path = os.path.join(base_dir, "assets", "wiring.gif")
            
            # Use tk.PhotoImage directly, which supports GIF natively
            self.wiring_diagram_image = tk.PhotoImage(file=image_path)
            
        except FileNotFoundError:
            self.ui.log_system_message("Error: wiring.gif image not found.")
            self.wiring_diagram_image = None
        except tk.TclError as e:
            self.ui.log_system_message(f"Error loading wiring.gif (is it a valid GIF?): {e}")
            self.wiring_diagram_image = None
        except Exception as e:
            self.ui.log_system_message(f"Error loading wiring diagram image: {e}")
            self.wiring_diagram_image = None

    def _open_wiring_diagram_popup(self):
        popup = tk.Toplevel(self.root); popup.title("Wiring Diagram"); popup.transient(self.root); popup.grab_set()
        self._load_wiring_diagram_image() 
        main_frame = ttk.Frame(popup, padding="15"); main_frame.pack(fill="both", expand=True)

        image_frame = ttk.Frame(main_frame, width=690, height=520, relief="sunken", borderwidth=1)
        image_frame.pack(fill="both", expand=True); image_frame.pack_propagate(False) 

        if self.wiring_diagram_image:
            canvas = tk.Canvas(image_frame)
            v_scroll = ttk.Scrollbar(image_frame, orient="vertical", command=canvas.yview)
            h_scroll = ttk.Scrollbar(image_frame, orient="horizontal", command=canvas.xview)
            canvas.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)
            canvas.grid(row=0, column=0, sticky="nsew")
            v_scroll.grid(row=0, column=1, sticky="ns")
            h_scroll.grid(row=1, column=0, sticky="ew")
            image_frame.grid_rowconfigure(0, weight=1); image_frame.grid_columnconfigure(0, weight=1)
            image_label = ttk.Label(canvas, image=self.wiring_diagram_image)
            canvas.create_window((0, 0), window=image_label, anchor="nw")
            image_label.bind('<Configure>', lambda e: canvas.config(scrollregion=canvas.bbox("all")))
        else:
            ttk.Label(image_frame, text="[ wiring.gif not found ]", anchor="center").pack(expand=True)

        btns_frame = ttk.Frame(main_frame, padding=(0, 10, 0, 0)); btns_frame.pack(fill="x", side="bottom")
        ttk.Button(btns_frame, text="Close", command=popup.destroy).pack(side="right")
        if self.wiring_diagram_image:
            ttk.Button(btns_frame, text="Open in Image Viewer", command=self._open_native_viewer).pack(side="left")
        
        # HELP BUTTON (Linked to 'wiring' section)
        ttk.Button(btns_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("wiring")).pack(side="right", padx=5)

        popup.update_idletasks(); popup.withdraw()
        self._center_popup(popup, 680, 520)

    def _open_native_viewer(self):
        # --- PATH FIX: Use the *exact same logic* as _load_wiring_diagram_image ---
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            image_path = os.path.join(base_dir, "assets", "wiring.gif")
        except Exception as e:
            # Fallback to relative path
            self.ui.log_system_message(f"Error getting base_dir, falling back: {e}")
            image_path = os.path.join("assets", "wiring.gif")

        # --- Error 1: File not found ---
        if not os.path.exists(image_path):
            self.ui.log_system_message(f"Error: Native viewer could not find {image_path}")
            return

        viewer_cmd = "xdg-open"

        # --- Error 2: Viewer command not found ---
        if not shutil.which(viewer_cmd):
            # Fallback for minimal systems
            for fallback_viewer in ["eog", "gpicview", "lximage-qt"]:
                if shutil.which(fallback_viewer):
                    viewer_cmd = fallback_viewer
                    break
            else:
                # This is the "viewer not found" case
                self.ui.log_system_message("Error: Could not find a suitable image viewer (xdg-open, eog, etc.).")
                return
        
        # --- Error 3: Other OS-level error during launch ---
        try:
            # Open the viewer as a non-blocking, separate process
            subprocess.Popen([viewer_cmd, image_path])
        except Exception as e:
            # This catches errors like "Permission denied"
            self.ui.log_system_message(f"Error opening image viewer: {e}")

    def _create_formatted_help_popup(self, title, help_text):
        """
        [NEW HELPER]
        Creates a new Toplevel window and populates it with formatted
        text parsed from the help_text string.
        """
        popup = tk.Toplevel(self.root)
        popup.title(title)
        # --- MODIFICATION: Removed initial geometry ---
        popup.transient(self.root); popup.grab_set()
        
        try:
            default_font = tkfont.nametofont("TkDefaultFont")
            default_family = default_font.actual("family")
            default_size = default_font.actual("size")
        except:
            default_family = "TkDefaultFont"
            default_size = 10
        
        main_frame = ttk.Frame(popup, padding="10")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(0, weight=1)
        
        scrollbar = ttk.Scrollbar(main_frame, orient='vertical')
        scrollbar.grid(row=0, column=1, sticky='ns')
        
        text_widget = tk.Text(main_frame, wrap='word', yscrollcommand=scrollbar.set, 
                              relief='sunken', borderwidth=1, padx=10, pady=10,
                              font=(default_family, default_size))
        text_widget.grid(row=0, column=0, sticky='nsew')
        scrollbar.config(command=text_widget.yview)

        # --- Define Formatting Tags ---
        text_widget.tag_configure("heading", font=(default_family, default_size + 2, 'bold', 'underline'), spacing1=5, spacing3=10)
        text_widget.tag_configure("bold", font=(default_family, default_size, 'bold'))
        text_widget.tag_configure("bullet", lmargin1=20, lmargin2=20, offset=10)
        text_widget.tag_configure("link", font=(default_family, default_size, 'underline'), foreground="blue")
        
        text_widget.config(state='normal')
        
        link_regex = r'\[(.*?)\]\((.*?)\)'
        bold_regex = r'(\*\*.*?\*\*)'
        link_count = 0
        
        # --- Helper function to parse bold/links within a line ---
        def parse_line_content(line_str, base_tags=()):
            """Parses a line for bold/links and inserts it."""
            parts = re.split(r'(\[.*?\]\(.*?\))', line_str) # Split by links
            
            for part in parts:
                link_match = re.match(link_regex, part)
                
                if link_match:
                    link_text = link_match.group(1)
                    link_url = link_match.group(2)
                    
                    nonlocal link_count
                    tag_name = f"link_{link_count}"
                    link_count += 1
                    
                    all_tags = base_tags + (tag_name,)
                    
                    text_widget.tag_configure(tag_name, font=(default_family, default_size, 'underline'), foreground="blue")
                    text_widget.tag_bind(tag_name, "<Button-1>", lambda e, url=link_url: self._on_link_click(url))
                    text_widget.tag_bind(tag_name, "<Enter>", lambda e: text_widget.config(cursor="hand2"))
                    text_widget.tag_bind(tag_name, "<Leave>", lambda e: text_widget.config(cursor=""))
                    
                    text_widget.insert("end", link_text, all_tags)
                
                else:
                    bold_parts = re.split(bold_regex, part)
                    for bold_part in bold_parts:
                        if bold_part.startswith("**") and bold_part.endswith("**"):
                            all_tags = base_tags + ("bold",)
                            text_widget.insert("end", bold_part[2:-2], all_tags)
                        else:
                            text_widget.insert("end", bold_part, base_tags)
        # --- END Helper ---

        try:
            for line in help_text.strip().splitlines():
                line_stripped = line.strip()
                
                if line_stripped.startswith("##") and line_stripped.endswith("##"):
                    text_widget.insert("end", line_stripped[2:-2].strip() + "\n", "heading")
                
                elif line_stripped.startswith("* "):
                    text_widget.insert("end", "• ", ("bullet",)) 
                    parse_line_content(line_stripped[2:], base_tags=("bullet",))
                    text_widget.insert("end", "\n") 
                
                elif not line_stripped:
                    text_widget.insert("end", "\n")
                    
                else:
                    parse_line_content(line_stripped, base_tags=())
                    text_widget.insert("end", "\n") 
                    
        except Exception as e:
            text_widget.insert("end", f"An error occurred while parsing help text: {e}")
        
        text_widget.config(state='disabled') # Make read-only
        
        btn_frame = ttk.Frame(popup, padding=(10, 0, 10, 10))
        btn_frame.pack(fill="x", side="bottom")
        ttk.Button(btn_frame, text="Close", command=popup.destroy).pack(side="right")
        
        # --- MODIFICATION: Use dynamic centering ---
        popup.update_idletasks()
        popup_width = 720
        popup_height = 550 # Fixed height is fine for this
        self._center_popup(popup, popup_width, popup_height)
        # --- END MODIFICATION ---
        
    def _open_help_popup(self, section_name="main"):
        """
        Loads the help text for a specific section. 
        Defaults to 'main' table of contents.
        """
        help_text = self._get_help_section(section_name)
        
        # Map internal section names to human-readable window titles
        titles = {
            "main": "FermVault - Help",
            "setpoints": "Help: Setpoints",
            "pid": "Help: PID Tuning",
            "notifications": "Help: Notifications",
            "api": "Help: API & FG Settings",
            "system": "Help: System Settings",
            "brew_sessions": "Help: Brew Sessions",
            "wiring": "Help: Wiring Diagram"
        }
        
        title = titles.get(section_name, "FermVault Help")
        self._create_formatted_help_popup(title, help_text)

    def _on_link_click(self, url):
        """
        Handles link clicks in the help window.
        'section:name' stays in-app; others open in browser.
        """
        if url.startswith("section:"):
            section_name = url.split(":", 1)[1]
            
            # Find the top-level help window (active window) and close it
            top = self.root.focus_get().winfo_toplevel()
            if top:
                top.destroy()
                
            # Open the new section
            self.root.after(50, lambda: self._open_help_popup(section_name))
        else:
            try:
                webbrowser.open_new(url)
            except Exception as e:
                print(f"Error opening link: {e}")

    def _get_help_section(self, section_name):
        """
        Loads the consolidated help.txt file and extracts a specific section.
        """
        try:
            # Calculate path relative to this script
            base_dir = os.path.dirname(os.path.abspath(__file__))
            help_file_path = os.path.join(base_dir, "assets", "help.txt")
            
            with open(help_file_path, 'r', encoding='utf-8') as f:
                full_help_text = f.read()
            
            # Regex to find [SECTION: name] ... [SECTION: or EOF
            pattern = re.compile(r'\[SECTION:\s*' + re.escape(section_name) + r'\](.*?)(?=\[SECTION:|\Z)', re.S)
            match = pattern.search(full_help_text)
            
            if match:
                return match.group(1).strip()
            else:
                return f"## ERROR ##\nSection '[SECTION: {section_name}]' not found in help.txt."
                
        except FileNotFoundError:
            return "## ERROR ##\nConsolidated 'assets/help.txt' file not found."
        except Exception as e:
            return f"## ERROR ##\nAn error occurred loading the help file:\n{e}"
                
    def _get_git_commit_hash(self):
        """Gets the short commit hash using git."""
        try:
            # Assumes 'popup_manager.py' is in 'src/' and '.git' is in the parent folder
            src_dir = os.path.dirname(os.path.abspath(__file__))
            project_dir = os.path.dirname(src_dir)
            
            # We need to import subprocess here
            import subprocess
            
            result = subprocess.run(
                ['git', 'rev-parse', '--short', 'HEAD'],
                cwd=project_dir,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            # Return the short 7-character hash
            return result.stdout.strip()
            
        except FileNotFoundError:
            print("Error getting Git commit hash: 'git' command not found.")
            return "N/A (Git not found)"
        except subprocess.CalledProcessError:
            print("Error getting Git commit hash: Not a git repository?")
            return "N/A (Not a repo)"
        except Exception as e:
            print(f"Error getting Git commit hash: {e}")
            return "N/A (Error)"

    def _add_changelog_section(self, parent_frame, popup_window):
        """Creates and populates the changelog scrolled text area."""
        
        changelog_frame = ttk.Frame(parent_frame, padding=(0, 10, 0, 0))
        changelog_frame.pack(expand=True, fill="both")

        ttk.Label(changelog_frame, text="Change Log:", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(0, 5))
        
        # Create the scrolled text widget
        log_text_widget = scrolledtext.ScrolledText(
            changelog_frame, 
            height=10, 
            wrap="word", 
            relief="sunken", 
            borderwidth=1,
            state="disabled" # Start as read-only
        )
        log_text_widget.pack(expand=True, fill="both")
        
        try:
            # --- Path to changelog.txt ---
            # Assumes popup_manager.py is in 'src/' and assets is also in 'src/'
            src_dir = os.path.dirname(os.path.abspath(__file__))
            # Your changelog is in 'src/assets/changelog.txt'
            # But your file structure shows 'changelog.txt' in the root 'fermvault/' directory
            # I will use the root directory, as that is standard.
            
            project_dir = os.path.dirname(src_dir) # This is the 'fermvault/' folder
            changelog_path = os.path.join(project_dir, "changelog.txt")
            
            # --- FIX: Check for changelog in src/assets/ if not in root ---
            if not os.path.exists(changelog_path):
                 # User said: "the text for the change log is in the popup_manager.py/asset/ folder"
                 # This means 'src/assets/changelog.txt'
                 changelog_path = os.path.join(src_dir, "assets", "changelog.txt")
            # --- END FIX ---

            with open(changelog_path, 'r', encoding='utf-8') as f:
                changelog_content = f.read()

            log_text_widget.config(state="normal") # Make writable to insert text
            log_text_widget.insert("1.0", changelog_content)
            log_text_widget.config(state="disabled") # Return to read-only

        except FileNotFoundError:
            log_text_widget.config(state="normal")
            log_text_widget.insert("1.0", "changelog.txt file not found.")
            log_text_widget.config(state="disabled")
        except Exception as e:
            log_text_widget.config(state="normal")
            log_text_widget.insert("1.0", f"Error loading changelog: {e}")
            log_text_widget.config(state="disabled")

    def _open_about_popup(self):
        """
        Displays the 'About' window with changelog and revision info.
        (This function replaces the simple messagebox version)
        """
        popup = tk.Toplevel(self.root)
        popup.title("About Fermentation Vault")
        # popup.geometry("750x520") # We'll let _center_popup handle this
        popup.resizable(False, False); popup.transient(self.root); popup.grab_set()

        frame = ttk.Frame(popup, padding="10"); frame.pack(expand=True, fill="both")

        # --- 1. Title ---
        ttk.Label(frame, text="Fermentation Vault", font=('TkDefaultFont', 14, 'bold')).pack(pady=(0, 10))
        
        # --- 2. Copyright Text (Adapted) ---
        copyright_text = (
            "Fermentation Vault(c) name, texts, UI/UX "
            "(User Interface/User Experience or Graphical User Interface) and program code are copyrighted. "
            "This material and all components of this program are protected by "
            "copyright law. Unauthorized use, duplication, or distribution is "
            "strictly prohibited. This application is provided as-is without warranty."
        )
        ttk.Label(frame, text=copyright_text, wraplength=700, justify=tk.LEFT).pack(anchor='w', pady=(0, 10))

        # --- 3. Version and Revision (Using your git hash method) ---
        
        # Get the "v1.0" part from main.py
        version_display = self.ui.app_version_string if self.ui.app_version_string else 'Fermentation Vault'
        # Remove the base name if it's there
        if "Fermentation Vault" in version_display:
             version_display = version_display.replace("Fermentation Vault", "").strip()
             
        # Get the git hash
        app_revision = self._get_git_commit_hash()
        
        version_text = f"Version: {version_display} (Revision: {app_revision})"
        ttk.Label(frame, text=version_text, font=('TkDefaultFont', 10, 'italic')).pack(anchor='w', pady=(5, 10))

        # --- 4. License Key Section (OMITTED as requested) ---

        # --- 5. Changelog Section ---
        self._add_changelog_section(frame, popup) 
        
        # --- 6. Attribution Link (Placeholder for your assets) ---
        def open_flaticon_link(event):
            try:
                import webbrowser
                # This is a good default attribution link, update if you know the source
                webbrowser.open_new("https://www.flaticon.com")
            except Exception as e:
                messagebox.showerror("Link Error", f"Could not open link: {e}", parent=popup)

        link_label = ttk.Label(
            popup, 
            text="App icons created by Pixel Perfect - Flaticon (Placeholder)", 
            foreground="blue", 
            cursor="hand2", 
            font=('TkDefaultFont', 8, 'italic', 'underline'), 
            wraplength=700, 
            justify=tk.LEFT
        )
        link_label.pack(fill="x", side="bottom", pady=(0, 5), padx=10) 
        link_label.bind("<Button-1>", open_flaticon_link)
        
        # --- 7. Button Frame (with Support Button) ---
        buttons_frame = ttk.Frame(popup, padding=(10, 5)); 
        buttons_frame.pack(fill="x", side="bottom") 
        
        # --- MODIFICATION: Added "Support this App" button ---
        ttk.Button(
            buttons_frame, 
            text="Support this App", 
            command=lambda: (popup.destroy(), self._open_support_popup(is_launch=False))
        ).pack(side="left", pady=5)
        # --- END MODIFICATION ---

        ttk.Button(buttons_frame, text="Close", command=popup.destroy, width=10).pack(side="right", pady=5)
        
        # --- 8. Center Popup ---
        popup.update_idletasks()
        popup_width = 750
        popup_height = 520
        self._center_popup(popup, popup_width, popup_height)
    
# --- NEW: PID & TUNING POPUP ---
    
    def _open_pid_tuning_popup(self):
        # --- 1. Entrance Gate (Restored Original Text) ---
        title = "Expert Settings Warning"
        message = ("WARNING! These settings are for expert users only. "
                   "Improper settings may produce unexpected results and "
                   "potentially dangerous (overheating) conditions.\n\n"
                   "CANCEL now unless you accept full responsibility for "
                   "changes you make to these settings.")
        
        if not messagebox.askokcancel(title, message):
            return # User clicked Cancel

        # --- 2. Create Popup ---
        popup = tk.Toplevel(self.root); popup.title("PID & Tuning"); popup.transient(self.root); popup.grab_set()
        self._load_pid_tuning_vars()
        
        main_frame = ttk.Frame(popup, padding=(15, 15, 15, 0)); main_frame.pack(fill="both", expand=True)
        notebook = ttk.Notebook(main_frame); notebook.pack(fill="both", expand=True, pady=(0, 15))
        
        pid_tab = ttk.Frame(notebook, padding="15"); notebook.add(pid_tab, text='PID Settings')
        tuning_tab = ttk.Frame(notebook, padding="15"); notebook.add(tuning_tab, text='Tuning Parameters')
        
        def add_tuning_row(parent, label, var, unit=None):
            row_frame = ttk.Frame(parent); row_frame.pack(fill="x", pady=4)
            ttk.Label(row_frame, text=label, width=30, anchor='w').pack(side='left')
            ttk.Entry(row_frame, textvariable=var, width=10).pack(side='left', padx=(5, 5))
            if unit: ttk.Label(row_frame, text=unit).pack(side='left')

        add_tuning_row(pid_tab, "Proportional (Kp)", self.pid_kp_var)
        add_tuning_row(pid_tab, "Integral (Ki)", self.pid_ki_var)
        add_tuning_row(pid_tab, "Derivative (Kd)", self.pid_kd_var)
        ttk.Separator(pid_tab, orient='horizontal').pack(fill='x', pady=10)
        ttk.Label(pid_tab, text="Data Logging", font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 5))
        ttk.Checkbutton(pid_tab, text="Log data for PID & Tuning analysis (pid_tuning_log.csv)", variable=self.pid_logging_var).pack(anchor='w', padx=5, pady=5)

        add_tuning_row(tuning_tab, "PID Idle Zone (All Modes)", self.pid_idle_zone_var, unit="F")
        ttk.Separator(tuning_tab, orient='horizontal').pack(fill='x', pady=10)
        add_tuning_row(tuning_tab, "Ambient Mode Deadband", self.ambient_deadband_var, unit="F")
        ttk.Separator(tuning_tab, orient='horizontal').pack(fill='x', pady=10)
        add_tuning_row(tuning_tab, "Standard PID Envelope (Beer/Ramp)", self.beer_pid_envelope_width_var, unit="F")
        ttk.Separator(tuning_tab, orient='horizontal').pack(fill='x', pady=10)
        add_tuning_row(tuning_tab, "Crash Mode Envelope Width", self.crash_pid_envelope_width_var, unit="F")
        ttk.Separator(tuning_tab, orient='horizontal').pack(fill='x', pady=10)
        add_tuning_row(tuning_tab, "Ramp: Pre-Ramp Tolerance", self.ramp_pre_ramp_tolerance_var, unit="F")
        add_tuning_row(tuning_tab, "Ramp: Thermostatic Deadband", self.ramp_thermo_deadband_var, unit="F")
        add_tuning_row(tuning_tab, "Ramp: PID Landing Zone", self.ramp_pid_landing_zone_var, unit="F")

        btns_frame = ttk.Frame(popup, padding="10"); btns_frame.pack(fill="x", side="bottom")
        ttk.Button(btns_frame, text="Save", command=lambda: self._save_pid_tuning_settings(popup)).pack(side="right", padx=5)
        ttk.Button(btns_frame, text="Cancel", command=popup.destroy).pack(side="right")
        
        # HELP BUTTON (Linked to 'pid' section)
        ttk.Button(btns_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("pid")).pack(side="left", padx=5)

        ttk.Button(btns_frame, text="Reset to Defaults", command=self._reset_pid_tuning_to_defaults).pack(side="left")

        popup.update_idletasks(); popup.withdraw()
        self._center_popup(popup, 500, popup.winfo_height())

    def _load_pid_tuning_vars(self):
        """Helper to load all 10 tuning values + 1 checkbox from settings_manager."""
        self.pid_kp_var.set(str(self.settings_manager.get("pid_kp", 2.0)))
        self.pid_ki_var.set(str(self.settings_manager.get("pid_ki", 0.03)))
        self.pid_kd_var.set(str(self.settings_manager.get("pid_kd", 20.0)))
        self.pid_idle_zone_var.set(str(self.settings_manager.get("pid_idle_zone", 0.5)))
        self.ambient_deadband_var.set(str(self.settings_manager.get("ambient_deadband", 1.0)))
        self.beer_pid_envelope_width_var.set(str(self.settings_manager.get("beer_pid_envelope_width", 1.0)))
        self.ramp_pre_ramp_tolerance_var.set(str(self.settings_manager.get("ramp_pre_ramp_tolerance", 0.2)))
        self.ramp_thermo_deadband_var.set(str(self.settings_manager.get("ramp_thermo_deadband", 0.1)))
        self.ramp_pid_landing_zone_var.set(str(self.settings_manager.get("ramp_pid_landing_zone", 0.5)))
        self.crash_pid_envelope_width_var.set(str(self.settings_manager.get("crash_pid_envelope_width", 2.0)))
        
        # --- MODIFICATION: Load PID logging var ---
        self.pid_logging_var.set(self.settings_manager.get("pid_logging_enabled", False))
        # --- END MODIFICATION ---
        
    def _save_pid_tuning_settings(self, popup):
        
        # 1. Get current (old) values for comparison
        old_vals = {
            "pid_kp": str(self.settings_manager.get("pid_kp", 2.0)),
            "pid_ki": str(self.settings_manager.get("pid_ki", 0.03)),
            "pid_kd": str(self.settings_manager.get("pid_kd", 20.0)),
            "pid_idle_zone": str(self.settings_manager.get("pid_idle_zone", 0.5)),
            "ambient_deadband": str(self.settings_manager.get("ambient_deadband", 1.0)),
            "beer_pid_envelope_width": str(self.settings_manager.get("beer_pid_envelope_width", 1.0)),
            "ramp_pre_ramp_tolerance": str(self.settings_manager.get("ramp_pre_ramp_tolerance", 0.2)),
            "ramp_thermo_deadband": str(self.settings_manager.get("ramp_thermo_deadband", 0.1)),
            "ramp_pid_landing_zone": str(self.settings_manager.get("ramp_pid_landing_zone", 0.5)),
            "crash_pid_envelope_width": str(self.settings_manager.get("crash_pid_envelope_width", 2.0))
        }
        old_pid_logging_state = self.settings_manager.get("pid_logging_enabled", False)

        # 2. Get new values from UI
        new_vals = {
            "pid_kp": self.pid_kp_var.get(),
            "pid_ki": self.pid_ki_var.get(),
            "pid_kd": self.pid_kd_var.get(),
            "pid_idle_zone": self.pid_idle_zone_var.get(),
            "ambient_deadband": self.ambient_deadband_var.get(),
            "beer_pid_envelope_width": self.beer_pid_envelope_width_var.get(),
            "ramp_pre_ramp_tolerance": self.ramp_pre_ramp_tolerance_var.get(),
            "ramp_thermo_deadband": self.ramp_thermo_deadband_var.get(),
            "ramp_pid_landing_zone": self.ramp_pid_landing_zone_var.get(),
            "crash_pid_envelope_width": self.crash_pid_envelope_width_var.get()
        }
        new_pid_logging_state = self.pid_logging_var.get()
        
        # 3. Check for changes (NEW LOGIC)
        text_fields_changed = False
        for key in new_vals:
            if new_vals[key] != old_vals[key]:
                text_fields_changed = True
                break
        
        logging_state_changed = (new_pid_logging_state != old_pid_logging_state)

        # 3a. Check if NOTHING changed
        if not text_fields_changed and not logging_state_changed:
            self.ui.log_system_message("PID & Tuning settings saved. (No changes detected.)")
            popup.destroy()
            return

        # 3b. Check if text fields changed (which requires the challenge)
        if text_fields_changed:
            # 4. Exit Gate (askyesnocancel)
            title = "Confirm Expert Settings"
            message = ("You have made changes to the PID & Tuning settings.\n\n"
                       "- Yes:   Save all changes and close.\n"
                       "- No:    Exit without saving.\n"
                       "- Cancel: Return to the settings window.")
            
            choice = messagebox.askyesnocancel(title, message, parent=popup)
            
            if choice is None: # Cancel
                return # Return to settings
            elif choice is False: # No
                popup.destroy() # Exit without saving
                return
            # If choice is True (Yes), we fall through to Step 5.

        # 5. User clicked YES, OR only the checkbox changed. Validate and Save.
        try:
            log_parts = []
            
            # A. Validate and Save Text Fields (if they changed)
            if text_fields_changed:
                validated_settings = {}
                try:
                    # First, validate all
                    for key, str_val in new_vals.items():
                        val = self._to_float_or_error(str_val)
                        validated_settings[key] = val
                        
                        # Log changes
                        if str(val) != old_vals[key]:
                            log_parts.append(f"{key} set to {val}.")
                    
                    # Second, save all (if validation passed)
                    for key, val in validated_settings.items():
                        self.settings_manager.set(key, val)
                    
                    # Third, update PID controller
                    self.temp_controller.pid.Kp = validated_settings['pid_kp']
                    self.temp_controller.pid.Ki = validated_settings['pid_ki']
                    self.temp_controller.pid.Kd = validated_settings['pid_kd']
                    print("[TempController] PID values updated by user.")
                
                except ValueError as e:
                    # Validation failed, show error and stop
                    messagebox.showerror("Input Error", f"All values must be valid numbers. ({e})", parent=popup)
                    return # Stop the save process
            
            # B. Save Logging State (if it changed)
            if logging_state_changed:
                self.settings_manager.set("pid_logging_enabled", new_pid_logging_state)
                log_parts.append(f"PID Logging {'enabled' if new_pid_logging_state else 'disabled'}.")
                
            # C. Final Log Message
            if log_parts:
                message = "PID & Tuning settings saved. " + " ".join(log_parts)
            else:
                # This should only be hit if the "no changes" check failed, which is rare.
                message = "PID & Tuning settings saved. (No changes detected.)"
            
            self.ui.log_system_message(message)
            popup.destroy()

        except Exception as e:
            # Catch any other unexpected errors
            messagebox.showerror("Error", f"An unexpected error occurred: {e}", parent=popup)

    def _reset_pid_tuning_to_defaults(self):
        """Asks for confirmation, then resets the StringVars in the popup to the hard-coded defaults."""
        
        # --- NEW: Add confirmation dialog ---
        title = "Confirm Reset to Defaults"
        message = "Resets PID settings & tuning parameters to defaults."
        
        # Use askokcancel, consistent with the popup's entry warning
        if not messagebox.askokcancel(title, message):
            return # User clicked Cancel
        # --- END NEW ---
        
        self.pid_kp_var.set("2.0")
        self.pid_ki_var.set("0.03")
        self.pid_kd_var.set("20.0")
        self.pid_idle_zone_var.set("0.5")
        self.ambient_deadband_var.set("1.0")
        self.beer_pid_envelope_width_var.set("1.0")
        self.ramp_pre_ramp_tolerance_var.set("0.2")
        self.ramp_thermo_deadband_var.set("0.1")
        self.ramp_pid_landing_zone_var.set("0.5")
        self.crash_pid_envelope_width_var.set("2.0")
        
        # --- MODIFICATION: Reset PID logging var ---
        self.pid_logging_var.set(False)
        # --- END MODIFICATION ---
                
    # --- EULA / SUPPORT POPUP ---

    def _load_support_image(self):
        """Loads the QR code image and stores it."""
        if self.support_qr_image:
            return # Already loaded
            
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            # Path is now src/assets/support.gif
            image_path = os.path.join(base_dir, "assets", "support.gif")
            
            # Use tk.PhotoImage directly, which supports GIF natively
            self.support_qr_image = tk.PhotoImage(file=image_path)
            
        except FileNotFoundError:
            self.ui.log_system_message("Error: support.gif image not found.")
            self.support_qr_image = None
        except tk.TclError as e:
            self.ui.log_system_message(f"Error loading support.gif (is it a valid GIF?): {e}")
            self.support_qr_image = None
        except Exception as e:
            self.ui.log_system_message(f"Error loading support image: {e}")
            self.support_qr_image = None
            
    # FIXED
    def _load_relay_led_image(self):
        """Loads the relay LED diagram image and stores it."""
        if self.relay_led_image:
            return # Already loaded
            
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            # Assumes file is named relay_led.gif
            image_path = os.path.join(base_dir, "assets", "relay_led.gif")
            
            # Use tk.PhotoImage directly
            self.relay_led_image = tk.PhotoImage(file=image_path)
            
        except FileNotFoundError:
            self.ui.log_system_message("Error: relay_led.gif image not found.")
            self.relay_led_image = None
        except tk.TclError as e:
            self.ui.log_system_message(f"Error loading relay_led.gif: {e}")
            self.relay_led_image = None
        except Exception as e:
            self.ui.log_system_message(f"Error loading relay LED image: {e}")
            self.relay_led_image = None


    # FIXED
    def _open_system_settings_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("System Settings")
        popup.transient(self.root)
        popup.grab_set()
        
        # --- Create Tabs ---
        notebook = ttk.Notebook(popup)
        notebook.pack(expand=True, fill='both', padx=5, pady=5)
        
        settings_tab = ttk.Frame(notebook, padding=15)
        test_tab = ttk.Frame(notebook, padding=15)
        
        notebook.add(settings_tab, text='Configuration')
        notebook.add(test_tab, text='Test Relays')

        # ==========================================
        # TAB 1: CONFIGURATION (Existing Settings)
        # ==========================================
        
        # 1. Load Current Settings
        comp_settings = self.settings_manager.get_all_compressor_protection_settings()
        
        self.dwell_time_min_var.set(str(int(comp_settings['cooling_dwell_time_s'] / 60)))
        self.max_run_time_min_var.set(str(int(comp_settings['max_cool_runtime_s'] / 60)))
        self.fail_safe_shutdown_min_var.set(str(int(comp_settings['fail_safe_shutdown_time_s'] / 60)))

        current_beer_sensor = self.settings_manager.get("ds18b20_beer_sensor", "unassigned")
        current_amb_sensor = self.settings_manager.get("ds18b20_ambient_sensor", "unassigned")
        
        self.beer_sensor_var.set(current_beer_sensor)
        self.ambient_sensor_var.set(current_amb_sensor)
        
        # 2. Detect Sensors
        available_sensors = ["unassigned"]
        try:
            detected = self.temp_controller.detect_ds18b20_sensors()
            if detected:
                available_sensors.extend(detected)
        except Exception as e:
            print(f"Error detecting sensors: {e}")
            
        if current_beer_sensor not in available_sensors:
            available_sensors.append(current_beer_sensor)
        if current_amb_sensor not in available_sensors and current_amb_sensor != current_beer_sensor:
             available_sensors.append(current_amb_sensor)

        # 3. Build UI for Tab 1
        ttk.Label(settings_tab, text="Compressor Protection", font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 5))
        
        def add_row(parent, label, var, unit="minutes"):
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=30, anchor='w').pack(side='left')
            ttk.Entry(row, textvariable=var, width=10).pack(side='left', padx=(5, 5))
            ttk.Label(row, text=unit).pack(side='left')

        add_row(settings_tab, "Cooling Dwell Time:", self.dwell_time_min_var)
        add_row(settings_tab, "Max Cool Runtime:", self.max_run_time_min_var)
        add_row(settings_tab, "Fail-Safe Shutdown Time:", self.fail_safe_shutdown_min_var)
        
        ttk.Separator(settings_tab, orient='horizontal').pack(fill='x', pady=15)
        
        ttk.Label(settings_tab, text="Sensor Assignment (DS18B20)", font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 5))
        
        def add_sensor_row(parent, label, var, options):
            row = ttk.Frame(parent)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=label, width=30, anchor='w').pack(side='left')
            cb = ttk.Combobox(row, textvariable=var, values=options, state="readonly", width=25)
            cb.pack(side='left', padx=(5, 5))
            return cb

        add_sensor_row(settings_tab, "Beer Sensor:", self.beer_sensor_var, available_sensors)
        add_sensor_row(settings_tab, "Ambient Sensor:", self.ambient_sensor_var, available_sensors)
        
        ttk.Separator(settings_tab, orient='horizontal').pack(fill='x', pady=15)
        
        # --- NEW: Relay Logic Re-Configuration ---
        ttk.Label(settings_tab, text="Hardware Configuration", font=('TkDefaultFont', 10, 'bold')).pack(anchor="w", pady=(0, 5))
        
        logic_frame = ttk.Frame(settings_tab)
        logic_frame.pack(fill="x", pady=2)
        
        current_logic = "Active High" if self.settings_manager.get("relay_active_high") else "Active Low"
        ttk.Label(logic_frame, text=f"Current Relay Logic: {current_logic}").pack(side="left")
        
        ttk.Button(logic_frame, text="Re-configure / Test", 
                   command=lambda: [popup.destroy(), self._open_relay_setup_wizard()]).pack(side="right")
        # -----------------------------------------

        # ==========================================
        # TAB 2: TEST RELAYS
        # ==========================================
        
        self.test_heat_var = tk.BooleanVar(value=False)
        self.test_cool_var = tk.BooleanVar(value=False)
        self.test_aux_var = tk.BooleanVar(value=False)
        
        self.test_heat_status_var = tk.StringVar(value="Heating OFF")
        self.test_cool_status_var = tk.StringVar(value="Cooling OFF")
        self.test_restrict_status_var = tk.StringVar(value="")
        
        is_monitoring = (self.ui.monitoring_var.get() == "ON")
        state_str = "disabled" if is_monitoring else "normal"
        
        if is_monitoring:
            ttk.Label(test_tab, text="Monitoring must be OFF to test relays.", foreground="red", font=('TkDefaultFont', 10, 'bold')).pack(pady=(0, 10))
        else:
             ttk.Label(test_tab, text="Select a relay to force it ON. Only one can be active at a time.", font=('TkDefaultFont', 9, 'italic')).pack(pady=(0, 10))

        controls_frame = ttk.LabelFrame(test_tab, text="Manual Relay Control", padding=10)
        controls_frame.pack(fill="x", pady=(0, 15))
        
        def update_test_colors():
            """Updates the background colors of the test status labels."""
            h_val = self.test_heat_status_var.get()
            c_val = self.test_cool_status_var.get()
            r_val = self.test_restrict_status_var.get()
            
            self.lbl_heat_status.config(style='Red.TLabel' if "HEATING" in h_val else 'Gray.TLabel')
            self.lbl_cool_status.config(style='Blue.TLabel' if "COOLING" in c_val else 'Gray.TLabel')
            
            if "DWELL" in r_val:
                self.lbl_restrict_status.config(style='Yellow.TLabel')
            elif "FAIL-SAFE" in r_val:
                self.lbl_restrict_status.config(style='AlertRed.TLabel')
            else:
                self.lbl_restrict_status.config(style='Gray.TLabel')

        def toggle_relay(selected_relay):
            """Logic to enforce one-at-a-time and update UI immediately."""
            if is_monitoring: return 

            # 1. Enforce Mutual Exclusion in UI
            if selected_relay == "Heat":
                self.test_cool_var.set(False)
                self.test_aux_var.set(False)
            elif selected_relay == "Cool":
                self.test_heat_var.set(False)
                self.test_aux_var.set(False)
            elif selected_relay == "Aux":
                self.test_heat_var.set(False)
                self.test_cool_var.set(False)
            
            # Note: We don't call controller here anymore, the loop handles it naturally 
            # based on the variables we just set. However, calling it once here ensures instant response.
            do_heat = self.test_heat_var.get()
            do_cool = self.test_cool_var.get()
            do_aux = self.test_aux_var.get()
            
            self.temp_controller.relay_control.set_desired_states(
                desired_heat=do_heat, desired_cool=do_cool, control_mode="OFF", aux_override=do_aux
            )
            
            # Update display immediately
            self.test_heat_status_var.set(self.settings_manager.get("heat_state"))
            self.test_cool_status_var.set(self.settings_manager.get("cool_state"))
            self.test_restrict_status_var.set(self.settings_manager.get("cool_restriction_status"))
            update_test_colors()

        ttk.Checkbutton(controls_frame, text="Heating Relay", variable=self.test_heat_var, 
                        command=lambda: toggle_relay("Heat"), state=state_str).pack(anchor="w", pady=2)
        ttk.Checkbutton(controls_frame, text="Cooling Relay", variable=self.test_cool_var, 
                        command=lambda: toggle_relay("Cool"), state=state_str).pack(anchor="w", pady=2)
        ttk.Checkbutton(controls_frame, text="Aux Relay", variable=self.test_aux_var, 
                        command=lambda: toggle_relay("Aux"), state=state_str).pack(anchor="w", pady=2)

        status_frame = ttk.LabelFrame(test_tab, text="System Status", padding=10)
        status_frame.pack(fill="x")
        
        self.lbl_heat_status = ttk.Label(status_frame, textvariable=self.test_heat_status_var, style='Gray.TLabel', relief='sunken', anchor='center')
        self.lbl_heat_status.pack(fill="x", pady=2)
        self.lbl_cool_status = ttk.Label(status_frame, textvariable=self.test_cool_status_var, style='Gray.TLabel', relief='sunken', anchor='center')
        self.lbl_cool_status.pack(fill="x", pady=2)
        self.lbl_restrict_status = ttk.Label(status_frame, textvariable=self.test_restrict_status_var, style='Gray.TLabel', relief='sunken', anchor='center')
        self.lbl_restrict_status.pack(fill="x", pady=2)
        
        ttk.Label(test_tab, text="Note: Cooling relay respects Compressor Protection (Dwell/Fail-Safe).", font=('TkDefaultFont', 8)).pack(pady=(5, 0))
        
        update_test_colors()

        # --- NEW: Background Loop for Test Tab ---
        # This ensures Dwell timers count down and states update even without user clicks.
        def run_test_loop():
            if not popup.winfo_exists():
                return
            
            if not is_monitoring:
                # 1. Get current UI intent
                do_heat = self.test_heat_var.get()
                do_cool = self.test_cool_var.get()
                do_aux_override = self.test_aux_var.get()
                
                # 2. Re-run controller logic (Updates relays based on elapsed time)
                self.temp_controller.relay_control.set_desired_states(
                    desired_heat=do_heat, 
                    desired_cool=do_cool, 
                    control_mode="OFF", 
                    aux_override=do_aux_override
                )
                
                # 3. Refresh Status
                self.test_heat_status_var.set(self.settings_manager.get("heat_state"))
                self.test_cool_status_var.set(self.settings_manager.get("cool_state"))
                self.test_restrict_status_var.set(self.settings_manager.get("cool_restriction_status"))
                update_test_colors()
            
            # Run again in 1 second
            popup.after(1000, run_test_loop)

        if not is_monitoring:
            run_test_loop()

        # ==========================================
        # COMMON BUTTONS
        # ==========================================
        btns_frame = ttk.Frame(popup, padding="10")
        btns_frame.pack(fill="x", side="bottom")
        
        ttk.Button(btns_frame, text="Help", command=lambda: self._open_help_popup("system")).pack(side="left", padx=5)
        ttk.Button(btns_frame, text="Save", command=lambda: self._save_system_settings(popup)).pack(side="right", padx=5)
        
        def on_close():
            # CRITICAL SAFETY: Kill all relays on close if we were in test mode
            if not is_monitoring:
                 self.temp_controller.relay_control.turn_off_all_relays()
            popup.destroy()
            
        # --- TEXT CHANGE: "Close" -> "Cancel" ---
        ttk.Button(btns_frame, text="Cancel", command=on_close).pack(side="right")
        popup.protocol("WM_DELETE_WINDOW", on_close) 

        popup.update_idletasks()
        popup.withdraw()
        self._center_popup(popup, 550, 450)
        
    # FIXED
    def _finalize_relay_setup(self, popup, active_high):
        """Saves the detected logic and initializes the relays."""
        try:
            # 1. Save Settings
            self.settings_manager.set("relay_active_high", active_high)
            self.settings_manager.set("relay_logic_configured", True)
            
            # 2. Update Controller Live
            rc = self.temp_controller.relay_control
            rc.logic_configured = True
            
            # --- CRITICAL FIX ---
            # Pass initial_setup=True to update constants WITHOUT attempting 
            # to write to the GPIO pins yet. The pins are still INPUTs here; 
            # writing to them causes the crash.
            rc.update_relay_logic(initial_setup=True)
            # --------------------
            
            # 3. Initialize Pins (Switch from INPUT to OUT/OFF)
            # This applies the configuration safely to the hardware.
            rc._setup_gpio() 
            
            popup.destroy()
            
            # --- TEXT FIX: Removed "(Standard)" ---
            mode_str = "Active High" if active_high else "Active Low"
            
            self.ui.log_system_message(f"Relay logic configured: {mode_str}")
            
            messagebox.showinfo("Setup Complete", f"Relay logic has been configured as:\n{mode_str}")
            
        except Exception as e:
            messagebox.showerror("Setup Error", f"Failed to apply relay settings: {e}")

    # FIXED
    def _open_relay_setup_wizard(self):
        """
        Opens a wizard that forces the AUX relay LOW and asks the user
        to visually confirm the LED state.
        """
        # 1. Start the hardware test (Send LOW to Aux)
        self.temp_controller.relay_control.run_setup_test("TEST_LOW")
        
        # 2. Load Image
        self._load_relay_led_image()
        
        popup = tk.Toplevel(self.root)
        popup.title("Hardware Setup: Relay Logic")
        popup.transient(self.root)
        popup.grab_set()
        
        main_frame = ttk.Frame(popup, padding=15)
        main_frame.pack(fill="both", expand=True)
        
        # Header
        ttk.Label(main_frame, text="Hardware Logic Detection", font=('TkDefaultFont', 12, 'bold')).pack(pady=(0, 10))
        
        # Instructions
        msg = ("The system has sent a LOW signal to the AUX Relay.\n\n"
               "Please look at your relay board.\n"
               "Is the LED indicator for the AUX relay ON?")
        ttk.Label(main_frame, text=msg, justify="center").pack(pady=(0, 10))
        
        # Image (Placed beneath instructions, above buttons)
        if self.relay_led_image:
            img_label = ttk.Label(main_frame, image=self.relay_led_image)
            img_label.pack(pady=(0, 15))
        else:
            # Fallback if image missing
            ttk.Label(main_frame, text="[Image relay_led.gif missing]", foreground="red").pack(pady=(0, 15))
        
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill="x", pady=5)
        
        # LOGIC MAPPING:
        # User says ON -> LOW signal turned it ON -> Active Low (Standard)
        # --- TEXT CHANGE HERE ---
        ttk.Button(btn_frame, text="YES, AUX LED is ON\n(Active Low Board)", 
                   command=lambda: self._finalize_relay_setup(popup, active_high=False)).pack(side="left", expand=True, padx=5, fill="x")
                   
        # User says OFF -> LOW signal kept it OFF -> Active High
        ttk.Button(btn_frame, text="NO, AUX LED is OFF\n(Active High Board)", 
                   command=lambda: self._finalize_relay_setup(popup, active_high=True)).pack(side="right", expand=True, padx=5, fill="x")
                   
        # Prevent closing without choice
        popup.protocol("WM_DELETE_WINDOW", lambda: None) 
        
        # Increased size to accommodate image (Approx 500x580)
        self._center_popup(popup, 500, 580)
        
    def _open_support_popup(self, is_launch=False):
        """
        Displays the 'Support this App' popup, which includes the EULA.
        'is_launch=True' modifies behavior (e.g., forces modal).
        """
        popup = tk.Toplevel(self.root)
        popup.title("Support This App & EULA")
        
        # --- 1. Load Image ---
        self._load_support_image() # Load/check image

        # --- 2. Reset UI Variables ---
        
        # --- MODIFICATION: Pre-select "I agree" if previously agreed ---
        has_agreed = self.settings_manager.get("eula_agreed", False)
        if has_agreed:
            self.eula_agreement_var.set(1) # 1 = agree
        else:
            self.eula_agreement_var.set(0) # 0 = unset
        # --- END MODIFICATION ---
        
        # Load the saved setting for "show on launch"
        # The checkbox var is "Do not show", so its state is the *inverse*
        show_on_launch_setting = self.settings_manager.get("show_eula_on_launch", True)
        self.show_eula_checkbox_var.set(not show_on_launch_setting)
        
        # --- 3. Build UI ---
        main_frame = ttk.Frame(popup, padding="15")
        main_frame.pack(fill="both", expand=True)

        # --- Top Section ---
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill="x", pady=(0, 15))
        top_frame.grid_columnconfigure(0, weight=1) # Text column
        top_frame.grid_columnconfigure(1, weight=0) # Image column

        support_text = (
            "This App took hundreds of hours to develop, test, and optimize. "
            "Please consider supporting this App with a donation so continuous improvements "
            "can be made. If you wish to receive customer support via email, please "
            "make a reasonable donation in support of this App. Customer support "
            "requests without a donation may not be considered for response."
        )
        
        # --- MODIFICATION: Increased wraplength from 400 to 520 ---
        text_label = ttk.Label(top_frame, text=support_text, wraplength=520, justify="left")
        text_label.grid(row=0, column=0, sticky="nsew", padx=(0, 15))
        
        if self.support_qr_image:
            qr_label = ttk.Label(top_frame, image=self.support_qr_image)
            qr_label.grid(row=0, column=1, sticky="e")
        else:
            qr_placeholder = ttk.Label(top_frame, text="[QR Code Image Missing]", relief="sunken", padding=20)
            qr_placeholder.grid(row=0, column=1, sticky="e")
            
        # --- EULA Section ---
        eula_frame = ttk.LabelFrame(main_frame, text="End User License Agreement (EULA)", padding=10)
        eula_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        eula_text_widget = scrolledtext.ScrolledText(eula_frame, height=10, wrap="word", relief="flat")
        eula_text_widget.pack(fill="both", expand=True)
        
        # --- THIS IS THE FIX ---
        # 1. Define tags
        try:
            default_font = tkfont.nametofont("TkDefaultFont")
            bold_font = default_font.copy()
            bold_font.config(weight="bold")
            eula_text_widget.tag_configure("bold", font=bold_font)
        except:
            eula_text_widget.tag_configure("bold", font=('TkDefaultFont', 10, 'bold'))
        
        # 2. Insert content line by line, applying tags as we go
        eula_text_widget.config(state="normal") # Enable editing to insert text
        
        eula_text_widget.insert("end", "End User License Agreement (EULA)\n\n", "bold")
        
        eula_text_widget.insert("end", "1. Scope of Agreement\n", "bold")
        eula_text_widget.insert("end", (
            "This Agreement applies to the \"Fermentation Vault\" software (hereafter \"this app\"). "
            "\"This app\" includes the main software program and all related software and hardware components, "
            "including commercially supplied, home-made, or independently supplied hardware "
            "and software components of any kind.\n\n"
        ))
        
        eula_text_widget.insert("end", "2. Acceptance of Responsibility\n", "bold")
        eula_text_widget.insert("end", (
            "By using this app, you, the user, accept all responsibility for any consequence or "
            "outcome arising from the use of, or inability to use, this app.\n\n"
        ))
        
        eula_text_widget.insert("end", "3. No Guarantee or Warranty\n", "bold")
        eula_text_widget.insert("end", (
            "This app is provided \"as is.\" It provides no guarantee of usefulness or fitness "
            "for any particular purpose. The app provides no warranty, expressed or implied. "
            "You use this app entirely at your own risk.\n"
        ))
        
        eula_text_widget.config(state="disabled") # Make read-only
        # --- END OF FIX ---

        # --- Agreement Section ---
        agreement_frame = ttk.Frame(main_frame)
        agreement_frame.pack(fill="x")

        # Radio 1: Agree
        agree_rb = ttk.Radiobutton(agreement_frame, 
                                   text="I agree with the above End User License Agreement", 
                                   variable=self.eula_agreement_var, value=1)
        agree_rb.pack(anchor="w")
        agree_note = ttk.Label(agreement_frame, text="User may proceed to the app after closing this popup",
                               font=('TkDefaultFont', 8, 'italic'))
        agree_note.pack(anchor="w", padx=(20, 0), pady=(0, 5))

        # Radio 2: Disagree
        disagree_rb = ttk.Radiobutton(agreement_frame, 
                                     text="I do not agree with the above End User License Agreement", 
                                     variable=self.eula_agreement_var, value=2)
        disagree_rb.pack(anchor="w")
        disagree_note = ttk.Label(agreement_frame, text="User will exit the app after closing this popup",
                                 font=('TkDefaultFont', 8, 'italic'))
        disagree_note.pack(anchor="w", padx=(20, 0), pady=(0, 10))

        # --- Bottom Section (Checkbox & Close) ---
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill="x", side="bottom")

        show_again_cb = ttk.Checkbutton(bottom_frame, 
                                        text="This popup can be found on the Settings & Info menu. Do not show this popup at launch again.",
                                        variable=self.show_eula_checkbox_var)
        show_again_cb.pack(anchor="w", pady=(0, 10))

        close_btn = ttk.Button(bottom_frame, text="Close", 
                               command=lambda: self._handle_support_popup_close(popup))
        close_btn.pack(side="right")

        # --- 4. Finalize Popup ---
        popup.update_idletasks()
        
        # --- MODIFICATION: Use dynamic centering ---
        popup_width = 720
        popup_height = popup.winfo_height()
        self._center_popup(popup, popup_width, popup_height)
        # --- END MODIFICATION ---
        
        popup.resizable(False, False)
        
        # Force modal interaction if on launch
        if is_launch:
            popup.protocol("WM_DELETE_WINDOW", lambda: self._handle_support_popup_close(popup))
            popup.transient(self.root)
            popup.grab_set()
            self.root.wait_window(popup)
        else:
            popup.transient(self.root)
            popup.grab_set()
            
    # FIXED
    def _handle_support_popup_close(self, popup):
        """Handles the logic for the 'Close' button on the Support/EULA popup."""
        
        # Check if the popup is valid
        if not popup.winfo_exists():
            return
        
        agreement_state = self.eula_agreement_var.get()
        do_not_show_checked = self.show_eula_checkbox_var.get()
        
        # --- CASE 1: User Agreed ---
        if agreement_state == 1: 
            print("[PopupManager] User agreed to EULA.")
            
            # Save settings
            self.settings_manager.set("show_eula_on_launch", not do_not_show_checked)
            self.settings_manager.set("eula_agreed", True)
            
            # Close EULA window first
            popup.destroy()
            
            # --- CHAIN TO RELAY WIZARD ---
            # Check if logic is configured. If not, open the wizard IMMEDIATELY.
            # We check for False OR None to be safe.
            is_configured = self.settings_manager.get("relay_logic_configured", False)
            
            if not is_configured:
                print("[PopupManager] Relay logic not configured. Launching Wizard...")
                # Call directly, no .after() delay to prevent timing issues
                self._open_relay_setup_wizard()
            else:
                print("[PopupManager] Relay logic already configured. Skipping Wizard.")
            # -----------------------------
            return

        # --- CASE 2: User Disagreed ---
        elif agreement_state == 2: 
            print("[PopupManager] User disagreed with EULA.")
            
            # Reset "do not show" if they disagreed
            if do_not_show_checked:
                self.settings_manager.set("show_eula_on_launch", True)
            
            self.settings_manager.set("eula_agreed", False)
            
            popup.destroy()
            self._show_disagree_dialog()
            return
            
        # --- CASE 3: No Selection ---
        else: 
            if not popup.winfo_exists(): return
            messagebox.showwarning("Agreement Required", 
                                   "You must select 'I agree' or 'I do not agree' to proceed.", 
                                   parent=popup)
            return

    def _show_disagree_dialog(self):
        """Shows the final confirmation dialog when user disagrees with EULA."""
        
        # --- MODIFICATION: Updated dialog text ---
        if messagebox.askokcancel("EULA Disagreement",
                                "You chose to not agree with the End User License Agreement, so the app will terminate when you click OK.\n\n"
                                "Click Cancel to return to the agreement or click OK to exit the app."):
            # --- END MODIFICATION ---
            
            # User clicked OK (True) -> Terminate the app
            self.ui.log_system_message("User disagreed with EULA. Terminating application.")
            
            # We must call the root's destroy method
            self.root.destroy()
            
        else:
            # User clicked Cancel (False) -> Re-open the EULA popup
            # Force it as a 'launch' popup to ensure it's modal
            self._open_support_popup(is_launch=True)
            
            
