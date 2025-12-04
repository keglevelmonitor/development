# keglevel app
#
# popup_manager_mixin.py
import shutil # required for recursive Uninstall deletion
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import tkinter.font as tkfont 
import math
import time
import queue
import os
import uuid 
import subprocess 
import sys      
import re
import threading


# FIX: Import UNASSIGNED_KEG_ID and UNASSIGNED_BEVERAGE_ID
try:
    from settings_manager import UNASSIGNED_KEG_ID, UNASSIGNED_BEVERAGE_ID
except ImportError:
    UNASSIGNED_KEG_ID = "unassigned_keg_id"
    UNASSIGNED_BEVERAGE_ID = "unassigned_beverage_id"
    
# --- NEW: EULA/Support Imports ---
import tkinter.scrolledtext as scrolledtext
import webbrowser
# --- END NEW ---

# --- NEW: Import manage_autostart_file from main.py ---
from main import manage_autostart_file
# --- END NEW IMPORT ---

# --- NEW: Import ProcessFlowApp for in-process hosting ---
# Removing mock for ProcessFlowApp is not feasible here as it needs to run 
# in the environment if the import fails, so the conditional import is necessary.
try:
    from process_flow import ProcessFlowApp 
except ImportError:
    class ProcessFlowApp:
        def __init__(self, root_window, settings_manager, base_dir, parent_root=None): pass
        def run(self): print("ProcessFlowApp mock run.")

# --- NEW: Import platform flag from sensor_logic ---\
# FIX: IS_RASPBERRY_PI_MODE is still needed, keep import.
from sensor_logic import IS_RASPBERRY_PI_MODE
# ------------------------------------

LITERS_TO_GALLONS = 0.264172
KG_TO_LB = 2.20462
# CONSTANT: Ratio of US Fluid Ounces to Liters
OZ_TO_LITERS = 0.0295735

# --- MIXIN CLASS: Contains all settings/popup logic ---
class PopupManagerMixin:    
    """
    Mixin class to handle popups (Help, Support/EULA, etc.) for the KegLevel application.
    Assumes access to:
      - self.root
      - self.settings_manager
      - self.support_qr_image (can be None)
      - self._load_support_image()
      - self.eula_agreement_var
      - self.show_eula_checkbox_var
    """
    
    def __init__(self, settings_manager_instance, num_sensors, app_version_string=None):
        self.settings_manager = settings_manager_instance
        self.num_sensors = num_sensors
        self.base_dir = os.path.dirname(os.path.abspath(__file__)) 
        
        # --- Version Calculation (Unchanged) ---
        version_source = app_version_string if app_version_string else 'Unknown (Script Model)'
        try:
            executable_path = sys.argv[0]
            filename = os.path.basename(executable_path)
            match = re.search(r'KegLevel_Monitor_(\d{12})', filename)
            if match:
                datecode = match.group(1)
                year, month, day, hour, minute = datecode[0:4], datecode[4:6], datecode[6:8], datecode[8:10], datecode[10:12]
                version_source = f"{datecode} (Compiled: {year}-{month}-{day} {hour}:{minute})"
        except Exception:
            version_source = "Unknown (Error during startup parsing)"
        self.app_version_string = version_source 
        
        # --- Settings Popup Variables ---
        self.beverage_popup_vars = [] 
        self.keg_settings_popup_vars = [] 
        
        # System Settings
        self.system_settings_unit_var = tk.StringVar()
        self.system_settings_taps_var = tk.StringVar()
        self.system_settings_ui_mode_var = tk.StringVar()
        self.system_settings_temp_unit_label = tk.StringVar() 
        self.sensor_ambient_var = tk.StringVar()
        
        self.system_settings_autostart_var = tk.BooleanVar() 
        self.system_settings_launch_workflow_var = tk.BooleanVar() 
        
        # --- Terminal Toggle Variable ---
        self.system_settings_terminal_var = tk.BooleanVar()

        # --- Num Lock Variable ---
        self.system_settings_numlock_var = tk.BooleanVar()

        # --- Pour Volume Variables (Backing Store & Display) ---
        self.system_settings_pour_ml_var = tk.StringVar()
        self.system_settings_pour_oz_var = tk.StringVar()
        self.system_settings_pour_size_display_var = tk.StringVar() 
        self.system_settings_pour_unit_label_var = tk.StringVar()   
        
        # --- Messaging Settings Variables ---
        self.msg_push_enabled_var = tk.BooleanVar()
        self.msg_conditional_enabled_var = tk.BooleanVar()
        self.status_req_enable_var = tk.BooleanVar() 
        
        # --- NEW: Update Notification Variable ---
        self.msg_notify_on_update_var = tk.BooleanVar()
        # ----------------------------------------

        self.msg_frequency_var = tk.StringVar()
        self.msg_server_email_var = tk.StringVar()
        self.msg_server_password_var = tk.StringVar()
        self.msg_email_recipient_var = tk.StringVar()
        self.msg_smtp_server_var = tk.StringVar()
        self.msg_smtp_port_var = tk.StringVar()
        
        self.status_req_sender_var = tk.StringVar() 
        self.status_req_imap_server_var = tk.StringVar()
        self.status_req_imap_port_var = tk.StringVar()
        
        self.msg_conditional_threshold_var = tk.StringVar()
        self.msg_conditional_threshold_units_var = tk.StringVar(value="Gallons")
        self.last_units_for_threshold = self.settings_manager.get_display_units()
        self.msg_conditional_threshold_label_text = tk.StringVar()
        self.msg_conditional_low_temp_var = tk.StringVar()
        self.msg_conditional_high_temp_var = tk.StringVar()
        
        # --- Flow Calibration Variables ---
        self.flow_cal_current_factors = [tk.StringVar() for _ in range(self.num_sensors)]
        self.flow_cal_new_factor_entries = [tk.StringVar() for _ in range(self.num_sensors)]
        self.flow_cal_notes_var = tk.StringVar()
        self.single_cal_target_volume_var = tk.StringVar()
        self.single_cal_measured_flow_var = tk.StringVar(value="0.00 L/min")
        self.single_cal_measured_pour_var = tk.StringVar(value="0.00")
        self.single_cal_unit_label = tk.StringVar()
        self.single_cal_tap_index = -1
        self.single_cal_current_factor_var = tk.StringVar() 
        self.single_cal_new_factor_var = tk.StringVar()      
        self._single_cal_calculated_new_factor = None        
        self.single_cal_deduct_volume_var = tk.BooleanVar(value=False)

        self._single_cal_in_progress = False
        self._single_cal_complete = False
        self._single_cal_pulse_count = 0
        self._single_cal_last_pour = 0.0
        self._single_cal_popup_window = None 

        # --- EULA/Support Popup Variables ---
        self.eula_agreement_var = tk.IntVar(value=0) 
        self.show_eula_checkbox_var = tk.BooleanVar()
        self.support_qr_image = None
        
    # --- NEW: Helper for checking git status (Used by UI and NotificationService) ---
    def check_update_available(self):
        """
        Checks if the local git branch is behind origin.
        Returns True if an update is available, False otherwise.
        """
        try:
            # base_dir is src/, so project_dir is one up
            project_dir = os.path.dirname(self.base_dir)
            
            # 1. Fetch latest info (silent)
            subprocess.run(
                ['git', 'fetch', 'origin'], 
                cwd=project_dir, 
                check=True, 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            
            # 2. Check status
            result = subprocess.run(
                ['git', 'status', '-uno'], 
                cwd=project_dir, 
                check=True, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
            
            if "Your branch is behind" in result.stdout:
                return True
                
        except Exception as e:
            print(f"Update Check Logic Error: {e}")
            
        return False
    # -------------------------------------------------------------------------------

    def _open_message_settings_popup(self):
        popup = tk.Toplevel(self.root)
        popup.withdraw() 
        
        popup.title("Notification Settings")
        popup.transient(self.root)
        popup.grab_set()
        
        form_frame = ttk.Frame(popup, padding="5")
        form_frame.pack(expand=True, fill="both")
        
        # --- FETCH SETTINGS ---
        push_notif_settings = self.settings_manager.get_push_notification_settings()
        cond_notif_settings = self.settings_manager.get_conditional_notification_settings()
        status_req_settings = self.settings_manager.get_status_request_settings()
        display_units = self.settings_manager.get_display_units()
        
        # --- INITIALIZE VARIABLES ---
        
        # 1. Push Logic
        push_type = push_notif_settings.get('notification_type', 'None')
        self.msg_push_enabled_var.set(push_type != 'None')
        self.msg_frequency_var.set(push_notif_settings.get('frequency', 'Daily'))
        
        # Shared Recipient
        self.msg_email_recipient_var.set(push_notif_settings.get('email_recipient', ''))
        
        # --- NEW: Load Update Notification Setting ---
        self.msg_notify_on_update_var.set(push_notif_settings.get('notify_on_update', True))
        # ---------------------------------------------

        # 2. Conditional Logic
        cond_type = cond_notif_settings.get('notification_type', 'None')
        self.msg_conditional_enabled_var.set(cond_type != 'None')
        
        # Initialize Thresholds (Unit Conversion)
        cond_threshold_liters = cond_notif_settings.get('threshold_liters')
        if display_units == "imperial":
            threshold_value = cond_threshold_liters * LITERS_TO_GALLONS if cond_threshold_liters is not None else None
            self.msg_conditional_threshold_var.set(f"{threshold_value:.2f}" if threshold_value is not None else "")
            self.msg_conditional_threshold_units_var.set("Gallons")
        else:
            self.msg_conditional_threshold_var.set(f"{cond_threshold_liters:.2f}" if cond_threshold_liters is not None else "")
            self.msg_conditional_threshold_units_var.set("Liters")

        low_temp_f = cond_notif_settings.get('low_temp_f'); high_temp_f = cond_notif_settings.get('high_temp_f')
        if display_units == "imperial":
            self.msg_conditional_low_temp_var.set(f"{low_temp_f:.1f}" if low_temp_f is not None else "")
            self.msg_conditional_high_temp_var.set(f"{high_temp_f:.1f}" if high_temp_f is not None else "")
        else:
            low_temp_c = (low_temp_f - 32) * (5/9) if low_temp_f is not None else None
            high_temp_c = (high_temp_f - 32) * (5/9) if high_temp_f is not None else None
            self.msg_conditional_low_temp_var.set(f"{low_temp_c:.1f}" if low_temp_c is not None else "")
            self.msg_conditional_high_temp_var.set(f"{high_temp_c:.1f}" if high_temp_f is not None else "")

        # 3. Status Request Logic
        self.status_req_enable_var.set(status_req_settings.get('enable_status_request', False))
        self.status_req_sender_var.set(status_req_settings.get('authorized_sender', ''))

        # 4. RPi Config
        self.msg_server_email_var.set(push_notif_settings.get('server_email', ''))
        self.msg_server_password_var.set(push_notif_settings.get('server_password', ''))
        self.msg_smtp_server_var.set(push_notif_settings.get('smtp_server', ''))
        
        smtp_port_val = push_notif_settings.get('smtp_port', '')
        self.msg_smtp_port_var.set(str(smtp_port_val) if isinstance(smtp_port_val, int) else '')
        
        self.status_req_imap_server_var.set(status_req_settings.get('imap_server', ''))
        
        imap_port_val = status_req_settings.get('imap_port', '')
        self.status_req_imap_port_var.set(str(imap_port_val) if isinstance(imap_port_val, int) else '')

        # --- HELPER FOR ROWS ---
        def add_row(parent_frame, label_text, string_var, show_char=None, is_dropdown=False, options=None):
            row_frame = ttk.Frame(parent_frame); row_frame.pack(fill="x", pady=2)
            ttk.Label(row_frame, text=label_text, width=25, anchor='w').pack(side="left", padx=(5, 5))
            
            widget = None
            if is_dropdown:
                widget = ttk.Combobox(row_frame, textvariable=string_var, values=options, state="readonly", width=30)
            else:
                widget = ttk.Entry(row_frame, textvariable=string_var, width=30, show=show_char)
            widget.pack(side="left", fill="x", expand=True)
            return widget

        # --- BUILD UI (NOTEBOOK) ---
        notebook = ttk.Notebook(form_frame)
        notebook.pack(expand=True, fill='both', padx=5, pady=5)

        # Tab 1: Alerts & Controls
        tab1 = ttk.Frame(notebook, padding=10)
        notebook.add(tab1, text='Alerts & Controls')

        # Tab 2: RPi Email Configuration
        tab2 = ttk.Frame(notebook, padding=10)
        notebook.add(tab2, text='RPi Email Configuration')
        
        # ============================================================
        # TAB 1: ALERTS & CONTROLS
        # ============================================================
        
        # Section A: Outbound Alerts
        outbound_frame = ttk.LabelFrame(tab1, text="Outbound Alerts (Push & Conditional)", padding=10)
        outbound_frame.pack(fill='x', pady=(0, 10))
        
        # 1. Recipient
        self.shared_recipient_entry = add_row(outbound_frame, "Recipient Email:", self.msg_email_recipient_var)
        ttk.Label(outbound_frame, text="(Required if any Outbound notification is enabled)", 
                  font=('TkDefaultFont', 8, 'italic')).pack(anchor='w', padx=25, pady=(0, 10))

        # 2. Push Notifications
        self.push_check = ttk.Checkbutton(outbound_frame, text="Enable Push Notifications", variable=self.msg_push_enabled_var)
        self.push_check.pack(anchor='w', pady=(0, 2))
        
        push_notes = "E.g. Daily status reports sent at a fixed interval."
        ttk.Label(outbound_frame, text=push_notes, font=('TkDefaultFont', 8, 'italic'), wraplength=500).pack(anchor='w', padx=25, pady=(0, 5))
        
        freq_frame = ttk.Frame(outbound_frame); freq_frame.pack(fill='x', padx=25, pady=(0, 10))
        ttk.Label(freq_frame, text="Report Frequency:", width=20, anchor='w').pack(side='left')
        self.freq_dropdown = ttk.Combobox(freq_frame, textvariable=self.msg_frequency_var, 
                                          values=["Hourly", "Daily", "Weekly", "Monthly"], state="readonly", width=20)
        self.freq_dropdown.pack(side='left')

        # 3. Conditional Notifications
        self.cond_check = ttk.Checkbutton(outbound_frame, text="Enable Conditional Notifications", variable=self.msg_conditional_enabled_var)
        self.cond_check.pack(anchor='w', pady=(0, 2))
        
        cond_options_frame = ttk.Frame(outbound_frame); cond_options_frame.pack(fill="x", padx=25, pady=(0, 10))

        # Volume Row
        self.cond_vol_frame = ttk.Frame(cond_options_frame); self.cond_vol_frame.pack(fill="x", pady=2)
        ttk.Label(self.cond_vol_frame, text="Notify when tap volume <", width=24).pack(side="left", padx=(5,0))
        self.cond_vol_entry = ttk.Entry(self.cond_vol_frame, textvariable=self.msg_conditional_threshold_var, width=8)
        self.cond_vol_entry.pack(side="left")
        ttk.Label(self.cond_vol_frame, textvariable=self.msg_conditional_threshold_units_var).pack(side="left", padx=(5, 5))

        # Temp Row
        self.cond_temp_frame = ttk.Frame(cond_options_frame); self.cond_temp_frame.pack(fill="x", pady=2)
        unit_char = "F" if display_units == "imperial" else "C"
        ttk.Label(self.cond_temp_frame, text=f"Notify when Temp outside:", width=24).pack(side="left", padx=(5,0))
        self.cond_low_entry = ttk.Entry(self.cond_temp_frame, textvariable=self.msg_conditional_low_temp_var, width=6)
        self.cond_low_entry.pack(side="left")
        ttk.Label(self.cond_temp_frame, text=f" - ").pack(side="left")
        self.cond_high_entry = ttk.Entry(self.cond_temp_frame, textvariable=self.msg_conditional_high_temp_var, width=6)
        self.cond_high_entry.pack(side="left")
        ttk.Label(self.cond_temp_frame, text=f"{unit_char}").pack(side="left", padx=(5, 5))

        # 4. Update Notifications (NEW)
        self.update_check = ttk.Checkbutton(outbound_frame, text="Notify when an update is available", variable=self.msg_notify_on_update_var)
        self.update_check.pack(anchor='w', pady=(0, 2))
        ttk.Label(outbound_frame, text="Checks once every 24 hours.", font=('TkDefaultFont', 8, 'italic')).pack(anchor='w', padx=25)

        # Section B: Inbound Controls
        inbound_frame = ttk.LabelFrame(tab1, text="Inbound Controls (Status & Commands)", padding=10)
        inbound_frame.pack(fill='x', pady=10)

        self.req_check = ttk.Checkbutton(inbound_frame, text="Enable Email Control (Status & Commands)", variable=self.status_req_enable_var)
        self.req_check.pack(anchor='w', pady=(0, 5))
        
        warning_text_tab1 = (
            "WARNING: When enabled, the app checks the 'RPi Email Configuration' account for new messages "
            "from the Authorized Sender. If new messages exist, the app marks them as 'read', and "
            "processes them for 'Status' or 'Command' actions. Only enable this feature if you are using "
            "a dedicated email account set up exclusively for this app."
        )
        ttk.Label(inbound_frame, text=warning_text_tab1, font=('TkDefaultFont', 8, 'italic'), wraplength=550, justify='left').pack(anchor='w', padx=20, pady=(0, 5))

        auth_frame = ttk.Frame(inbound_frame); auth_frame.pack(fill='x', padx=20)
        ttk.Label(auth_frame, text="Authorized Sender:", width=20, anchor='w').pack(side='left')
        self.req_sender_entry = ttk.Entry(auth_frame, textvariable=self.status_req_sender_var, width=35)
        self.req_sender_entry.pack(side='left', fill='x', expand=True)

        # ============================================================
        # TAB 2: RPi CONFIG
        # ============================================================
        
        warning_text_tab2 = (
            "WARNING: When Email Control is enabled, the app checks the 'RPi Email Configuration' account for new messages "
            "from the Authorized Sender. If new messages exist, the app marks them as 'read', and "
            "processes them for 'Status' or 'Command' actions. Only enable this feature if you are using "
            "a dedicated email account set up exclusively for this app."
        )
        ttk.Label(tab2, text=warning_text_tab2, font=('TkDefaultFont', 8, 'italic'), wraplength=550, justify='left').pack(anchor='w', pady=(0, 15))

        self.rpi_email_entry = add_row(tab2, "RPi Email Address:", self.msg_server_email_var)
        self.rpi_password_entry = add_row(tab2, "RPi Email Password:", self.msg_server_password_var, show_char="*")
        ttk.Separator(tab2, orient='horizontal').pack(fill='x', pady=10)
        self.smtp_server_entry = add_row(tab2, "SMTP (Outgoing) Server:", self.msg_smtp_server_var)
        self.smtp_port_entry = add_row(tab2, "SMTP (Outgoing) Port:", self.msg_smtp_port_var)
        ttk.Separator(tab2, orient='horizontal').pack(fill='x', pady=10)
        self.imap_server_entry = add_row(tab2, "IMAP (Incoming) Server:", self.status_req_imap_server_var)
        self.imap_port_entry = add_row(tab2, "IMAP (Incoming) Port:", self.status_req_imap_port_var)

        # --- BUTTONS ---
        btns_frame = ttk.Frame(popup, padding="10"); btns_frame.pack(fill="x", side="bottom")
        ttk.Button(btns_frame, text="Save", command=lambda: self._save_message_settings(popup)).pack(side="right", padx=5)
        ttk.Button(btns_frame, text="Cancel", command=popup.destroy).pack(side="right", padx=5)
        ttk.Button(btns_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("notifications")).pack(side="right", padx=5)

        # --- TRACES ---
        self.msg_push_enabled_var.trace_add("write", self._toggle_email_fields_state)
        self.msg_conditional_enabled_var.trace_add("write", self._toggle_email_fields_state)
        self.status_req_enable_var.trace_add("write", self._toggle_email_fields_state)
        # Add trace for update notification too
        self.msg_notify_on_update_var.trace_add("write", self._toggle_email_fields_state)
        
        self._toggle_email_fields_state()
        
        self._center_popup(popup, 650, 600) # Slightly taller for new option
        
        if hasattr(self, 'shared_recipient_entry'):
            self.shared_recipient_entry.focus_set()
        
        
    def _save_status_request_settings(self, popup_window):
        # 1. Validation
        if self.status_req_enable_var.get():
            fields_to_check = [
                (self.status_req_sender_var, "Authorized Sender"),
                (self.status_req_rpi_email_var, "RPi Email"),
                (self.status_req_rpi_password_var, "RPi Password"),
                (self.status_req_imap_server_var, "IMAP Server"),
                (self.status_req_imap_port_var, "IMAP Port"),
                (self.status_req_smtp_server_var, "SMTP Server"),
                (self.status_req_smtp_port_var, "SMTP Port")
            ]
            
            for var, name in fields_to_check:
                if not var.get().strip():
                    messagebox.showerror("Input Error", f"Enabling Status Request requires the '{name}' field to be filled.", parent=popup_window)
                    return
            
            try:
                if not (0 < int(self.status_req_imap_port_var.get().strip()) <= 65535):
                    messagebox.showerror("Input Error", "IMAP Port must be 1-65535.", parent=popup_window)
                    return
                if not (0 < int(self.status_req_smtp_port_var.get().strip()) <= 65535):
                    messagebox.showerror("Input Error", "SMTP Port must be 1-65535.", parent=popup_window)
                    return
            except ValueError:
                messagebox.showerror("Input Error", "IMAP/SMTP Port must be valid numbers.", parent=popup_window)
                return

        # 2. Compile settings dict (port variables are saved as strings/empty strings if not integer)
        new_settings = {
            "enable_status_request": self.status_req_enable_var.get(),
            "authorized_sender": self.status_req_sender_var.get().strip(),
            "rpi_email_address": self.status_req_rpi_email_var.get().strip(),
            "rpi_email_password": self.status_req_rpi_password_var.get(),
            "imap_server": self.status_req_imap_server_var.get().strip(),
            "imap_port": self.status_req_imap_port_var.get().strip(), # Saved as string, converted to int/"" by SettingsManager
            "smtp_server": self.status_req_smtp_server_var.get().strip(),
            "smtp_port": self.status_req_smtp_port_var.get().strip() # Saved as string, converted to int/"" by SettingsManager
        }

        # 3. Save and trigger reschedule
        self.settings_manager.save_status_request_settings(new_settings)
        
        if hasattr(self, 'notification_service') and self.notification_service: 
            # This handles stopping the old thread and starting the new one if enabled/disabled
            self.notification_service.force_reschedule() 
        
        print("UIManager: Status Request settings saved.")
        popup_window.destroy()
        
    # --- END Status Request Settings Popup Logic ---

    # --- Popup Implementations ---

    def _open_workflow_popup(self):
        try:
            workflow_window = tk.Toplevel(self.root)
            workflow_window.title("KegLevel Workflow")
            workflow_window.transient(self.root)
            
            ui_mode = self.settings_manager.get_ui_mode()
            is_full_mode = (ui_mode == 'full')

            if is_full_mode:
                WORKFLOW_WIDTH, WORKFLOW_HEIGHT, X_POS, Y_POS = 1920, 564, 0, 522
                workflow_window.geometry(f"{WORKFLOW_WIDTH}x{WORKFLOW_HEIGHT}+{X_POS}+{Y_POS}")
                workflow_window.resizable(True, True) 
            else:
                W, H = 700, 600
                X, Y = 0, 72 
                workflow_window.geometry(f"{W}x{H}+{X}+{Y}")
                workflow_window.resizable(False, False)

            self.workflow_app = ProcessFlowApp(
                root_window=workflow_window, 
                settings_manager=self.settings_manager, 
                base_dir=self.base_dir, 
                parent_root=self.root 
            )
            
            self.workflow_app.run() 
            
            if not IS_RASPBERRY_PI_MODE:
                messagebox.showinfo("Workflow Launched", 
                                    "KegLevel Workflow has been launched in a separate window. "
                                    "If not immediately visible, please check your taskbar.", 
                                    parent=self.root)

        except Exception as e:
            messagebox.showerror("Launch Error", f"Could not launch Workflow UI in-process:\n{e}", parent=self.root)
            if 'workflow_window' in locals() and workflow_window.winfo_exists():
                 workflow_window.destroy()
                 
    def _open_update_status_popup(self, popup, on_complete_callback):
        """
        Opens the intermediate dialog to show the update script's output.
        This is based on the FermVault implementation.
        MODIFIED: Accepts an on_complete_callback to fix race condition.
        """
        # Create a queue to send stdout lines from the thread to the UI
        update_queue = queue.Queue()
        
        # Create the popup
        status_popup = tk.Toplevel(self.root)
        status_popup.title("Checking for Updates...")
        status_popup.geometry("600x400")
        status_popup.transient(self.root)
        status_popup.grab_set()

        # Create a ScrolledText widget
        text_area = scrolledtext.ScrolledText(status_popup, wrap=tk.WORD, height=20, width=80)
        text_area.pack(padx=10, pady=10, fill="both", expand=True)
        text_area.insert(tk.END, "Starting update check...\n")
        text_area.insert(tk.END, "This may take a moment. Please wait for the script to finish.\n")
        text_area.insert(tk.END, "--------------------------------------------------\n")
        text_area.config(state="disabled")

        # Create a close button (initially disabled)
        close_button = ttk.Button(status_popup, text="Close", state="disabled")
        close_button.pack(pady=(0, 10))
        
        def check_queue():
            """Polls the queue for new messages from the update thread."""
            try:
                while True:
                    line = update_queue.get_nowait()
                    if line is None: # End signal
                        close_button.config(state="normal")
                        status_popup.title("Update Check Finished")
                        
                        # --- FIX: Trigger the callback function ---
                        if on_complete_callback:
                            on_complete_callback(status_popup) # Pass popup to the callback
                        # --- END FIX ---
                        return # Stop polling
                    
                    text_area.config(state="normal")
                    text_area.insert(tk.END, line)
                    text_area.see(tk.END)
                    text_area.config(state="disabled")
                    
            except queue.Empty:
                pass # No new messages
            
            status_popup.after(100, check_queue)

        # Start polling the queue
        status_popup.after(100, check_queue)

        # Make the close button work
        close_button.config(command=status_popup.destroy)

        return update_queue, status_popup

    def _read_update_output(self, process, queue_, shared_output_list):
        """
        Thread target function: Reads stdout from the subprocess
        and puts it on the queue.
        MODIFIED: Now stores full output in a shared list to avoid race conditions.
        """
        full_output = ""
        try:
            # Read stdout line by line in real-time
            for line in iter(process.stdout.readline, ''):
                queue_.put(line) # Put line for UI
                full_output += line
            
            process.stdout.close()
            return_code = process.wait()
            
            if return_code != 0:
                stderr_output = process.stderr.read()
                error_lines = f"\n--- SCRIPT ERROR ---\nReturn Code: {return_code}\n{stderr_output}"
                queue_.put(error_lines) # Put error for UI
                full_output += error_lines
                
        except Exception as e:
            error_lines = f"\n--- PYTHON ERROR ---\nError reading script output: {e}\n"
            queue_.put(error_lines) # Put error for UI
            
        finally:
            # --- FIX: Store final output for parser, then send end signal ---
            shared_output_list.append(full_output) 
            queue_.put(None) 
            # --- END FIX --- 
            

    def _check_for_updates(self, is_launch_check=False):
        """
        Opens the update window and starts Phase 1 (Check).
        If is_launch_check is True, it runs silently first and only shows popup if update exists.
        """
        script_path = os.path.join(self.base_dir, "..", "update.sh")
        
        if not os.path.exists(script_path):
            if not is_launch_check:
                messagebox.showerror("Error", f"Update script not found at:\n{script_path}", parent=self.root)
            else:
                print(f"Update Check: Script not found at {script_path}")
            return

        if is_launch_check:
            # Silent Check Mode
            threading.Thread(
                target=self._run_silent_update_check,
                args=(script_path,),
                daemon=True
            ).start()
            return

        # Normal (Menu) Mode: Show Popup immediately
        self._show_update_popup(script_path)
        
    def _show_update_popup(self, script_path, initial_message=None):
        """Helper to create and show the update popup window."""
        status_popup = tk.Toplevel(self.root)
        status_popup.title("System Update")
        status_popup.geometry("650x500") # Increased height for checkbox
        status_popup.transient(self.root)
        status_popup.grab_set()
        
        # 2. Text Area for Logging
        text_area = scrolledtext.ScrolledText(status_popup, wrap=tk.WORD, height=20, width=80)
        text_area.pack(padx=10, pady=10, fill="both", expand=True)
        
        text_area.tag_config("info", foreground="black")
        text_area.tag_config("success", foreground="green")
        text_area.tag_config("warning", foreground="#FF8C00") 
        text_area.tag_config("error", foreground="red")
        
        if initial_message:
             text_area.insert(tk.END, initial_message, "info")
        else:
             text_area.insert(tk.END, "Initializing update check...\n", "info")
             
        text_area.config(state="disabled")

        # 3. Checkbox Frame
        chk_frame = ttk.Frame(status_popup, padding=(10, 0, 10, 5))
        chk_frame.pack(fill="x")
        
        check_on_launch_var = tk.BooleanVar(value=self.settings_manager.get_check_updates_on_launch())
        
        def on_check_toggle():
            self.settings_manager.save_check_updates_on_launch(check_on_launch_var.get())
            
        ttk.Checkbutton(chk_frame, text="Enable Check for Updates on launch", 
                        variable=check_on_launch_var, command=on_check_toggle).pack(side="left")

        # 4. Button Frame
        btn_frame = ttk.Frame(status_popup, padding=(0, 0, 0, 10))
        btn_frame.pack(fill="x")
        
        # Define Buttons (Pack order: Right to Left)
        
        # A. Close (Window only)
        close_btn = ttk.Button(btn_frame, text="Close", state="disabled", command=status_popup.destroy)
        close_btn.pack(side="right", padx=5)
        
        # NEW Help Button
        ttk.Button(btn_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("check_for_updates")).pack(side="right", padx=5)
        
        # B. Close App (Shutdown app for restart) - Initially Disabled
        close_app_btn = ttk.Button(btn_frame, text="Close App (Restart)", state="disabled", 
                                   command=lambda: [status_popup.destroy(), self._on_closing_ui()])
        close_app_btn.pack(side="right", padx=5)
        
        # C. Install Updates - Initially Disabled
        install_btn = ttk.Button(btn_frame, text="Install Updates", state="disabled")
        install_btn.pack(side="right", padx=5)

        # 5. Start Phase 1 (if not already done via silent check)
        if not initial_message:
            threading.Thread(
                target=self._run_update_check_phase,
                args=(text_area, install_btn, close_btn, close_app_btn, script_path, status_popup),
                daemon=True
            ).start()
        else:
            # If we provided an initial message, it means silent check found an update.
            # Enable the install button immediately.
            install_btn.config(state="normal", 
                command=lambda: self._start_install_phase(text_area, install_btn, close_btn, close_app_btn, script_path))
            close_btn.config(state="normal")

    def _run_silent_update_check(self, script_path):
        """Runs git fetch/status silently. If update found, opens popup."""
        project_dir = os.path.dirname(self.base_dir)
        
        try:
            # Step A: Git Fetch
            subprocess.run(
                ['git', 'fetch', 'origin'], 
                cwd=project_dir, check=True, 
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            
            # Step B: Check Status
            result = subprocess.run(
                ['git', 'status', '-uno'], 
                cwd=project_dir, check=True, 
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            
            output = result.stdout
            
            if "Your branch is behind" in output:
                # Update found! Open the popup on the main thread.
                def open_popup_with_result():
                    msg = "--- AUTOMATIC UPDATE CHECK ---\n"
                    msg += output
                    msg += "\n[!] UPDATE AVAILABLE\nClick 'Install Updates' to proceed.\n"
                    self._show_update_popup(script_path, initial_message=msg)
                
                self.root.after(0, open_popup_with_result)
            else:
                print("Silent Update Check: System is up to date.")

        except Exception as e:
             print(f"Silent Update Check Failed: {e}")

    def _safe_log_to_update_window(self, text_widget, message, tag="info"):
        """Helper to write to the scrolled text widget from a background thread."""
        def _update():
            if not text_widget.winfo_exists(): return
            text_widget.config(state="normal")
            text_widget.insert(tk.END, message + "\n", tag)
            text_widget.see(tk.END)
            text_widget.config(state="disabled")
        self.root.after(0, _update)

    def _run_update_check_phase(self, text_widget, install_btn, close_btn, close_app_btn, script_path, popup):
        """
        Phase 1: Runs git fetch/status to see if updates are needed.
        """
        self._safe_log_to_update_window(text_widget, "--- PHASE 1: CHECKING FOR UPDATES ---", "info")
        
        project_dir = os.path.dirname(self.base_dir)
        
        try:
            # Step A: Git Fetch
            self._safe_log_to_update_window(text_widget, "> git fetch origin", "info")
            subprocess.run(
                ['git', 'fetch', 'origin'], 
                cwd=project_dir, check=True, 
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            
            # Step B: Check Status
            self._safe_log_to_update_window(text_widget, "> git status -uno", "info")
            result = subprocess.run(
                ['git', 'status', '-uno'], 
                cwd=project_dir, check=True, 
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            
            output = result.stdout
            self._safe_log_to_update_window(text_widget, output, "info")
            
            # Step C: Analyze Result
            if "Your branch is behind" in output:
                self._safe_log_to_update_window(text_widget, "\n[!] UPDATE AVAILABLE", "success")
                self._safe_log_to_update_window(text_widget, "Click 'Install Updates' to proceed.", "info")
                
                # Enable Install Button via main thread
                def _enable_install():
                    if install_btn.winfo_exists():
                        install_btn.config(state="normal", 
                            command=lambda: self._start_install_phase(text_widget, install_btn, close_btn, close_app_btn, script_path))
                    if close_btn.winfo_exists():
                        close_btn.config(state="normal")
                self.root.after(0, _enable_install)
                
            elif "Your branch is up to date" in output:
                self._safe_log_to_update_window(text_widget, "\n[OK] System is up to date.", "success")
                self.root.after(0, lambda: close_btn.config(state="normal"))
                
            else:
                self._safe_log_to_update_window(text_widget, "\n[?] Status Unclear. Please check logs.", "warning")
                self.root.after(0, lambda: close_btn.config(state="normal"))

        except Exception as e:
            self._safe_log_to_update_window(text_widget, f"\n[ERROR] Check failed: {e}", "error")
            self.root.after(0, lambda: close_btn.config(state="normal"))

    def _start_install_phase(self, text_widget, install_btn, close_btn, close_app_btn, script_path):
        """Triggered by the Install button. Disables buttons and starts Phase 2."""
        install_btn.config(state="disabled")
        close_btn.config(state="disabled")
        # Close App remains disabled during install
        
        threading.Thread(
            target=self._run_update_install_phase,
            args=(text_widget, close_btn, close_app_btn, script_path),
            daemon=True
        ).start()

    def _run_update_install_phase(self, text_widget, close_btn, close_app_btn, script_path):
        """
        Phase 2: Runs the actual update.sh script and streams output.
        Enables 'Close App' button only on success.
        """
        self._safe_log_to_update_window(text_widget, "\n--- PHASE 2: INSTALLING UPDATES ---", "info")
        
        try:
            process = subprocess.Popen(
                ['sh', script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, 
                text=True,
                encoding='utf-8',
                bufsize=1,
                start_new_session=True
            )
            
            for line in iter(process.stdout.readline, ''):
                self._safe_log_to_update_window(text_widget, line.strip(), "info")
                
            process.stdout.close()
            return_code = process.wait()
            
            if return_code == 0:
                self._safe_log_to_update_window(text_widget, "\n[SUCCESS] Update complete.", "success")
                self._safe_log_to_update_window(text_widget, "Click 'Close App (Restart)' to finish.", "success")
                
                # Enable the Close App button on success
                self.root.after(0, lambda: close_app_btn.config(state="normal"))
            else:
                self._safe_log_to_update_window(text_widget, f"\n[ERROR] Update script failed with code {return_code}", "error")

        except Exception as e:
             self._safe_log_to_update_window(text_widget, f"\n[ERROR] Failed to run update script: {e}", "error")
             
        finally:
            # Always re-enable the standard close button so user isn't stuck
            self.root.after(0, lambda: close_btn.config(state="normal"))
                 
    def get_git_commit_hash(self):
        """Attempts to get the short git commit hash of the current build."""
        try:
            # Assumes git is installed and this is running from within the repo
            # --git-dir specifies the .git folder location relative to the script
            # --work-tree specifies the root of the working copy
            
            # --- MODIFICATION: Use self.base_dir to find the .git folder ---
            # self.base_dir is src, so ../.git points to the repo root
            git_dir = os.path.join(self.base_dir, "..", ".git")
            work_tree = os.path.join(self.base_dir, "..")
            
            if not os.path.isdir(git_dir):
                # Fallback: Check if .git is in the current dir (e.g., running from root)
                git_dir = os.path.join(self.base_dir, ".git")
                work_tree = self.base_dir
                if not os.path.isdir(git_dir):
                    print("Debug: .git directory not found.")
                    return None

            result = subprocess.run(
                ['git', f'--git-dir={git_dir}', f'--work-tree={work_tree}', 'rev-parse', '--short', 'HEAD'],
                capture_output=True, text=True, check=True, encoding='utf-8'
            )
            return result.stdout.strip()
        except FileNotFoundError:
            print("Git executable not found.")
            return None
        except subprocess.CalledProcessError as e:
            print(f"Git rev-parse failed: {e.stderr}")
            return None
        except Exception as e:
            print(f"Error getting git commit: {e}")
            return None

    def _setup_menu_commands(self):
        """Builds the Settings menu, assigning commands to popup methods."""
        
        # --- 1. Configuration ---
        self.settings_menu.add_command(label="Configuration", font=self.menu_heading_font, state="disabled")
        
        self.settings_menu.add_command(label="Keg Settings", command=self._open_keg_settings_popup)
        self.settings_menu.add_command(label="Beverage Library", command=self._open_beverage_library_popup)
        self.settings_menu.add_command(label="Notification Settings", command=self._open_message_settings_popup)
        self.settings_menu.add_command(label="Flow Sensor Calibration", command=self._open_flow_calibration_popup)
        self.settings_menu.add_command(label="System Settings", command=self._open_system_settings_popup)
        
        self.settings_menu.add_separator()
        
        # --- 2. Utilities ---
        self.settings_menu.add_command(label="Utilities", font=self.menu_heading_font, state="disabled")
        self.settings_menu.add_command(label="KegLevel Workflow", command=self._open_workflow_popup)
        self.settings_menu.add_command(label="Temperature Log", command=self._open_temperature_log_popup)
        
        self.settings_menu.add_separator()
        
        # --- 3. Maintenance ---
        self.settings_menu.add_command(label="Maintenance", font=self.menu_heading_font, state="disabled")
        self.settings_menu.add_command(label="Check for Updates", command=self._check_for_updates)
        self.settings_menu.add_command(label="Reset to Defaults", command=self._open_reset_to_defaults_popup)
        self.settings_menu.add_command(label="Uninstall App", command=self._open_uninstall_app_popup)
        
        self.settings_menu.add_separator()
        
        # --- 4. App Info ---
        self.settings_menu.add_command(label="App Info", font=self.menu_heading_font, state="disabled")
        self.settings_menu.add_command(label="Wiring Diagram", command=self._open_wiring_diagram_popup)
        
        self.settings_menu.add_command(label="Help", command=self._open_help_popup)
        
        # RENAMED: Support this App -> EULA
        self.settings_menu.add_command(label="EULA", command=lambda: self._open_eula_popup(is_launch=False))
        self.settings_menu.add_command(label="About...", command=self._open_about_popup)

    def _open_about_popup(self):
        try:
            APP_REVISION = self.__class__.__bases__[0].APP_REVISION
        except:
             APP_REVISION = "Unknown"
             
        popup = tk.Toplevel(self.root)
        popup.title("About KegLevel Monitor")
        # Increased height slightly to accommodate the support info
        self._center_popup(popup, 750, 580)
        
        popup.transient(self.root)
        popup.grab_set()

        frame = ttk.Frame(popup, padding="15")
        frame.pack(expand=True, fill="both")

        # --- Header Section ---
        ttk.Label(frame, text="KegLevel Monitor", font=('TkDefaultFont', 14, 'bold')).pack(pady=(0, 10))

        copyright_text = (
            "KegLevel Monitor(c) and KegLevel Workflow(c) names, texts, UI/UX "
            "and program code are copyrighted. This material and all components of this program are protected by "
            "copyright law. Unauthorized use, duplication, or distribution is "
            "strictly prohibited."
        )
        ttk.Label(frame, text=copyright_text, wraplength=700, justify=tk.LEFT).pack(anchor='w', pady=(0, 5))
        
        version_display = self.app_version_string if self.app_version_string else 'Unknown'
        commit_hash = self.get_git_commit_hash()
        
        if commit_hash:
            version_text = f"Version: {version_display} (Commit: {commit_hash})"
        else:
            version_text = f"Version: {version_display}"
                       
        ttk.Label(frame, text=version_text, font=('TkDefaultFont', 10, 'italic')).pack(anchor='w', pady=(0, 15))
        
        ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=5)

        # --- MOVED: Support / Donation Section ---
        self._load_support_image()
        
        support_frame = ttk.Frame(frame)
        support_frame.pack(fill="x", pady=10)
        
        # Left side: Text
        support_text_container = ttk.Frame(support_frame)
        support_text_container.pack(side="left", fill="both", expand=True, padx=(0, 15))
        
        support_header = "Support this Project"
        ttk.Label(support_text_container, text=support_header, font=('TkDefaultFont', 11, 'bold')).pack(anchor='w', pady=(0, 5))
        
        support_msg = (
            "This App took hundreds of hours to develop, test, and optimize. "
            "Please consider supporting this App with a donation so continuous improvements "
            "can be made.\n\n"
            "If you wish to receive customer support via email, please make a reasonable "
            "donation. Customer support requests without a donation may not be considered."
        )
        ttk.Label(support_text_container, text=support_msg, wraplength=480, justify="left").pack(anchor='w')

        # Right side: QR Code
        if self.support_qr_image:
            qr_label = ttk.Label(support_frame, image=self.support_qr_image, relief="groove", borderwidth=1)
            qr_label.pack(side="right", anchor="n")
        else:
            ttk.Label(support_frame, text="[QR Code Missing]", relief="sunken", padding=20).pack(side="right")

        # --- Footer Section ---
        # Function to open the link in a browser
        def open_flaticon_link(event):
            try:
                import webbrowser
                webbrowser.open_new("https://www.flaticon.com/free-icons/update")
            except Exception as e:
                messagebox.showerror("Link Error", f"Could not open link: {e}", parent=popup)

        link_label = ttk.Label(
            popup, 
            text="Beer Keg and Update icons created by Pixel Perfect - Flaticon", 
            foreground="blue", 
            cursor="hand2", 
            font=('TkDefaultFont', 8, 'italic', 'underline'), 
            wraplength=700, 
            justify=tk.LEFT
        )
        # Pack at bottom
        link_label.pack(fill="x", side="bottom", pady=5, padx=15) 
        link_label.bind("<Button-1>", open_flaticon_link)
        
        buttons_frame = ttk.Frame(popup, padding=(10, 5))
        buttons_frame.pack(fill="x", side="bottom") 
        
        ttk.Button(buttons_frame, text="Close", command=popup.destroy, width=10).pack(side="right", pady=5)
        
        ttk.Button(buttons_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("about")).pack(side="right", padx=5, pady=5)

    def _open_eula_popup(self, is_launch=False):
        """
        Displays the EULA popup.
        Renamed from _open_support_popup.
        """
        popup = tk.Toplevel(self.root)
        popup.withdraw()
        
        popup.title("End User License Agreement (EULA)")
        
        # --- 1. Reset UI Variables ---
        system_settings = self.settings_manager.get_system_settings()
        
        has_agreed = system_settings.get("eula_agreed", False)
        if has_agreed:
            self.eula_agreement_var.set(1) 
        else:
            self.eula_agreement_var.set(0) 
        
        # --- 2. Build UI ---
        main_frame = ttk.Frame(popup, padding="15")
        main_frame.pack(fill="both", expand=True)

        # --- EULA Text Section ---
        eula_frame = ttk.LabelFrame(main_frame, text="Terms and Conditions", padding=10)
        eula_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        eula_text_widget = scrolledtext.ScrolledText(eula_frame, height=10, wrap="word", relief="flat")
        eula_text_widget.pack(fill="both", expand=True)
        
        try:
            bold_font = tkfont.nametofont("TkDefaultFont").copy()
            bold_font.config(weight="bold")
            eula_text_widget.tag_configure("bold", font=bold_font)
        except:
            eula_text_widget.tag_configure("bold", font=('TkDefaultFont', 10, 'bold'))
        
        eula_text_widget.config(state="normal")
        eula_text_widget.insert("end", "End User License Agreement (EULA)\n\n", "bold")
        eula_text_widget.insert("end", "1. Scope of Agreement\n", "bold")
        eula_text_widget.insert("end", (
            "This Agreement applies to the \"Keg Level Monitor\" software (hereafter \"this app\"). "
            "\"This app\" includes the main software program and all related software and hardware components.\n\n"
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
        eula_text_widget.config(state="disabled")

        # --- Agreement Section ---
        agreement_frame = ttk.Frame(main_frame)
        agreement_frame.pack(fill="x")

        # Radio 1: Agree
        agree_rb = ttk.Radiobutton(agreement_frame, 
                                   text="I agree with the above End User License Agreement", 
                                   variable=self.eula_agreement_var, value=1)
        agree_rb.pack(anchor="w")
        agree_note = ttk.Label(agreement_frame, text="You may proceed to the app after clicking Confirm",
                               font=('TkDefaultFont', 8, 'italic'))
        agree_note.pack(anchor="w", padx=(20, 0), pady=(0, 5))

        # Radio 2: Disagree
        disagree_rb = ttk.Radiobutton(agreement_frame, 
                                     text="I do not agree with the above End User License Agreement", 
                                     variable=self.eula_agreement_var, value=2)
        disagree_rb.pack(anchor="w")
        disagree_note = ttk.Label(agreement_frame, text="The application will exit if you select this option",
                                 font=('TkDefaultFont', 8, 'italic'))
        disagree_note.pack(anchor="w", padx=(20, 0), pady=(0, 10))

        # --- Bottom Section ---
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill="x", side="bottom", pady=(10, 0))

        close_btn = ttk.Button(bottom_frame, text="Confirm & Close", 
                               command=lambda: self._handle_eula_popup_close(popup))
        close_btn.pack(side="right")
        
        # Help Button
        ttk.Button(bottom_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("support")).pack(side="right", padx=5)

        # --- Finalize Popup ---
        popup_width = 700
        popup_height = 500
        self._center_popup(popup, popup_width, popup_height)
        popup.resizable(False, False)
        
        # Modal logic for launch
        if is_launch:
            popup.protocol("WM_DELETE_WINDOW", lambda: self._handle_eula_popup_close(popup))
            popup.transient(self.root)
            popup.lift()
            popup.focus_force()
            popup.grab_set()
            try:
                self.root.wait_window(popup)
            except tk.TclError:
                pass
        else:
            popup.transient(self.root)
            popup.grab_set()

    def _handle_eula_popup_close(self, popup):
        """Handles the logic for the 'Close' button on the EULA popup."""
        
        if not popup.winfo_exists():
            return
        
        agreement_state = self.eula_agreement_var.get()
        
        # Get actual settings
        try:
            system_settings = self.settings_manager.settings['system_settings']
        except KeyError:
            print("Error: 'system_settings' key missing from settings manager.")
            system_settings = self.settings_manager._get_default_system_settings()
            
        settings_changed = False

        if agreement_state == 1: # "I agree"
            if not system_settings.get("eula_agreed"):
                system_settings["eula_agreed"] = True
                settings_changed = True
            
            # Ensure legacy flag is off
            if system_settings.get("show_eula_on_launch"):
                system_settings["show_eula_on_launch"] = False
                settings_changed = True
            
            if settings_changed:
                self.settings_manager._save_all_settings()
            
            popup.destroy()
            return

        elif agreement_state == 2: # "I do not agree"
            if system_settings.get("eula_agreed"):
                system_settings["eula_agreed"] = False
                settings_changed = True
            
            if settings_changed:
                self.settings_manager._save_all_settings()
            
            popup.destroy()
            self._show_disagree_dialog()
            return
            
        else: # State is 0 (neither selected)
            messagebox.showwarning("Agreement Required", 
                                   "You must select 'I agree' or 'I do not agree' to proceed.", 
                                   parent=popup)
            return
            
    def _add_changelog_section(self, parent_frame, popup_window):
        """Adds a scrollable changelog text area to the About popup."""
        
        ttk.Label(parent_frame, text="Change Log", font=('TkDefaultFont', 10, 'bold')).pack(anchor='w', pady=(5, 5))

        text_frame = ttk.Frame(parent_frame); text_frame.pack(fill="both", expand=True)
        text_frame.grid_columnconfigure(0, weight=1); text_frame.grid_rowconfigure(0, weight=1)

        changelog_text = tk.Text(text_frame, height=12, wrap='word', state='disabled', relief='sunken', borderwidth=1)
        changelog_text.grid(row=0, column=0, sticky="nsew")

        v_scrollbar = ttk.Scrollbar(text_frame, orient="vertical", command=changelog_text.yview)
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        changelog_text.config(yscrollcommand=v_scrollbar.set)

        # --- REFACTOR: Look in the 'assets' subdirectory ---
        changelog_path = os.path.join(self.base_dir, "assets", "changelog.txt")
        # --- END REFACTOR ---
        log_content = "Changelog file not found."
        
        try:
            with open(changelog_path, 'r', encoding='utf-8') as f:
                log_content = f.read()
        except FileNotFoundError:
            pass
        except Exception as e:
            log_content = f"Error loading changelog: {e}"

        changelog_text.config(state='normal')
        changelog_text.insert(tk.END, log_content)
        changelog_text.config(state='disabled')
        
    def _open_beverage_library_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Beverage Library"); popup.geometry("800x480"); popup.transient(self.root); popup.grab_set()
        main_frame = ttk.Frame(popup, padding="10"); main_frame.pack(expand=True, fill="both")
        
        canvas = tk.Canvas(main_frame, borderwidth=0)
        v_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        v_scrollbar.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=v_scrollbar.set)
        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=800) 

        def on_frame_configure(event): canvas.configure(scrollregion=canvas.bbox("all"))
        scroll_frame.bind("<Configure>", on_frame_configure)
        def on_canvas_resize(event): canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', on_canvas_resize)

        self.beverage_popup_vars = []
        beverage_list = self.settings_manager.get_beverage_library().get('beverages', [])
        scroll_frame.grid_columnconfigure(0, weight=1); scroll_frame.grid_columnconfigure(1, weight=0); scroll_frame.grid_columnconfigure(2, weight=0)

        header_frame = ttk.Frame(scroll_frame); header_frame.grid(row=0, column=0, columnspan=2, sticky='ew', padx=5, pady=5)
        header_frame.grid_columnconfigure(0, weight=1); header_frame.grid_columnconfigure(1, weight=0); header_frame.grid_columnconfigure(2, weight=0)
        ttk.Label(header_frame, text="Beverage Name", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, padx=5, sticky='w')
        ttk.Label(header_frame, text="Actions", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=1, columnspan=2, sticky='w', padx=(20, 5))

        BG_EVEN = '#FFFFFF'; BG_ODD = '#F5F5F5' 

        for i in range(len(beverage_list)):
            beverage = beverage_list[i]; row = i + 1; bg_color = BG_ODD if i % 2 else BG_EVEN
            row_frame = tk.Frame(scroll_frame, bg=bg_color, relief='flat', bd=0); row_frame.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(1, 0))
            row_frame.grid_columnconfigure(0, weight=1); row_frame.grid_columnconfigure(1, weight=0); row_frame.grid_columnconfigure(2, weight=0)
            
            name_label_text = tk.StringVar(value=beverage.get('name', ''))
            ttk.Label(row_frame, textvariable=name_label_text, anchor='w', background=bg_color, padding=(5, 5)).grid(row=0, column=0, sticky='w')
            self.beverage_popup_vars.append(name_label_text)
            
            ttk.Button(row_frame, text="Edit", width=8, 
                       command=lambda b=beverage, p=popup: self._open_beverage_edit_popup(b, p)).grid(row=0, column=1, padx=(10, 5), pady=2, sticky='e')

            ttk.Button(row_frame, text="Delete", width=8, style="TButton", 
                       command=lambda b_id=beverage.get('id'), b_name=beverage.get('name'), 
                       p=popup: self._delete_beverage(b_id, b_name, p)).grid(row=0, column=2, padx=(0, 5), pady=2, sticky='e')

        footer_frame = ttk.Frame(popup, padding="10"); 
        footer_frame.pack(fill="x", side="bottom", pady=(10, 0))
        
        ttk.Button(footer_frame, text="Add New Beverage", 
                   command=lambda p=popup: self._open_beverage_edit_popup(None, p)).pack(side="left", padx=5)

        ttk.Button(footer_frame, text="Close", 
                   command=lambda p=popup: self._close_and_sort_beverage_library_popup(p)).pack(side="right", padx=5)

        # NEW Help Button
        ttk.Button(footer_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("beverage_library")).pack(side="right", padx=5)

        center_import_frame = ttk.Frame(footer_frame)
        center_import_frame.pack(expand=True, fill="x", padx=10) 

        available_libraries = self.settings_manager.get_available_addon_libraries()
        library_options = ["Select Library"] + available_libraries
        
        self.bjcp_import_var = tk.StringVar(value=library_options[0]) 
        
        import_dropdown = ttk.Combobox(center_import_frame, textvariable=self.bjcp_import_var, 
                                       values=library_options, state="readonly", width=20)
        import_dropdown.pack(side="left", padx=(0, 5), anchor="center")
        
        ttk.Button(center_import_frame, text="Import", width=8, 
                   command=lambda p=popup: self._validate_and_open_dialog('import', p, self.bjcp_import_var.get())).pack(side="left", padx=(0, 10), anchor="center")

        ttk.Button(center_import_frame, text="Delete", width=8, 
                   command=lambda p=popup: self._validate_and_open_dialog('delete', p, self.bjcp_import_var.get())).pack(side="left", padx=(0, 5), anchor="center")
        
        scroll_frame.update_idletasks()
        
    def _close_and_sort_beverage_library_popup(self, popup_window):
        beverage_library = self.settings_manager.get_beverage_library()
        beverage_list = beverage_library.get('beverages', [])
        
        try:
            sorted_list = sorted(beverage_list, key=lambda b: b.get('name', '').lower())
        except Exception as e:
            messagebox.showerror("Sort Error", f"An error occurred during automatic sorting of the library. {e}", parent=popup_window)
            popup_window.destroy(); return

        self.settings_manager.save_beverage_library(sorted_list)
        print("UIManager: Beverage library automatically sorted and saved upon close.")
        
        self._populate_beverage_dropdowns()
        self._refresh_beverage_metadata()
        
        if hasattr(self, 'workflow_app') and self.workflow_app and self.workflow_app.popup.winfo_exists():
             self.workflow_app._refresh_all_columns()

        popup_window.destroy()

    def _open_beverage_edit_popup(self, beverage_data=None, parent_popup=None):
        is_new = beverage_data is None; popup = tk.Toplevel(self.root)
        beverage_name = beverage_data.get('name', 'Beverage') if beverage_data else 'Beverage'
        popup.title("Add New Beverage" if is_new else f"Edit {beverage_name}"); popup.geometry("600x450")
        popup.transient(self.root); popup.grab_set()

        form_frame = ttk.Frame(popup, padding="15"); form_frame.pack(expand=True, fill="both")
        
        # NEW: Default includes srm
        default_data = {
            'id': str(uuid.uuid4()), 'name': '', 'bjcp': '', 'abv': '', 'ibu': None, 'srm': None, 'description': ''
        }
        data = beverage_data if beverage_data else default_data

        temp_vars = {
            'id': tk.StringVar(value=data.get('id')),
            'name': tk.StringVar(value=data.get('name')),
            'bjcp': tk.StringVar(value=data.get('bjcp')), 
            'abv': tk.StringVar(value=data.get('abv')),
            'ibu': tk.StringVar(value=str(data.get('ibu', '')) if data.get('ibu') is not None else ''),
            # NEW: SRM Variable
            'srm': tk.StringVar(value=str(data.get('srm', '')) if data.get('srm') is not None else ''),
            'description': tk.StringVar(value=data.get('description'))
        }

        row_idx = tk.IntVar(value=0)

        def add_field(parent, label_text, var, width, is_text=False, max_len=None, row=None):
            ttk.Label(parent, text=label_text, width=15, anchor="w").grid(row=row, column=0, padx=5, pady=5 if not is_text else (10,0), sticky='w')
            if is_text:
                text_widget = tk.Text(parent, height=5, width=width, wrap=tk.WORD)
                text_widget.insert(tk.END, var.get())
                text_widget.grid(row=row, column=1, sticky='nsew', padx=5, pady=5)
                return text_widget 
            else:
                entry = ttk.Entry(parent, textvariable=var, width=width)
                entry.grid(row=row, column=1, sticky='ew', padx=5, pady=5)
                if max_len:
                    ttk.Label(parent, text=f"({max_len} chars)", font=('TkDefaultFont', 8, 'italic')).grid(row=row, column=2, sticky='w', padx=2)
                return entry 

        form_frame.grid_columnconfigure(0, weight=0); form_frame.grid_columnconfigure(1, weight=1); form_frame.grid_columnconfigure(2, weight=0)
        
        # --- NEW: Capture the Name Entry widget ---
        name_entry = add_field(form_frame, "Beverage Name:", temp_vars['name'], 25, row=row_idx.get(), max_len=35); row_idx.set(row_idx.get() + 1)
        
        add_field(form_frame, "BJCP/Style Name:", temp_vars['bjcp'], 25, row=row_idx.get()); row_idx.set(row_idx.get() + 1)
        
        # Compact Row for ABV / IBU / SRM
        stats_frame = ttk.Frame(form_frame)
        stats_frame.grid(row=row_idx.get(), column=0, columnspan=3, sticky='w')
        
        ttk.Label(stats_frame, text="ABV:").pack(side='left', padx=(5, 5))
        ttk.Entry(stats_frame, textvariable=temp_vars['abv'], width=6).pack(side='left')
        
        ttk.Label(stats_frame, text="IBU:").pack(side='left', padx=(15, 5))
        ttk.Entry(stats_frame, textvariable=temp_vars['ibu'], width=6).pack(side='left')
        
        # NEW: SRM Field
        ttk.Label(stats_frame, text="SRM:").pack(side='left', padx=(15, 5))
        ttk.Entry(stats_frame, textvariable=temp_vars['srm'], width=6).pack(side='left')
        ttk.Label(stats_frame, text="(Color 0-40)").pack(side='left', padx=(5, 0))
        
        row_idx.set(row_idx.get() + 1)
        
        description_row = row_idx.get()
        description_text_widget = add_field(form_frame, "Description:", temp_vars['description'], 40, is_text=True, max_len=255, row=description_row)
        form_frame.grid_rowconfigure(description_row, weight=1); row_idx.set(row_idx.get() + 1)

        # Footer Buttons
        btns_frame = ttk.Frame(popup, padding="10"); btns_frame.pack(fill="x", side="bottom")
        
        ttk.Button(btns_frame, text="Save", command=lambda p=popup: self._save_beverage(temp_vars, description_text_widget, is_new, p, parent_popup)).pack(side="right", padx=5)
        ttk.Button(btns_frame, text="Cancel", command=popup.destroy).pack(side="right", padx=5)
        
        # NEW Help Button
        ttk.Button(btns_frame, text="Help", width=8, 
                   command=lambda: self._open_help_popup("beverage_library")).pack(side="right", padx=5)

        popup.update_idletasks()
        
        # --- NEW: Set focus to Name field ---
        if name_entry:
            name_entry.focus_set()

    def _save_beverage(self, temp_vars, description_text_widget, is_new, popup_window, parent_popup):
        try:
            name = temp_vars['name'].get().strip(); 
            ibu_str = temp_vars['ibu'].get().strip(); 
            abv = temp_vars['abv'].get().strip()
            srm_str = temp_vars['srm'].get().strip() 
            bjcp_style = temp_vars['bjcp'].get().strip(); 
            description = description_text_widget.get("1.0", tk.END).strip()
            
            if not name: messagebox.showerror("Input Error", "Beverage Name cannot be empty.", parent=popup_window); return
            if len(name) > 35: messagebox.showerror("Input Error", "Beverage Name is limited to 35 characters.", parent=popup_window); return
            if len(bjcp_style) > 35: messagebox.showerror("Input Error", "BJCP/Style Name is limited to 35 characters.", parent=popup_window); return
            if not (0 <= len(abv) <= 5): messagebox.showerror("Input Error", "ABV is limited to 5 characters (e.g., 5.5).", parent=popup_window); return
            
            ibu = None
            if ibu_str:
                try:
                    ibu = int(ibu_str)
                    if not (0 <= ibu <= 200): raise ValueError 
                except ValueError:
                    messagebox.showerror("Input Error", "IBU must be blank or a whole number.", parent=popup_window); return

            # VALIDATE SRM (FIXED: Int only, 0-40)
            srm = None
            if srm_str:
                try:
                    srm = int(srm_str) # Changed from float to int
                    if not (0 <= srm <= 40): raise ValueError
                except ValueError:
                    # Updated error message to reflect the correct range
                    messagebox.showerror("Input Error", "SRM must be blank or a whole number between 0 and 40.", parent=popup_window); return
            
            new_data = {
                "id": temp_vars['id'].get(), "name": name, "bjcp": bjcp_style, 
                "abv": abv, "ibu": ibu, "srm": srm, "description": description 
            }
            beverage_list = self.settings_manager.get_beverage_library().get('beverages', [])
            
            if is_new: beverage_list.append(new_data)
            else:
                found = False
                for i, b in enumerate(beverage_list):
                    if b.get('id') == new_data['id']: 
                        if b.get('source_library'):
                            new_data['source_library'] = b['source_library']
                        beverage_list[i] = new_data; 
                        found = True; 
                        break
                if not found: messagebox.showerror("Save Error", "Could could not find the original beverage to update.", parent=popup_window); return

            sorted_list = sorted(beverage_list, key=lambda b: b.get('name', '').lower())
            self.settings_manager.save_beverage_library(sorted_list)
            
            self._populate_beverage_dropdowns()
            self._refresh_beverage_metadata()
            
            if hasattr(self, 'workflow_app') and self.workflow_app and self.workflow_app.popup.winfo_exists(): self.workflow_app._refresh_all_columns()
                 
            popup_window.destroy()
            if parent_popup and parent_popup.winfo_exists():
                 parent_popup.destroy() 
                 self._open_beverage_library_popup()
            
            print(f"UIManager: Beverage '{name}' saved and sorted successfully.")

        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred while saving the beverage: {e}", parent=popup_window)
            
    def _delete_beverage(self, beverage_id, beverage_name, parent_popup):
        if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the beverage '{beverage_name}'? This cannot be undone.", parent=parent_popup): return
            
        beverage_list = self.settings_manager.get_beverage_library().get('beverages', [])
        new_list = [b for b in beverage_list if b.get('id') != beverage_id]
        assignments = self.settings_manager.get_sensor_beverage_assignments()
        
        first_beverage_id = new_list[0]['id'] if new_list else self.settings_manager._get_default_beverage_library().get('beverages')[0]['id']
        
        needs_assignment_update = False
        for i in range(len(assignments)):
            if assignments[i] == beverage_id:
                assignments[i] = first_beverage_id
                needs_assignment_update = True
        
        if needs_assignment_update:
            for i in range(len(assignments)): self.settings_manager.save_sensor_beverage_assignment(i, assignments[i])
            print("UIManager: Re-assigned taps after deleting a beverage.")
            
        sorted_list = sorted(new_list, key=lambda b: b.get('name', '').lower())
        self.settings_manager.save_beverage_library(sorted_list)

        self._populate_beverage_dropdowns()
        self._refresh_beverage_metadata()

        if hasattr(self, 'workflow_app') and self.workflow_app and self.workflow_app.popup.winfo_exists(): self.workflow_app._refresh_all_columns()
             
        parent_popup.destroy() 
        if self.settings_manager.get_beverage_library().get('beverages'): self._open_beverage_library_popup()
        else: messagebox.showinfo("Library Empty", "The Beverage Library is now empty.", parent=self.root)

    
    # --- NEW: Import Dialog Logic (Unchanged) ---
    def _open_bjcp_import_dialog(self, parent_popup, addon_name):
        addon_list = self.settings_manager.load_addon_library(addon_name)
        if addon_list is None:
            messagebox.showerror("Import Error", f"Could not load the {addon_name} file for pre-check.", parent=parent_popup)
            return

        current_beverages = self.settings_manager.get_beverage_library().get('beverages', [])
        current_ids = {b['id'] for b in current_beverages if 'id' in b}
        entries_to_import = [b for b in addon_list if b.get('id') not in current_ids]
        import_count = len(entries_to_import)

        popup = tk.Toplevel(self.root); popup.title(f"Confirm Import: {addon_name}"); popup.geometry("450x200"); popup.transient(self.root); popup.grab_set()
        
        frame = ttk.Frame(popup, padding="15"); frame.pack(expand=True, fill="both")
        
        message_text = (
            "The library contains {import_count} entries. Once imported, the library entries can be "
            "individually edited or deleted. The library entries may be deleted all at once "
            "with the Delete function, but any library entries that have been edited will not "
            "be deleted."
        ).format(import_count=import_count) 
        ttk.Label(frame, text=message_text, wraplength=400, justify=tk.LEFT).pack(pady=(0, 20))
        
        buttons_frame = ttk.Frame(popup, padding="10"); buttons_frame.pack(fill="x", side="bottom")
        
        ttk.Button(buttons_frame, text="Cancel", command=popup.destroy).pack(side="right", padx=5)
        ttk.Button(buttons_frame, text="Continue", 
                   command=lambda: self._execute_bjcp_import(addon_name, popup, parent_popup)).pack(side="right")

    def _execute_bjcp_import(self, addon_name, dialog_popup, library_popup):
        success, message, new_count = self.settings_manager.import_beverages_from_addon(addon_name)
        
        dialog_popup.destroy()
        library_popup.destroy()

        if success:
            messagebox.showinfo("Import Successful", f"{message}", parent=self.root)
            self._open_beverage_library_popup()
            self._populate_beverage_dropdowns()
            self._refresh_beverage_metadata()
            if hasattr(self, 'workflow_app') and self.workflow_app and self.workflow_app.popup.winfo_exists():
                 self.workflow_app._refresh_all_columns()
        else:
            messagebox.showerror("Import Failed", message, parent=self.root)

    # --- NEW: Delete Dialog Logic (Unchanged) ---
    def _open_bjcp_delete_dialog(self, parent_popup, addon_name):
        popup = tk.Toplevel(self.root); popup.title(f"Confirm Delete: {addon_name}"); popup.geometry("450x200"); popup.transient(self.root); popup.grab_set()
        
        frame = ttk.Frame(popup, padding="15"); frame.pack(expand=True, fill="both")
        
        message_text = (
            "This action attempts to remove all original entries from the imported library. Any "
            "imported library entries that have been edited will not be deleted. Any taps assigned "
            "to these entries will be reassigned to the first beverage in the list of beverages."
        )
        ttk.Label(frame, text=message_text, wraplength=400, justify=tk.LEFT).pack(pady=(0, 20))
        
        buttons_frame = ttk.Frame(popup, padding="10"); buttons_frame.pack(fill="x", side="bottom")
        
        ttk.Button(buttons_frame, text="Cancel", command=popup.destroy).pack(side="right", padx=5)
        ttk.Button(buttons_frame, text="Continue", 
                   command=lambda: self._execute_bjcp_delete(addon_name, popup, parent_popup)).pack(side="right")

    def _execute_bjcp_delete(self, addon_name, dialog_popup, library_popup):
        success, message, total_original_count, deleted_count = self.settings_manager.delete_beverages_from_addon(addon_name)
        
        dialog_popup.destroy()
        library_popup.destroy()
        
        if success:
            messagebox.showinfo("Delete Successful", 
                                f"Successfully deleted {deleted_count} of {total_original_count} original entries from {addon_name}. Taps were reassigned.", 
                                parent=self.root)
            self._open_beverage_library_popup()
            self._populate_beverage_dropdowns()
            self._refresh_beverage_metadata()
            if hasattr(self, 'workflow_app') and self.workflow_app and self.workflow_app.popup.winfo_exists():
                 self.workflow_app._refresh_all_columns()
        else:
            messagebox.showerror("Import Failed", message, parent=self.root)

    def _validate_and_open_dialog(self, action, parent_popup, selected_library_name):
        """Checks if a valid library is selected before opening the import/delete dialog."""
        if selected_library_name == "Select Library" or not selected_library_name:
            messagebox.showerror("Selection Error", "Please select a valid library to proceed.", parent=parent_popup)
            return

        if action == 'import':
            self._open_bjcp_import_dialog(parent_popup, selected_library_name)
        elif action == 'delete':
            self._open_bjcp_delete_dialog(parent_popup, selected_library_name)

    # --- Keg Settings Helper Methods (REPLACED/MODIFIED) ---
    
    # --- FIX: Added 'row' parameter to the internal helper function signature ---
    def _add_link_field(self, parent, label_text, var, unit, row, readonly=False):
        """Helper to create and place linked fields for the edit popup."""
        ttk.Label(parent, text=label_text, width=25, anchor="w").grid(row=row, column=0, padx=5, pady=5, sticky='w')
        entry = ttk.Entry(parent, textvariable=var, width=15, state=('readonly' if readonly else 'normal'))
        entry.grid(row=row, column=1, sticky='ew', padx=5, pady=5)
        if unit: ttk.Label(parent, text=unit).grid(row=row, column=2, sticky='w', padx=2)
        return entry

    def _keg_edit_link_weight_to_volume(self, temp_vars, source_var):
        """
        Performs the linked calculation between weight and volume in the edit popup.
        
        FIX: The trace handler is ONLY attached to tare_weight_kg and total_weight_kg.
        Maximum Full Volume should NOT trigger this calculation.
        """
        
        # Determine current units for parsing inputs
        display_units = self.settings_manager.get_display_units()
        weight_conversion = 1.0 if display_units == "metric" else KG_TO_LB
        volume_conversion = 1.0 if display_units == "metric" else LITERS_TO_GALLONS

        # Temporarily remove trace to prevent infinite loop
        # ONLY remove traces for the variables that trigger the calculation.
        for var_name in ['tare_weight_kg', 'total_weight_kg']:
            trace_id = getattr(temp_vars[var_name], '_trace_id', None)
            if trace_id: 
                 try: temp_vars[var_name].trace_remove("write", trace_id)
                 except tk.TclError: pass
        
        try:
            # Read the current displayed value from the entry widget
            # Note: The helper function binds FocusOut to update the underlying 'kg' variable, 
            # so we read the stored KG value here, which is more reliable than reading the entry widget text.
            empty_kg = float(temp_vars['tare_weight_kg'].get())
            total_kg = float(temp_vars['total_weight_kg'].get())
        except ValueError: 
            # If weight entries are invalid, show error in volume field
            temp_vars['starting_volume_display'].set("--.--")
            self._re_add_keg_edit_traces(temp_vars); return
        
        if total_kg >= empty_kg and empty_kg >= 0 and total_kg >= 0:
             # Calculate volume in liters (stored unit)
             new_vol_liters = self.settings_manager._calculate_volume_from_weight(total_kg, empty_kg)
             
             # Convert liters to displayed volume unit for setting the StringVar
             new_vol_display = new_vol_liters * volume_conversion
             temp_vars['starting_volume_display'].set(f"{new_vol_display:.2f}")
        else:
             temp_vars['starting_volume_display'].set("--.--")

        self._re_add_keg_edit_traces(temp_vars)

    def _re_add_keg_edit_traces(self, temp_vars):
        """
        Re-adds the traces after a calculated change in the edit popup.
        
        FIX: ONLY adds traces to the weight fields.
        """
        
        # We trace the underlying KG variable's write event, but the handler reads the actual Entry text
        def trace_handler(var_name):
            return lambda n, i, m, r=temp_vars: self._keg_edit_link_weight_to_volume(r, var_name)
            
        # ONLY trace the weight-related variables
        temp_vars['tare_weight_kg']._trace_id = temp_vars['tare_weight_kg'].trace_add("write", trace_handler('tare_weight_kg'))
        temp_vars['total_weight_kg']._trace_id = temp_vars['total_weight_kg'].trace_add("write", trace_handler('total_weight_kg'))

    # --- Keg Settings Popup Logic (RESTRUCTURED TO MIRROR BEVERAGE LAYOUT) ---

    def _open_keg_settings_popup(self):
        # UI mirrors the Beverage Library for consistent behavior
        popup = tk.Toplevel(self.root)
        popup.title("Keg Settings")
        
        # FIX: Use center_popup to ensure title bar/X is visible
        self._center_popup(popup, 700, 510)
        
        popup.transient(self.root)
        popup.grab_set() 
        
        main_frame = ttk.Frame(popup, padding="10"); main_frame.pack(expand=True, fill="both")
        
        canvas = tk.Canvas(main_frame, borderwidth=0)
        v_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        v_scrollbar.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=v_scrollbar.set)
        
        # Adjust canvas window width to fit the geometry
        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=680) 

        def on_frame_configure(event): canvas.configure(scrollregion=canvas.bbox("all"))
        scroll_frame.bind("<Configure>", on_frame_configure)
        def on_canvas_resize(event): canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', on_canvas_resize)

        # Store scroll_frame on the popup object so we can access it later for refreshing
        popup.scroll_frame = scroll_frame

        # Initial Population of the list
        self._populate_keg_settings_list(popup)
        
        # --- FIX: Restore Footer Buttons ---
        footer_frame = ttk.Frame(popup, padding="10")
        footer_frame.pack(fill="x", side="bottom")
        
        ttk.Button(footer_frame, text="Add New Keg", 
                   command=lambda p=popup: self._open_keg_edit_popup(None, p)).pack(side="left", padx=5)

        ttk.Button(footer_frame, text="Close", command=popup.destroy).pack(side="right", padx=5)
        
        ttk.Button(footer_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("keg_settings")).pack(side="right", padx=5)
        # -------------------------------
        
        popup.update_idletasks()

    def _populate_keg_settings_list(self, popup_window):
        """Helper to rebuild the keg list inside the existing popup window."""
        scroll_frame = getattr(popup_window, 'scroll_frame', None)
        if not scroll_frame: return

        # Clear existing rows/widgets in the scroll frame
        for widget in scroll_frame.winfo_children():
            widget.destroy()

        self.keg_settings_popup_vars = []
        
        # Fetch Data
        keg_list_unsorted = self.settings_manager.get_keg_definitions()
        keg_list = sorted(keg_list_unsorted, key=lambda k: k.get('title', '').lower())
        beverage_lib = self.settings_manager.get_beverage_library().get('beverages', [])
        beverage_map = {b['id']: b['name'] for b in beverage_lib}

        # --- Helper to force alignment across separate row frames ---
        def configure_grid_cols(container):
            container.grid_columnconfigure(0, weight=1, minsize=220) # Title
            container.grid_columnconfigure(1, weight=1, minsize=220) # Contents
            container.grid_columnconfigure(2, weight=0, minsize=80)  # Edit
            container.grid_columnconfigure(3, weight=0, minsize=80)  # Delete

        # --- Header Row ---
        header_frame = ttk.Frame(scroll_frame)
        header_frame.grid(row=0, column=0, columnspan=4, sticky='ew', padx=5, pady=5)
        configure_grid_cols(header_frame)
        
        ttk.Label(header_frame, text="Keg Title", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, padx=5, sticky='w')
        
        # Contents Header (Left-Justified with padding to prevent crowding)
        contents_header = ttk.Label(header_frame, text="Contents (Beverage)", font=('TkDefaultFont', 10, 'bold'))
        contents_header.grid(row=0, column=1, padx=(5, 30), sticky='w') 
        
        ttk.Label(header_frame, text="Actions", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=2, columnspan=2, sticky='e', padx=(5, 25))

        BG_EVEN = '#FFFFFF'; BG_ODD = '#F5F5F5' 

        for i in range(len(keg_list)):
            keg = keg_list[i]; row = i + 1; bg_color = BG_ODD if i % 2 else BG_EVEN
            
            row_frame = tk.Frame(scroll_frame, bg=bg_color, relief='flat', bd=0)
            row_frame.grid(row=row, column=0, columnspan=4, sticky='ew', pady=(1, 0))
            configure_grid_cols(row_frame)
            
            # Col 0: Keg Title
            title_label_text = tk.StringVar(value=keg.get('title', ''))
            ttk.Label(row_frame, textvariable=title_label_text, anchor='w', background=bg_color, 
                      padding=(5, 5)).grid(row=0, column=0, sticky='ew', padx=5)
            self.keg_settings_popup_vars.append(title_label_text)
            
            # Col 1: Contents (Beverage)
            bev_id = keg.get('beverage_id', UNASSIGNED_BEVERAGE_ID)
            bev_name = beverage_map.get(bev_id, "")
            if not bev_name and bev_id != UNASSIGNED_BEVERAGE_ID: bev_name = "Unknown"
            elif not bev_name: bev_name = "" 
            
            ttk.Label(row_frame, text=bev_name, anchor='w', background=bg_color,
                      padding=(5, 5)).grid(row=0, column=1, sticky='ew', padx=(5, 30))

            # Col 2: Edit Button
            ttk.Button(row_frame, text="Edit", width=8, 
                       command=lambda k=keg.copy(), p=popup_window: self._open_keg_edit_popup(k, p)).grid(row=0, column=2, padx=(5, 5), pady=2, sticky='e')

            # Col 3: Delete Button
            ttk.Button(row_frame, text="Delete", width=8, style="TButton", 
                       command=lambda k_id=keg.get('id'), k_name=keg.get('title'), 
                       p=popup_window: self._delete_keg_definition(k_id, k_name, p)).grid(row=0, column=3, padx=(0, 5), pady=2, sticky='e')

        # Footer Area (Re-used from open logic, no need to redraw)
        # However, we need to ensure the footer buttons are packed in the _open function (which they are)
        
        scroll_frame.update_idletasks()
    
    # def _open_keg_settings_popup(self):
        # # UI mirrors the Beverage Library for consistent behavior
        # popup = tk.Toplevel(self.root)
        # popup.title("Keg Settings")
        
        # # Fixed window size
        # popup.geometry("700x510") 
        
        # popup.transient(self.root)
        # popup.grab_set() 
        
        # main_frame = ttk.Frame(popup, padding="10"); main_frame.pack(expand=True, fill="both")
        
        # canvas = tk.Canvas(main_frame, borderwidth=0)
        # v_scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        # scroll_frame = ttk.Frame(canvas)
        # v_scrollbar.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
        # canvas.configure(yscrollcommand=v_scrollbar.set)
        
        # # Adjust canvas window width to fit the geometry
        # canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=680) 

        # def on_frame_configure(event): canvas.configure(scrollregion=canvas.bbox("all"))
        # scroll_frame.bind("<Configure>", on_frame_configure)
        # def on_canvas_resize(event): canvas.itemconfig(canvas_window, width=event.width)
        # canvas.bind('<Configure>', on_canvas_resize)

        # self.keg_settings_popup_vars = []
        
        # # Auto-sort the list upon opening the popup
        # keg_list_unsorted = self.settings_manager.get_keg_definitions()
        # keg_list = sorted(keg_list_unsorted, key=lambda k: k.get('title', '').lower())
        
        # # Pre-fetch beverage library for lookup
        # beverage_lib = self.settings_manager.get_beverage_library().get('beverages', [])
        # beverage_map = {b['id']: b['name'] for b in beverage_lib}

        # # --- Helper to force alignment across separate row frames ---
        # def configure_grid_cols(container):
            # container.grid_columnconfigure(0, weight=1, minsize=220) # Title
            # container.grid_columnconfigure(1, weight=1, minsize=220) # Contents
            # container.grid_columnconfigure(2, weight=0, minsize=80)  # Edit
            # container.grid_columnconfigure(3, weight=0, minsize=80)  # Delete

        # # --- Header Row ---
        # header_frame = ttk.Frame(scroll_frame)
        # header_frame.grid(row=0, column=0, columnspan=4, sticky='ew', padx=5, pady=5)
        # configure_grid_cols(header_frame)
        
        # # Header: Keg Title (Left)
        # ttk.Label(header_frame, text="Keg Title", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, padx=5, sticky='w')
        
        # # Header: Contents (Left-Justified with extra right padding)
        # # padx=(5, 30) adds 5px left and 30px right padding to push it away from buttons
        # contents_header = ttk.Label(header_frame, text="Contents (Beverage)", font=('TkDefaultFont', 10, 'bold'))
        # contents_header.grid(row=0, column=1, padx=(5, 60), sticky='w') 
        
        # # Header: Actions (Right)
        # ttk.Label(header_frame, text="Actions", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=2, columnspan=2, sticky='e', padx=(5, 25))

        # BG_EVEN = '#FFFFFF'; BG_ODD = '#F5F5F5' 

        # for i in range(len(keg_list)):
            # keg = keg_list[i]; row = i + 1; bg_color = BG_ODD if i % 2 else BG_EVEN
            
            # row_frame = tk.Frame(scroll_frame, bg=bg_color, relief='flat', bd=0)
            # row_frame.grid(row=row, column=0, columnspan=4, sticky='ew', pady=(1, 0))
            
            # # Apply same column sizing to this row
            # configure_grid_cols(row_frame)
            
            # # Col 0: Keg Title
            # title_label_text = tk.StringVar(value=keg.get('title', ''))
            # ttk.Label(row_frame, textvariable=title_label_text, anchor='w', background=bg_color, 
                      # padding=(5, 5)).grid(row=0, column=0, sticky='ew', padx=5)
            # self.keg_settings_popup_vars.append(title_label_text)
            
            # # Col 1: Contents (Beverage) - Resolved Name
            # bev_id = keg.get('beverage_id', UNASSIGNED_BEVERAGE_ID)
            # bev_name = beverage_map.get(bev_id, "")
            # if not bev_name and bev_id != UNASSIGNED_BEVERAGE_ID: 
                # bev_name = "Unknown"
            # elif not bev_name:
                # bev_name = "" 
            
            # # FIX: Added padx=(5, 30) to create the buffer zone on the right
            # ttk.Label(row_frame, text=bev_name, anchor='w', background=bg_color,
                      # padding=(5, 5)).grid(row=0, column=1, sticky='w', padx=(5, 60))

            # # Col 2: Edit Button
            # ttk.Button(row_frame, text="Edit", width=8, 
                       # command=lambda k=keg.copy(), p=popup: self._open_keg_edit_popup(k, p)).grid(row=0, column=2, padx=(5, 5), pady=2, sticky='e')

            # # Col 3: Delete Button
            # ttk.Button(row_frame, text="Delete", width=8, style="TButton", 
                       # command=lambda k_id=keg.get('id'), k_name=keg.get('title'), 
                       # p=popup: self._delete_keg_definition(k_id, k_name, p)).grid(row=0, column=3, padx=(0, 5), pady=2, sticky='e')

        # footer_frame = ttk.Frame(popup, padding="10"); 
        # footer_frame.pack(fill="x", side="bottom", pady=(10, 0))
        
        # ttk.Button(footer_frame, text="Add New Keg", 
                   # command=lambda p=popup: self._open_keg_edit_popup(None, p)).pack(side="left", padx=5)

        # ttk.Button(footer_frame, text="Close", command=popup.destroy).pack(side="right", padx=5)
        # # Help Button
        # ttk.Button(footer_frame, text="Help", width=8,
                   # command=lambda: self._open_help_popup("keg_settings")).pack(side="right", padx=5)
        
        # scroll_frame.update_idletasks()

    def _open_keg_edit_popup(self, keg_data=None, parent_popup=None):
        is_new = keg_data is None
        popup = tk.Toplevel(self.root)
        keg_title = keg_data.get('title', 'New Keg') if keg_data else 'New Keg'
        popup.title("Add New Keg" if is_new else f"Edit {keg_title}")
        popup.geometry("600x480")
        popup.transient(self.root)
        popup.grab_set()

        form_frame = ttk.Frame(popup, padding="15")
        form_frame.pack(expand=True, fill="both")
        
        default_data = self.settings_manager._get_default_keg_definitions()[0] 
        data = keg_data if keg_data else default_data.copy()
        
        display_units = self.settings_manager.get_display_units()
        weight_unit = "kg" if display_units == "metric" else "lb"
        volume_unit = "Liters" if display_units == "metric" else "Gallons"
        weight_conversion = 1.0 if display_units == "metric" else KG_TO_LB
        volume_conversion = 1.0 if display_units == "metric" else LITERS_TO_GALLONS
        entry_width = 10 

        max_vol_l = data.get('maximum_full_volume_liters', default_data['maximum_full_volume_liters'])
        start_vol_l = data.get('calculated_starting_volume_liters', 0.0)
        dispensed_l = data.get('current_dispensed_liters', 0.0)
        remaining_l = max(0.0, start_vol_l - dispensed_l)
        empty_kg = data.get('tare_weight_kg', 0.0)
        total_kg = data.get('starting_total_weight_kg', 0.0)
        max_vol_display = max_vol_l * volume_conversion
        start_vol_display = start_vol_l * volume_conversion
        remaining_display = remaining_l * volume_conversion

        temp_vars = {
            'id': tk.StringVar(value=data.get('id', str(uuid.uuid4()))),
            'title': tk.StringVar(value=data.get('title')),
            'max_volume_display': tk.StringVar(value=f"{max_vol_display:.2f}"),
            'tare_weight_kg': tk.StringVar(value=f"{empty_kg:.2f}"), 
            'total_weight_kg': tk.StringVar(value=f"{total_kg:.2f}"), 
            'starting_volume_display': tk.StringVar(value=f"{start_vol_display:.2f}"),
            'current_volume_display': tk.StringVar(value=f"{remaining_display:.2f}"), 
            'current_dispensed_liters': tk.StringVar(value=f"{dispensed_l:.2f}"),
            'beverage_name_var': tk.StringVar(), 
            'original_keg_data': data.copy()
        }
        # Helper vars
        temp_vars['tare_entry'] = tk.StringVar(value=f"{empty_kg * weight_conversion:.2f}")
        temp_vars['total_entry'] = tk.StringVar(value=f"{total_kg * weight_conversion:.2f}")

        row_idx = tk.IntVar(value=0)
        
        # Helper re-definition
        def add_field(parent, label_text, var, unit="", row=None, readonly=False, is_volume=False, is_weight=False, is_title=False):
            ttk.Label(parent, text=label_text, width=25, anchor="w").grid(row=row, column=0, padx=5, pady=5, sticky='w')
            if is_weight:
                base_name = var.get().split('_')[0]; display_var_name = f"{base_name}_entry"; display_var = temp_vars[display_var_name]
            elif is_volume or not is_title: display_var = var
            else: display_var = var
            widget_width = 30 if is_title else entry_width
            entry = ttk.Entry(parent, textvariable=display_var, width=widget_width, state=('readonly' if readonly else 'normal'))
            if is_weight: temp_vars[var.get().replace('_weight_kg', '_entry_widget')] = entry
            entry.grid(row=row, column=1, sticky='ew', padx=5, pady=5)
            if is_weight and not readonly:
                 def update_kg_on_change(event, kg_var_name, entry_var):
                     try:
                         kg_value = float(entry_var.get()) / weight_conversion
                         temp_vars[kg_var_name].set(f"{kg_value:.2f}")
                     except ValueError: temp_vars[kg_var_name].set("0.00")
                 entry.bind("<FocusOut>", lambda event, kg_var=var.get(), entry_var=display_var: update_kg_on_change(event, kg_var, entry_var))
            if unit: ttk.Label(parent, text=unit).grid(row=row, column=2, sticky='w', padx=2)
            row_idx.set(row + 1)
            return entry

        form_frame.grid_columnconfigure(1, weight=1)
        
        # Row 0: Contents Dropdown
        ttk.Label(form_frame, text="Contents (Beverage):", width=25, anchor='w').grid(row=row_idx.get(), column=0, padx=5, pady=5, sticky='w')
        
        # Populate Beverages
        beverage_lib = self.settings_manager.get_beverage_library().get('beverages', [])
        bev_names = [b['name'] for b in beverage_lib]
        bev_names.insert(0, "Empty")
        
        # Set Initial Value
        current_bev_id = data.get('beverage_id', UNASSIGNED_BEVERAGE_ID)
        if current_bev_id == UNASSIGNED_BEVERAGE_ID:
            temp_vars['beverage_name_var'].set("Empty")
        else:
            bev = next((b for b in beverage_lib if b['id'] == current_bev_id), None)
            temp_vars['beverage_name_var'].set(bev['name'] if bev else "Empty")
            
        bev_dropdown = ttk.Combobox(form_frame, textvariable=temp_vars['beverage_name_var'], values=bev_names, state="readonly", width=28)
        bev_dropdown.grid(row=row_idx.get(), column=1, sticky='ew', padx=5, pady=5)
        row_idx.set(row_idx.get() + 1)
        
        ttk.Separator(form_frame, orient='horizontal').grid(row=row_idx.get(), column=0, columnspan=3, sticky='ew', pady=5); row_idx.set(row_idx.get() + 1)

        # Row 2+: Standard Keg Fields (Title, Max Vol, Weights...)
        # Updated label to indicate character limit
        title_entry = add_field(form_frame, "Keg Title (Max 24 chars):", temp_vars['title'], unit="", row=row_idx.get(), readonly=False, is_title=True); row_idx.set(row_idx.get())
        add_field(form_frame, "Maximum Full Volume:", temp_vars['max_volume_display'], volume_unit, row=row_idx.get()); row_idx.set(row_idx.get())

        ttk.Separator(form_frame, orient='horizontal').grid(row=row_idx.get(), column=0, columnspan=3, sticky='ew', pady=5); row_idx.set(row_idx.get() + 1)
        
        link_frame = ttk.Frame(form_frame)
        link_frame.grid(row=row_idx.get(), column=0, columnspan=3, sticky='ew')
        link_frame.grid_columnconfigure(1, weight=0, minsize=entry_width*8) 
        link_frame.grid_columnconfigure(2, weight=0) 
        link_frame.grid_columnconfigure(3, weight=1)
        row_idx.set(row_idx.get() + 1) 

        tare_entry = add_field(link_frame, "Tare weight (empty weight):", tk.StringVar(value='tare_weight_kg'), weight_unit, row=0, is_weight=True)
        total_entry = add_field(link_frame, "Starting Total Weight:", tk.StringVar(value='total_weight_kg'), weight_unit, row=1, is_weight=True)
        calc_vol_entry = add_field(link_frame, "Starting Volume:", temp_vars['starting_volume_display'], unit="", row=2, readonly=True, is_volume=True)
        
        self._keg_edit_link_weight_to_volume(temp_vars, None)
        ttk.Label(link_frame, text=volume_unit).grid(row=2, column=2, sticky='w', padx=2)
        ttk.Button(link_frame, text="Use Starting Volume", width=18,
                   command=lambda v=temp_vars: v['current_volume_display'].set(v['starting_volume_display'].get())).grid(row=2, column=3, sticky='w', padx=5)
        
        current_vol_entry = add_field(link_frame, "Current (Remaining) Volume:", temp_vars['current_volume_display'], volume_unit, row=3, is_volume=True)
        
        row_idx.set(row_idx.get() + 1)
        ttk.Separator(form_frame, orient='horizontal').grid(row=row_idx.get(), column=0, columnspan=3, sticky='ew', pady=10); row_idx.set(row_idx.get() + 1)
        
        btns_frame = ttk.Frame(popup, padding="10")
        btns_frame.pack(fill="x", side="bottom")
        
        ttk.Button(btns_frame, text="Save", command=lambda p=popup: self._save_keg_definition(temp_vars, is_new, p, parent_popup)).pack(side="right", padx=5)
        ttk.Button(btns_frame, text="Cancel", command=lambda p=popup: self._keg_edit_check_cancel(temp_vars, p)).pack(side="right", padx=5)
        ttk.Button(btns_frame, text="Help", width=8, command=lambda: self._open_help_popup("keg_settings")).pack(side="right", padx=5)

        popup.update_idletasks()
        if title_entry: title_entry.focus_set()

    def _keg_edit_check_cancel(self, temp_vars, popup_window):
        """
        Implements the intermediary popup logic when the user cancels an edited keg.
        """
        
        # 1. Manually trigger FocusOut on all weight entries to ensure KG/Volume variables are up-to-date
        # This is critical for comparing the potentially unsaved state
        if 'tare_entry_widget' in temp_vars:
             temp_vars['tare_entry_widget'].event_generate('<FocusOut>')
        if 'total_entry_widget' in temp_vars:
             temp_vars['total_entry_widget'].event_generate('<FocusOut>')
             
        # 2. Re-calculate the current state based on StringVars
        display_units = self.settings_manager.get_display_units()
        volume_conversion = 1.0 if display_units == "metric" else LITERS_TO_GALLONS

        try:
            # Get the new calculated starting volume and current remaining volume
            tare_kg = float(temp_vars['tare_weight_kg'].get())
            total_kg = float(temp_vars['total_weight_kg'].get())
            max_vol_l = float(temp_vars['max_volume_display'].get()) / volume_conversion
            
            new_start_vol_l = self.settings_manager._calculate_volume_from_weight(total_kg, tare_kg)
            new_current_vol_l = float(temp_vars['current_volume_display'].get()) / volume_conversion
            new_dispensed_l = new_start_vol_l - new_current_vol_l
        except ValueError:
             # If inputs are invalid, treat as modified to avoid data loss
             is_modified = True
        else:
            # Get the original (saved) state from the internal dict
            original_data = temp_vars['original_keg_data']
            
            # Use a small tolerance for float comparison
            TOLERANCE = 0.01 
            
            # Check for modification
            is_modified = (
                abs(original_data.get('tare_weight_kg', 0.0) - tare_kg) > TOLERANCE or
                abs(original_data.get('starting_total_weight_kg', 0.0) - total_kg) > TOLERANCE or
                abs(original_data.get('calculated_starting_volume_liters', 0.0) - new_start_vol_l) > TOLERANCE or
                abs(original_data.get('current_dispensed_liters', 0.0) - new_dispensed_l) > TOLERANCE or
                abs(original_data.get('maximum_full_volume_liters', 0.0) - max_vol_l) > TOLERANCE or
                original_data.get('title', '') != temp_vars['title'].get().strip()
            )

        if not is_modified:
            # No changes, close safely
            popup_window.destroy()
            return

        # --- Show Confirmation Dialog ---
        popup_window.grab_release() 
        confirm_popup = tk.Toplevel(self.root)
        confirm_popup.title("Unsaved Changes")
        confirm_popup.geometry("450x150")
        confirm_popup.transient(popup_window)
        confirm_popup.grab_set()

        parent_x = popup_window.winfo_x(); parent_y = popup_window.winfo_y()
        parent_w = popup_window.winfo_width(); parent_h = popup_window.winfo_height()
        x = parent_x + (parent_w // 2) - (450 // 2)
        y = parent_y + (parent_h // 2) - (150 // 2)
        confirm_popup.geometry(f"+{x}+{y}")
        
        msg = "The keg data has been changed. Do you want to exit without saving the change, or return to the Edit Keg screen to save the change?"
        ttk.Label(confirm_popup, text=msg, wraplength=400, justify=tk.CENTER, padding=15).pack(expand=True, fill="both")

        btns_frame = ttk.Frame(confirm_popup, padding="10"); btns_frame.pack(fill="x", side="bottom")

        def exit_without_saving():
            confirm_popup.destroy()
            popup_window.destroy()

        def return_to_edit():
            confirm_popup.destroy()
            popup_window.grab_set()

        ttk.Button(btns_frame, text="Exit (Discard Changes)", command=exit_without_saving).pack(side="right", padx=5)
        ttk.Button(btns_frame, text="Return to Edit", command=return_to_edit).pack(side="right")
        
        confirm_popup.protocol("WM_DELETE_WINDOW", return_to_edit)

    def _save_keg_definition(self, temp_vars, is_new, popup_window, parent_popup):
        try:
            display_units = self.settings_manager.get_display_units()
            volume_conversion = 1.0 if display_units == "metric" else LITERS_TO_GALLONS
            title = temp_vars['title'].get().strip()
            
            if 'tare_entry_widget' in temp_vars: temp_vars['tare_entry_widget'].event_generate('<FocusOut>')
            if 'total_entry_widget' in temp_vars: temp_vars['total_entry_widget'].event_generate('<FocusOut>')
            
            tare_kg = float(temp_vars['tare_weight_kg'].get())
            total_kg = float(temp_vars['total_weight_kg'].get())
            max_vol_l = float(temp_vars['max_volume_display'].get()) / volume_conversion
            current_vol_display = temp_vars['current_volume_display'].get()
            current_vol_l = float(current_vol_display) / volume_conversion 
            start_vol_l = self.settings_manager._calculate_volume_from_weight(total_kg, tare_kg)
            
            # Map Beverage Name -> ID
            bev_name = temp_vars['beverage_name_var'].get()
            if bev_name == "Empty":
                bev_id = UNASSIGNED_BEVERAGE_ID
            else:
                beverage_lib = self.settings_manager.get_beverage_library().get('beverages', [])
                found = next((b for b in beverage_lib if b['name'] == bev_name), None)
                bev_id = found['id'] if found else UNASSIGNED_BEVERAGE_ID

            # VALIDATION
            if not title: 
                messagebox.showerror("Input Error", "Keg Title cannot be empty.", parent=popup_window)
                return
            
            # 24 character limit check
            if len(title) > 24: 
                messagebox.showerror("Input Error", "Keg Title is limited to 24 characters.", parent=popup_window)
                return

            if not (tare_kg >= 0 and total_kg >= 0 and start_vol_l >= 0 and current_vol_l >= 0): 
                messagebox.showerror("Input Error", "All weights and volumes must be non-negative.", parent=popup_window); return
            if not (total_kg >= tare_kg):
                messagebox.showerror("Input Error", "Starting Total Weight must be greater than or equal to Tare Weight.", parent=popup_window); return
            if not (current_vol_l <= start_vol_l + 0.01): 
                messagebox.showerror("Input Error", f"Current Volume ({current_vol_l:.2f} L) cannot be greater than Calculated Starting Volume ({start_vol_l:.2f} L).", parent=popup_window); return
            if not (max_vol_l >= 0):
                 messagebox.showerror("Input Error", "Maximum Full Volume must be non-negative.", parent=popup_window); return

            current_dispensed_liters = start_vol_l - current_vol_l
            existing_keg = self.settings_manager.get_keg_by_id(temp_vars['id'].get()) if not is_new else None
            final_dispensed_to_save = current_dispensed_liters
            final_pulses_to_save = 0 

            if existing_keg:
                TOLERANCE = 0.01 
                starting_vol_changed = abs(existing_keg.get('calculated_starting_volume_liters', 0.0) - start_vol_l) > TOLERANCE
                if not starting_vol_changed:
                     final_dispensed_to_save = existing_keg.get('current_dispensed_liters', 0.0)
                     final_pulses_to_save = existing_keg.get('total_dispensed_pulses', 0)

            new_data = {
                "id": temp_vars['id'].get(), 
                "title": title, 
                "tare_weight_kg": tare_kg, 
                "starting_total_weight_kg": total_kg, 
                "maximum_full_volume_liters": max_vol_l, 
                "calculated_starting_volume_liters": start_vol_l, 
                "current_dispensed_liters": final_dispensed_to_save,
                "total_dispensed_pulses": final_pulses_to_save,
                "beverage_id": bev_id,
                "fill_date": "" 
            }
            
            keg_list = self.settings_manager.get_keg_definitions()
            if is_new: keg_list.append(new_data)
            else:
                found = False
                for i, k in enumerate(keg_list):
                    if k.get('id') == new_data['id']: 
                        keg_list[i] = new_data; 
                        found = True; 
                        break
                if not found: messagebox.showerror("Save Error", "Could not find the original keg to update.", parent=popup_window); return

            sorted_list = sorted(keg_list, key=lambda k: k.get('title', '').lower())
            self.settings_manager.save_keg_definitions(sorted_list)
            
            if hasattr(self, 'sensor_logic') and self.sensor_logic and not self.sensor_logic.is_paused: 
                self.sensor_logic.force_recalculation()
            
            self._populate_keg_dropdowns(); 
            popup_window.destroy()
            
            # --- PERSISTENCE FIX ---
            # Do NOT destroy parent_popup. Just refresh it.
            if parent_popup and parent_popup.winfo_exists():
                 self._populate_keg_settings_list(parent_popup)
            
            print(f"UIManager: Keg '{title}' saved successfully.")

        except ValueError as e:
            messagebox.showerror("Input Error", f"Invalid number input. {e}", parent=popup_window)
        except Exception as e:
            messagebox.showerror("Error", f"Error saving keg: {e}", parent=popup_window)

    def _delete_keg_definition(self, keg_id, keg_title, parent_popup):
        if not messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete the keg '{keg_title}'? This will also re-assign any taps currently linked to it.", parent=parent_popup): return
            
        success, message = self.settings_manager.delete_keg_definition(keg_id)
        
        if success:
            # CRITICAL: Reload initial volumes in SensorLogic
            if hasattr(self, 'sensor_logic') and self.sensor_logic and not self.sensor_logic.is_paused: 
                self.sensor_logic.force_recalculation()
                
            self._populate_keg_dropdowns()
            self._refresh_ui_for_settings_or_resume() 

            # --- PERSISTENCE FIX ---
            # Do NOT destroy parent_popup. Just refresh it.
            if self.settings_manager.get_keg_definitions(): 
                self._populate_keg_settings_list(parent_popup)
            else: 
                # If empty, we can still show the empty list (or close if you prefer, but persistence suggests keeping it open)
                self._populate_keg_settings_list(parent_popup)
                messagebox.showinfo("Keg Library Empty", "The Keg Library is now empty.", parent=self.root)
        else:
            messagebox.showerror("Delete Error", message, parent=parent_popup)

    # --- Flow Sensor Calibration Popup (NEW LIST VIEW) ---
    def _open_flow_calibration_popup(self, initial_tab_index=0, initial_tap_index=None, initial_keg_title=None):
         popup = tk.Toplevel(self.root)
         popup.title("Flow Sensor Calibration"); 
         popup.geometry("500x550"); # Increased height for tabs
         popup.transient(self.root); 
         popup.grab_set()

         # Create Notebook
         notebook = ttk.Notebook(popup)
         notebook.pack(expand=True, fill="both", padx=10, pady=10)

         # Tab 1: Pour Calibration (Existing Logic)
         tab1 = ttk.Frame(notebook, padding="10")
         notebook.add(tab1, text='Pour Calibration (Quick)')
         self._create_pour_calibration_tab(tab1, popup)

         # Tab 2: Keg Calibration (New Logic)
         tab2 = ttk.Frame(notebook, padding="10")
         notebook.add(tab2, text='Keg Calibration (Accurate)')
         self._create_keg_calibration_tab(tab2, popup)

         # --- Footer Buttons ---
         buttons_frame = ttk.Frame(popup, padding="10"); 
         buttons_frame.pack(fill="x", side="bottom", pady=(0, 10))
         
         # Advanced Users button (left side)
         ttk.Button(buttons_frame, text="Manual Cal Factor - Expert Only", 
                    command=lambda p=popup: self._open_manually_enter_calibration_factor_popup(p)).pack(side="left", padx=5)

         ttk.Button(buttons_frame, text="Close", command=popup.destroy).pack(side="right", padx=5)
         
         # Help Button
         ttk.Button(buttons_frame, text="Help", width=8, 
                   command=lambda: self._open_help_popup("calibration")).pack(side="right", padx=5)
         
         # --- NEW: Handle Pre-Selection Arguments ---
         if initial_tab_index is not None:
             notebook.select(initial_tab_index)
             
         if initial_tap_index is not None:
             # Set the tap dropdown (Format: "Tap N")
             tap_str = f"Tap {initial_tap_index + 1}"
             self.keg_cal_tap_var.set(tap_str)
             
             # If a keg title was passed, set it too
             if initial_keg_title:
                 self.keg_cal_keg_var.set(initial_keg_title)
                 
             # Force update of the display fields to show the data for the pre-selected keg
             self._update_keg_cal_tab_display()
         # -------------------------------------------
         
         popup.update_idletasks()

    def _create_pour_calibration_tab(self, parent_frame, popup):
         """Populates the existing list-based pour calibration UI into the given frame."""
         
         canvas = tk.Canvas(parent_frame, borderwidth=0)
         v_scrollbar = ttk.Scrollbar(parent_frame, orient="vertical", command=canvas.yview)
         scroll_frame = ttk.Frame(canvas)
         
         v_scrollbar.pack(side="right", fill="y"); 
         canvas.pack(side="left", fill="both", expand=True)
         canvas.configure(yscrollcommand=v_scrollbar.set)
         canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=440) 

         def on_frame_configure(event): canvas.configure(scrollregion=canvas.bbox("all"))
         scroll_frame.bind("<Configure>", on_frame_configure)
         def on_canvas_resize(event): canvas.itemconfig(canvas_window, width=event.width)
         canvas.bind('<Configure>', on_canvas_resize)

         # Grid column configuration
         scroll_frame.grid_columnconfigure(0, weight=1); 
         scroll_frame.grid_columnconfigure(1, weight=0); 

         # --- Header Row ---
         header_frame = ttk.Frame(scroll_frame); 
         header_frame.grid(row=0, column=0, columnspan=2, sticky='ew', padx=5, pady=5)
         header_frame.grid_columnconfigure(0, weight=1); 
         header_frame.grid_columnconfigure(1, weight=0);
         
         ttk.Label(header_frame, text="Flow Sensor", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, padx=5, sticky='w')
         ttk.Label(header_frame, text="Action", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=1, sticky='e', padx=5)

         BG_EVEN = '#FFFFFF'; BG_ODD = '#F5F5F5' 
         displayed_taps_count = self.settings_manager.get_displayed_taps()

         for i in range(displayed_taps_count):
             tap_name = f"Tap {i+1}"
             row = i + 1; bg_color = BG_ODD if i % 2 else BG_EVEN
             
             row_frame = tk.Frame(scroll_frame, bg=bg_color, relief='flat', bd=0); 
             row_frame.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(1, 0))
             row_frame.grid_columnconfigure(0, weight=1); row_frame.grid_columnconfigure(1, weight=0) 
             
             ttk.Label(row_frame, text=tap_name, anchor='w', background=bg_color, padding=(5, 5)).grid(row=0, column=0, sticky='ew', padx=5)
             
             ttk.Button(row_frame, text="Calibrate", width=12, 
                        command=lambda idx=i, p=popup: self._open_single_tap_calibration_popup(idx, p)).grid(row=0, column=1, padx=(5, 5), pady=2, sticky='e')

    def _create_keg_calibration_tab(self, parent_frame, popup):
        """Creates the new Keg Calibration UI."""
        
        # Variables for this tab
        self.keg_cal_tap_var = tk.StringVar()
        self.keg_cal_keg_var = tk.StringVar()
        
        self.keg_cal_vol_var = tk.StringVar(value="--")
        self.keg_cal_pulses_var = tk.StringVar(value="--")
        self.keg_cal_current_k_var = tk.StringVar(value="--")
        self.keg_cal_new_k_var = tk.StringVar(value="--")
        self.keg_cal_validation_var = tk.BooleanVar(value=False)
        
        # 1. Tap Selection
        row_frame = ttk.Frame(parent_frame); row_frame.pack(fill='x', pady=5)
        ttk.Label(row_frame, text="Select Tap:", width=15).pack(side='left')
        
        displayed_taps = self.settings_manager.get_displayed_taps()
        tap_options = [f"Tap {i+1}" for i in range(displayed_taps)]
        
        self.keg_cal_tap_dropdown = ttk.Combobox(row_frame, textvariable=self.keg_cal_tap_var, values=tap_options, state="readonly")
        self.keg_cal_tap_dropdown.pack(side='left', fill='x', expand=True)
        self.keg_cal_tap_dropdown.bind("<<ComboboxSelected>>", self._update_keg_cal_tab_display)

        # 2. Keg Selection
        row_frame = ttk.Frame(parent_frame); row_frame.pack(fill='x', pady=5)
        ttk.Label(row_frame, text="Select Keg:", width=15).pack(side='left')
        
        # Populate all kegs
        all_kegs = self.settings_manager.get_keg_definitions()
        keg_titles = [k.get('title', 'Unknown') for k in all_kegs]
        
        self.keg_cal_keg_dropdown = ttk.Combobox(row_frame, textvariable=self.keg_cal_keg_var, values=keg_titles, state="readonly")
        self.keg_cal_keg_dropdown.pack(side='left', fill='x', expand=True)
        self.keg_cal_keg_dropdown.bind("<<ComboboxSelected>>", self._update_keg_cal_tab_display)

        ttk.Separator(parent_frame, orient='horizontal').pack(fill='x', pady=15)

        # 3. Data Display
        def add_info_row(label, var):
            r = ttk.Frame(parent_frame); r.pack(fill='x', pady=2)
            ttk.Label(r, text=label, width=25, anchor='w').pack(side='left')
            ttk.Label(r, textvariable=var, width=15, anchor='e', relief='sunken').pack(side='left', padx=5)
            
        add_info_row("Keg Starting Volume (L):", self.keg_cal_vol_var)
        add_info_row("Total Pulses Recorded:", self.keg_cal_pulses_var)
        add_info_row("Current K-Factor:", self.keg_cal_current_k_var)
        
        ttk.Separator(parent_frame, orient='horizontal').pack(fill='x', pady=15)
        
        # 4. Result
        res_frame = ttk.Frame(parent_frame); res_frame.pack(fill='x', pady=5)
        ttk.Label(res_frame, text="Calculated New K-Factor:", width=25, font=('TkDefaultFont', 10, 'bold')).pack(side='left')
        ttk.Label(res_frame, textvariable=self.keg_cal_new_k_var, width=15, anchor='e', relief='sunken', font=('TkDefaultFont', 10, 'bold')).pack(side='left', padx=5)

        # 5. Validation (FIXED: Separated Checkbox and Label to support wrapping)
        chk_frame = ttk.Frame(parent_frame); chk_frame.pack(fill='x', pady=15)
        val_text = "I confirm this keg was assigned to and fully dispensed only from this tap, from the time its volume was calculated until it kicked."
        
        # Checkbox (No text, just the box)
        self.keg_cal_chk = ttk.Checkbutton(chk_frame, variable=self.keg_cal_validation_var)
        self.keg_cal_chk.pack(side='left', anchor='nw')
        
        # Label (Text with wrapping)
        ttk.Label(chk_frame, text=val_text, wraplength=400).pack(side='left', anchor='w', padx=(5, 0))
        
        # Trace logic remains the same
        self.keg_cal_validation_var.trace_add('write', lambda *args: self._update_keg_cal_save_button())

        # 6. Save Button
        self.keg_cal_save_btn = ttk.Button(parent_frame, text="Save Calibration", state='disabled', command=lambda: self._save_keg_calibration(popup))
        self.keg_cal_save_btn.pack(pady=5)

    def _update_keg_cal_tab_display(self, event=None):
        """Updates the calculated fields in the Keg Calibration tab."""
        tap_str = self.keg_cal_tap_var.get()
        keg_title = self.keg_cal_keg_var.get()
        
        if not tap_str: return

        # Parse Tap Index
        try:
            tap_idx = int(tap_str.split(" ")[1]) - 1
        except: return

        # If event came from Tap change, auto-select the assigned keg
        if event and event.widget == self.keg_cal_tap_dropdown:
            assignments = self.settings_manager.get_sensor_keg_assignments()
            if tap_idx < len(assignments):
                assigned_id = assignments[tap_idx]
                assigned_keg = self.settings_manager.get_keg_by_id(assigned_id)
                if assigned_keg:
                    self.keg_cal_keg_var.set(assigned_keg.get('title', ''))
                    keg_title = assigned_keg.get('title', '')

        # Get Keg Data
        all_kegs = self.settings_manager.get_keg_definitions()
        keg_data = next((k for k in all_kegs if k.get('title') == keg_title), None)
        
        # Get Current K-Factor
        factors = self.settings_manager.get_flow_calibration_factors()
        current_k = factors[tap_idx]
        self.keg_cal_current_k_var.set(f"{current_k:.2f}")

        if keg_data:
            start_vol = keg_data.get('calculated_starting_volume_liters', 0.0)
            pulses = keg_data.get('total_dispensed_pulses', 0)
            
            self.keg_cal_vol_var.set(f"{start_vol:.2f}")
            self.keg_cal_pulses_var.set(str(pulses))
            
            if start_vol > 0 and pulses > 0:
                new_k = pulses / start_vol
                self.keg_cal_new_k_var.set(f"{new_k:.2f}")
            else:
                self.keg_cal_new_k_var.set("Invalid Data")
        else:
            self.keg_cal_vol_var.set("--")
            self.keg_cal_pulses_var.set("--")
            self.keg_cal_new_k_var.set("--")
            
        self._update_keg_cal_save_button()

    def _update_keg_cal_save_button(self):
        """Enables save button only if math is valid and checkbox checked."""
        # FIX: Guard clause to prevent crash if called before button exists
        if not hasattr(self, 'keg_cal_save_btn') or not self.keg_cal_save_btn:
            return

        is_checked = self.keg_cal_validation_var.get()
        k_val_str = self.keg_cal_new_k_var.get()
        
        try:
            k_val = float(k_val_str)
            valid_math = (k_val > 0)
        except:
            valid_math = False
            
        if is_checked and valid_math:
            self.keg_cal_save_btn.config(state='normal')
        else:
            self.keg_cal_save_btn.config(state='disabled')

    def _save_keg_calibration(self, popup):
        # Retrieve values while widgets still exist
        try:
            new_k = float(self.keg_cal_new_k_var.get())
            tap_str = self.keg_cal_tap_var.get()
            # Parse "Tap 1 (Label)" -> Index 0
            tap_idx = int(tap_str.split(" ")[1]) - 1
            keg_title = self.keg_cal_keg_var.get()
        except ValueError as e:
            messagebox.showerror("Input Error", f"Invalid input: {e}", parent=popup)
            return

        # 1. Close the popup IMMEDIATELY to prevent z-order/freezing issues
        popup.destroy()

        try:
            # 2. Update calibration factors
            factors = self.settings_manager.get_flow_calibration_factors()
            factors[tap_idx] = new_k
            self.settings_manager.save_flow_calibration_factors(factors)
            
            # Use literals to avoid NameError if constants aren't imported
            SAFE_UNASSIGNED_KEG_ID = "unassigned_keg_id"
            SAFE_UNASSIGNED_BEVERAGE_ID = "unassigned_beverage_id"

            # 3. Set the Tap's Keg assignment to Offline
            self.settings_manager.save_sensor_keg_assignment(tap_idx, SAFE_UNASSIGNED_KEG_ID)

            # 4. Set the Tap's Beverage assignment to Offline
            self.settings_manager.save_sensor_beverage_assignment(tap_idx, SAFE_UNASSIGNED_BEVERAGE_ID)

            # 5. Reset the actual Keg Definition to Empty
            all_kegs = self.settings_manager.get_keg_definitions()
            keg_updated = False
            
            for keg in all_kegs:
                if keg.get('title') == keg_title:
                    keg['beverage_id'] = SAFE_UNASSIGNED_BEVERAGE_ID
                    keg['fill_date'] = ""
                    keg['current_dispensed_liters'] = 0.0
                    keg['total_dispensed_pulses'] = 0
                    keg_updated = True
                    break
            
            if keg_updated:
                self.settings_manager.save_keg_definitions(all_kegs)
                print(f"Calibration: Keg '{keg_title}' reset to Empty state.")

            # 6. Force Logic Refresh 
            if hasattr(self, 'sensor_logic') and self.sensor_logic:
                self.sensor_logic.force_recalculation()
            
            # 7. Force UI Refresh
            if hasattr(self, '_refresh_ui_for_settings_or_resume'):
                self._refresh_ui_for_settings_or_resume()
            
            # 8. Show Success Message (Parent is now root because popup is gone)
            messagebox.showinfo("Success", 
                                f"Tap {tap_idx+1} calibrated successfully.\n"
                                f"New K-Factor: {new_k:.2f}\n\n"
                                "The Tap has been set to 'Offline'.\n"
                                f"The Keg '{keg_title}' has been reset to Empty.", 
                                parent=self.root)
            
        except Exception as e:
            # If something fails after close, show error on root
            print(f"Calibration Save Error: {e}")
            messagebox.showerror("Error", f"Could not save calibration: {e}", parent=self.root)
        
    # --- END NEW LIVE DATA CALLBACK ---

    def _single_cal_stop(self):
        if not self._single_cal_in_progress: return
        
        self._single_cal_in_progress = False
        
        # Make the Volume Poured and Measured field READ-ONLY ('readonly') after stopping
        if hasattr(self, '_single_cal_volume_entry') and self._single_cal_volume_entry:
             self._single_cal_volume_entry.config(state='readonly')
        
        # In a real app, this would call sensor_logic to stop the flow cal mode for this tap
        if hasattr(self, 'sensor_logic') and self.sensor_logic:
            # stop_flow_calibration returns the total pulses and the final measured pour in Liters (sensor output)
            total_pulses, final_measured_liters = self.sensor_logic.stop_flow_calibration(self.single_cal_tap_index)
        else:
            total_pulses, final_measured_liters = 0, 0.0 # Mock data
            
        # 1. Get the value the user poured (in their unit, e.g., 1000 ml or 32 oz)
        try:
            target_pour_user_unit = float(self.single_cal_target_volume_var.get())
        except ValueError:
            target_pour_user_unit = 0.0 # Safety fallback
            
        # 2. Convert target pour to Liters (since K-factor is pulses/Liter)
        unit_label = self.single_cal_unit_label.get()
        if unit_label == "ml":
            target_pour_liters = target_pour_user_unit / 1000.0
        elif unit_label == "oz":
            target_pour_liters = target_pour_user_unit * OZ_TO_LITERS
        else:
            target_pour_liters = 0.0
            
        # --- NEW DEDUCTION LOGIC (Triggered by Stop Cal) ---
        deduct_volume = self.single_cal_deduct_volume_var.get()
        if deduct_volume and hasattr(self, 'sensor_logic') and self.sensor_logic and target_pour_liters > 0:
            
            # FIX: Deduct the KNOWN, MEASURED volume (target_pour_liters), not the sensor's output.
            self.sensor_logic.deduct_volume_from_keg(self.single_cal_tap_index, target_pour_liters)
            
            # Show message confirming deduction
            messagebox.showinfo("Inventory Deduction", 
                                f"Volume of {target_pour_liters:.2f} Liters deducted from the assigned keg inventory.", 
                                parent=self._single_cal_popup_window)
        # --- END NEW DEDUCTION LOGIC ---

        # 3. Calculate new K-factor (always using the user's ground truth volume)
        if target_pour_liters > 0 and total_pulses > 0:
            new_k_factor = total_pulses / target_pour_liters
            self._single_cal_calculated_new_factor = new_k_factor
            self._single_cal_last_pour = final_measured_liters # Keep sensor pour for tracking/diagnostic
            self.single_cal_new_factor_var.set(f"{new_k_factor:.2f}")
            self.single_cal_complete = True
            self.single_cal_set_btn.config(state=tk.NORMAL)
        else:
            self._single_cal_calculated_new_factor = None
            self._single_cal_last_pour = 0.0
            self.single_cal_new_factor_var.set("Error (0 Pulses or Target)")
            self.single_cal_complete = False
            self.single_cal_set_btn.config(state=tk.DISABLED)

        self.single_cal_start_btn.config(state=tk.NORMAL)
        self.single_cal_stop_btn.config(state=tk.DISABLED)
        
        print(f"Single Cal: Stopped. Pulses: {total_pulses}, Measured L: {final_measured_liters:.2f}")
        
    def _single_cal_check_close(self, popup_window, parent_window=None):
        """
        Intermediary function called when the user attempts to close the calibration popup.
        Checks if a new factor was calculated but not set.
        """
        # STEP 1: If calibration was in progress, stop it gracefully.
        if self._single_cal_in_progress and hasattr(self.sensor_logic, 'stop_flow_calibration'):
            if self.single_cal_tap_index != -1:
                self._single_cal_stop() 

        # STEP 2: Check if a new factor exists.
        if self._single_cal_calculated_new_factor is not None:
            # New factor calculated but not accepted (button is active)

            # Prevent closing the main popup until the choice is made
            popup_window.grab_release()

            confirm_popup = tk.Toplevel(self.root)
            confirm_popup.title("Unsaved Calibration")
            confirm_popup.geometry("450x150")
            confirm_popup.transient(popup_window)
            confirm_popup.grab_set()

            # Center the confirmation popup relative to the main one
            parent_x = popup_window.winfo_x(); parent_y = popup_window.winfo_y()
            parent_w = popup_window.winfo_width(); parent_h = popup_window.winfo_height()
            x = parent_x + (parent_w // 2) - (450 // 2)
            y = parent_y + (parent_h // 2) - (150 // 2)
            confirm_popup.geometry(f"+{x}+{y}")

            msg = "New cal factor has been calibrated. Do you want to set the new cal factor, or close without changing the cal factor?"
            ttk.Label(confirm_popup, text=msg, wraplength=400, justify=tk.CENTER, padding=15).pack(expand=True, fill="both")

            btns_frame = ttk.Frame(confirm_popup, padding="10"); btns_frame.pack(fill="x", side="bottom")

            # Define combined close action (saves, then closes both)
            def set_and_close():
                # We save, which effectively completes the task.
                self._single_cal_set(destroy_on_success=False, primary_popup=popup_window)
                self._single_cal_calculated_new_factor = None
                self._single_cal_popup_window = None
                
                # Close Confirmation
                confirm_popup.destroy()
                
                # --- FIX: Restore grab to parent before closing popup ---
                if parent_window and parent_window.winfo_exists():
                    parent_window.grab_set()
                # ------------------------------------------------------
                
                popup_window.destroy()

            # Define discard action (just closes both)
            def discard_and_close():
                self._single_cal_calculated_new_factor = None # Discard the value
                self._single_cal_popup_window = None
                
                confirm_popup.destroy()
                
                # --- FIX: Restore grab to parent before closing popup ---
                if parent_window and parent_window.winfo_exists():
                    parent_window.grab_set()
                # ------------------------------------------------------
                
                popup_window.destroy()

            ttk.Button(btns_frame, text="Close (Discard Factor)", command=discard_and_close).pack(side="right", padx=5)
            ttk.Button(btns_frame, text="Set New Cal Factor", command=set_and_close).pack(side="right")

            # Prevent user from closing confirmation via window manager
            confirm_popup.protocol("WM_DELETE_WINDOW", lambda: None)

        else:
            # Safe to close. Perform final cleanup.
            self._single_cal_popup_window = None
            
            # --- FIX: Restore grab to parent before closing popup ---
            if parent_window and parent_window.winfo_exists():
                parent_window.grab_set()
            # ------------------------------------------------------
            
            popup_window.destroy()
            
    def _open_single_tap_calibration_popup(self, tap_index, parent_popup):
        
        tap_name = f"Tap {tap_index + 1}"
        
        # Load current K-factors
        current_factors = self.settings_manager.get_flow_calibration_factors()
        current_k_factor = current_factors[tap_index]
        cal_settings = self.settings_manager.get_flow_calibration_settings()
        
        # Determine units for user entry
        display_units = self.settings_manager.get_display_units()
        unit_label = "ml" if display_units == "metric" else "oz"
        
        # Load variables for the single tap
        self.single_cal_tap_index = tap_index
        self.single_cal_unit_label.set(unit_label)
        
        # Load last used value for the user entry field (saved value is float)
        stored_value = cal_settings['to_be_poured']
        self.single_cal_target_volume_var.set(f"{stored_value:.0f}")

        # Set default deduction state (No = False)
        self.single_cal_deduct_volume_var.set(False)

        # Reset measured values
        self.single_cal_measured_flow_var.set("0.00 L/min")
        self.single_cal_measured_pour_var.set("0.00")
        
        # Initialize the new factor fields
        self.single_cal_current_factor_var.set(f"{current_k_factor:.2f}") # Show current factor
        self.single_cal_new_factor_var.set("") # Start blank
        self._single_cal_calculated_new_factor = None # Reset internal state

        # Reset calibration state
        self._single_cal_in_progress = False
        self._single_cal_complete = False
        self._single_cal_pulse_count = 0
        self._single_cal_last_pour = 0.0

        popup = tk.Toplevel(self.root)
        popup.title(f"Calibrate Flow Sensor: {tap_name}")
        popup.geometry("550x410") 
        popup.transient(self.root)
        popup.grab_set()
        
        self._single_cal_popup_window = popup 
        
        # --- FIX: Pass parent_popup to the check_close handler ---
        popup.protocol("WM_DELETE_WINDOW", lambda p=popup, pp=parent_popup: self._single_cal_check_close(p, pp))

        main_frame = ttk.Frame(popup, padding="15"); 
        main_frame.pack(expand=True, fill="both")
        
        # Labeling the selected tap (Tap N)
        ttk.Label(main_frame, text=f"Tap to Calibrate: {tap_name}", font=('TkDefaultFont', 12, 'bold')).pack(anchor='w', pady=(0, 10))

        form_frame = ttk.Frame(main_frame);
        form_frame.pack(fill="x", pady=10)
        
        # --- Column Weights (snug fit layout) ---
        form_frame.grid_columnconfigure(0, weight=1); 
        form_frame.grid_columnconfigure(1, weight=0); 
        form_frame.grid_columnconfigure(2, weight=0);
        # ----------------------------------------

        entry_width = 10 
        row = 0
        
        # NEW Row 1: Deduct Measured Volume from keg assigned to Tap N? No / Yes
        ttk.Label(form_frame, text=f"Deduct Measured Volume from keg assigned to {tap_name}?").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        
        radio_frame = ttk.Frame(form_frame)
        radio_frame.grid(row=row, column=1, columnspan=2, sticky='w', padx=5, pady=5)
        
        tk.Radiobutton(radio_frame, text="No", variable=self.single_cal_deduct_volume_var, 
                       value=False).pack(side='left', padx=(0, 15))
        tk.Radiobutton(radio_frame, text="Yes", variable=self.single_cal_deduct_volume_var, 
                       value=True).pack(side='left')
        row += 1
        
        # Row 2: Volume Poured and Measured: [1000] [ml/oz]
        ttk.Label(form_frame, text="Volume Poured and Measured:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        
        # FIX 1: Set initial state to 'readonly' (inverted logic start)
        self._single_cal_volume_entry = ttk.Entry(form_frame, textvariable=self.single_cal_target_volume_var, 
                                                  width=entry_width, justify='center', state='readonly') 
        self._single_cal_volume_entry.grid(row=row, column=1, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, textvariable=self.single_cal_unit_label).grid(row=row, column=2, sticky='w')
        
        row += 1

        # Row 3: Measured Pour with Current Calibration: [0.00] [ml/oz]
        ttk.Label(form_frame, text="Measured Pour with Current Calibration:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, textvariable=self.single_cal_measured_pour_var, relief='sunken', anchor='w', width=entry_width).grid(row=row, column=1, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, textvariable=self.single_cal_unit_label).grid(row=row, column=2, sticky='w')
        row += 1

        # Row 4: Measured Flow Rate L/min: [0.00] [L/min]
        ttk.Label(form_frame, text="Measured Flow Rate L/min:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, textvariable=self.single_cal_measured_flow_var, relief='sunken', anchor='w', width=entry_width).grid(row=row, column=1, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, text="L/min").grid(row=row, column=2, sticky='w') 
        row += 1
        
        # Row 5: Current Calibration Factor
        ttk.Label(form_frame, text="Current Calibration Factor:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, textvariable=self.single_cal_current_factor_var, relief='sunken', anchor='w', width=entry_width).grid(row=row, column=1, sticky='w', padx=5, pady=5)
        row += 1
        
        # Row 6: New Calculated Calibration Factor
        ttk.Label(form_frame, text="New Calculated Calibration Factor:").grid(row=row, column=0, sticky='w', padx=5, pady=5)
        ttk.Label(form_frame, textvariable=self.single_cal_new_factor_var, relief='sunken', anchor='w', width=entry_width).grid(row=row, column=1, sticky='w', padx=5, pady=5)
        row += 1
        
        # Row 7: Buttons (Restored)
        button_frame = ttk.Frame(main_frame);
        button_frame.pack(fill="x", pady=20)
        
        self.single_cal_start_btn = ttk.Button(button_frame, text="Start Cal", width=12, command=self._single_cal_start)
        self.single_cal_start_btn.pack(side='left', padx=5, fill='x', expand=True)

        self.single_cal_stop_btn = ttk.Button(button_frame, text="Stop Cal", width=12, state=tk.DISABLED, command=self._single_cal_stop)
        self.single_cal_stop_btn.pack(side='left', padx=5, fill='x', expand=True)

        self.single_cal_set_btn = ttk.Button(button_frame, text="Set New Cal Factor", width=16, state=tk.DISABLED, command=lambda: self._single_cal_set(destroy_on_success=True))
        self.single_cal_set_btn.pack(side='left', padx=5, fill='x', expand=True)

        # Footer Button (Restored)
        buttons_frame = ttk.Frame(popup, padding="10"); 
        buttons_frame.pack(fill="x", side="bottom")
        
        # --- FIX: Pass parent_popup here too ---
        ttk.Button(buttons_frame, text="Close", command=lambda p=popup, pp=parent_popup: self._single_cal_check_close(p, pp)).pack(side="right")
        
        # NEW Help Button
        ttk.Button(buttons_frame, text="Help", width=8, 
                   command=lambda: self._open_help_popup("calibration")).pack(side="right", padx=5)
                   
        # --- MOVED: Dev Tools Button (Now here) ---
        ttk.Button(buttons_frame, text="Dev Tools", width=10, 
                   command=lambda: self._open_dev_warning_popup(popup)).pack(side="left", padx=5)
        
    def _single_cal_start(self):
        # Validation
        try:
            target_vol_display = float(self.single_cal_target_volume_var.get())
            if target_vol_display <= 0:
                messagebox.showerror("Input Error", "Target volume must be a positive number.", parent=self.single_cal_start_btn.winfo_toplevel())
                return
        except ValueError:
            messagebox.showerror("Input Error", "Target volume must be a valid number.", parent=self.single_cal_start_btn.winfo_toplevel())
            return
            
        if self._single_cal_in_progress: return
        
        # Save the current target volume to settings immediately
        self.settings_manager.save_flow_calibration_settings(to_be_poured_value=target_vol_display)
        
        self._single_cal_in_progress = True
        self._single_cal_complete = False
        
        # NEW: Clear the New Calculated Calibration Factor field and internal state
        self.single_cal_new_factor_var.set("")
        self._single_cal_calculated_new_factor = None
        
        self.single_cal_start_btn.config(state=tk.DISABLED)
        self.single_cal_stop_btn.config(state=tk.NORMAL)
        self.single_cal_set_btn.config(state=tk.DISABLED)
        
        # FIX 2: Make the Volume Poured and Measured field EDITABLE ('normal') once calibration starts
        if hasattr(self, '_single_cal_volume_entry') and self._single_cal_volume_entry:
             self._single_cal_volume_entry.config(state='normal')
        
        # Reset measured values on UI to 0.00
        self.single_cal_measured_flow_var.set("0.00 L/min")
        self.single_cal_measured_pour_var.set("0.00")
        
        # In a real app, this would call sensor_logic to start the flow cal mode for this tap.
        if hasattr(self, 'sensor_logic') and self.sensor_logic:
            self.sensor_logic.start_flow_calibration(self.single_cal_tap_index, self.single_cal_target_volume_var.get())
            
        print(f"Single Cal: Started for Tap {self.single_cal_tap_index + 1} with target {target_vol_display}")

    # MODIFIED: Added parameter for the deduction flag
    def _single_cal_set(self, destroy_on_success=False, primary_popup=None):
        
        # Check against the internal storage, not the UI field
        if self._single_cal_calculated_new_factor is None:
            # Check if button state matches internal state
            if self.single_cal_set_btn.cget('state') == tk.NORMAL:
                messagebox.showwarning("Calibration", "Please perform a full Start Cal / Stop Cal sequence first.", parent=self.single_cal_set_btn.winfo_toplevel() or primary_popup)
            return

        new_k_factor = self._single_cal_calculated_new_factor
        
        try:
            target_pour_str = self.single_cal_target_volume_var.get()
            target_pour_display_unit = float(target_pour_str)
            
            # DEDUCTION LOGIC REMOVED: It is now handled in _single_cal_stop()
            # The deducted_liters variable is no longer needed here.

            # 1. Save the new factor
            factors = self.settings_manager.get_flow_calibration_factors()
            factors[self.single_cal_tap_index] = new_k_factor
            self.settings_manager.save_flow_calibration_factors(factors)
            
            # 2. Save the last used 'to be poured' value
            self.settings_manager.save_flow_calibration_settings(to_be_poured_value=target_pour_display_unit)
            
            # 3. Update the 'Current Calibration Factor' display
            self.single_cal_current_factor_var.set(f"{new_k_factor:.2f}")
            
            # 4. Success message (Removed deduction information)
            messagebox.showinfo("Calibration Success", 
                                f"Tap {self.single_cal_tap_index + 1}: New Calibration Factor (K) saved: {new_k_factor:.2f} pulses/Liter.", 
                                parent=self.single_cal_set_btn.winfo_toplevel() or primary_popup)
            
            # 5. Disable button
            self.single_cal_set_btn.config(state=tk.DISABLED)
            
            # 6. Clear the new factor UI and internal state
            self.single_cal_new_factor_var.set("")
            self._single_cal_calculated_new_factor = None
            self._single_cal_complete = False # Clear the completed state
            
            # 7. Force UI refresh
            if hasattr(self, 'sensor_logic') and self.sensor_logic:
                 # This reload will show the new K-Factor and the volume after deduction (if it occurred in _single_cal_stop)
                 self.sensor_logic.force_recalculation()
                 
            # 8. Close the single calibration popup if requested (from the close check dialog)
            if destroy_on_success and primary_popup and primary_popup.winfo_exists():
                 self._single_cal_popup_window = None # Clear reference before destroying
                 primary_popup.destroy()
                 
        except ValueError:
            messagebox.showerror("Error", "Calibration values are invalid.", parent=self.single_cal_set_btn.winfo_toplevel() or primary_popup)
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}", parent=self.single_cal_set_btn.winfo_toplevel() or primary_popup)
            
    def _open_manually_enter_calibration_factor_popup(self, parent_popup):
        # The parent_popup is the main Flow Sensor Calibration screen
        
        # --- NEW: Get displayed taps count ---
        displayed_taps_count = self.settings_manager.get_displayed_taps()
        # -------------------------------------
        
        # Load current factors and notes for display
        factors = self.settings_manager.get_flow_calibration_factors()
        cal_settings = self.settings_manager.get_flow_calibration_settings()
        notes = cal_settings['notes']
        
        # Load vars for the popup - only reset for the displayed taps
        # MODIFIED: Only loop over displayed_taps_count
        for i in range(displayed_taps_count):
            self.flow_cal_current_factors[i].set(f"{factors[i]:.2f}")
            self.flow_cal_new_factor_entries[i].set("") # Clear entry field on open
        self.flow_cal_notes_var.set(notes)

        popup = tk.Toplevel(self.root)
        popup.title("Manually Enter Calibration Factor")
        # --- FIX: Reduced vertical size for visibility of Close button ---
        popup.geometry("550x450") 
        # -----------------------------------------------------------------
        popup.transient(self.root)
        popup.grab_set()

        main_frame = ttk.Frame(popup, padding="10"); 
        main_frame.pack(expand=True, fill="both")

        # --- Table Headers (Fixed layout) ---
        header_frame = ttk.Frame(main_frame);
        header_frame.pack(fill="x", pady=(0, 5))
        
        header_frame.grid_columnconfigure(0, weight=1, minsize=80)  # Flow Sensor
        header_frame.grid_columnconfigure(1, weight=1, minsize=100) # Current Cal Factor
        header_frame.grid_columnconfigure(2, weight=1, minsize=100) # New Cal Factor
        header_frame.grid_columnconfigure(3, weight=1, minsize=120) # Button
        
        ttk.Label(header_frame, text="Flow Sensor", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky='w', padx=5)
        ttk.Label(header_frame, text="Cal Factor", font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=1, sticky='ew')
        ttk.Label(header_frame, text="New Cal Factor", font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=2, sticky='ew')
        # ttk.Label(header_frame, text="(button)", font=('TkDefaultFont', 9, 'bold')).grid(row=0, column=3, sticky='ew')

        # --- Scrollable Table Rows ---
        # Nested frame for scrollable content only, excluding the Notes area
        table_container = ttk.Frame(main_frame)
        table_container.pack(fill="x", expand=False)
        
        canvas = tk.Canvas(table_container, borderwidth=0, height=250) # Fixed height for the rows
        v_scrollbar = ttk.Scrollbar(table_container, orient="vertical", command=canvas.yview)
        scroll_frame = ttk.Frame(canvas)
        
        v_scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="x", expand=True)
        canvas.configure(yscrollcommand=v_scrollbar.set)
        canvas_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        
        def on_canvas_resize(event): canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind('<Configure>', on_canvas_resize)
        
        scroll_frame.grid_columnconfigure(0, weight=1, minsize=80)
        scroll_frame.grid_columnconfigure(1, weight=1, minsize=100)
        scroll_frame.grid_columnconfigure(2, weight=1, minsize=100)
        scroll_frame.grid_columnconfigure(3, weight=1, minsize=120)

        # MODIFIED: Only loop over displayed_taps_count
        for i in range(displayed_taps_count):
             row_idx = i
             
             ttk.Label(scroll_frame, text=f"Tap {i+1}").grid(row=row_idx, column=0, sticky='w', padx=5, pady=2)
             
             # Current Cal Factor (Display only)
             ttk.Label(scroll_frame, textvariable=self.flow_cal_current_factors[i], anchor='center', relief='sunken').grid(row=row_idx, column=1, sticky='ew', padx=5)

             # New Cal Factor (User Entry)
             # --- NEW: Capture widget ---
             entry_widget = ttk.Entry(scroll_frame, textvariable=self.flow_cal_new_factor_entries[i], width=12, justify='center')
             entry_widget.grid(row=row_idx, column=2, sticky='ew', padx=5)
             
             # --- NEW: Focus on first item ---
             if i == 0:
                 entry_widget.focus_set()
             
             # Set New Factor Button
             ttk.Button(scroll_frame, text="Set New Factor", 
                        command=lambda idx=i, p=popup: self._set_new_calibration_factor(idx, p)).grid(row=row_idx, column=3, sticky='ew', padx=5)
        
        scroll_frame.update_idletasks()
        canvas.config(scrollregion=canvas.bbox("all"))

        # --- Notes Area ---
        notes_frame = ttk.Frame(main_frame); 
        # Pack below the table container, allow it to expand for the remaining space
        notes_frame.pack(fill="both", expand=True, pady=(5, 5))
        ttk.Label(notes_frame, text="Notes: (user-editable notes area)").pack(anchor='w')
        
        # Height set to 3 to save vertical space
        notes_text_widget = tk.Text(notes_frame, height=3, wrap=tk.WORD, relief='sunken', borderwidth=1)
        notes_text_widget.pack(fill="both", expand=True, pady=(2, 0))
        
        # Populate Text widget from StringVar
        notes_text_widget.insert(tk.END, self.flow_cal_notes_var.get())

        # --- Footer Buttons ---
        buttons_frame = ttk.Frame(popup, padding="10"); buttons_frame.pack(fill="x", side="bottom")
        
        # Close button calls a save method to persist notes
        ttk.Button(buttons_frame, text="Close", 
                   command=lambda p=popup, t=notes_text_widget: self._close_and_save_manual_cal_popup(p, t)).pack(side="right", padx=5)

        # NEW Help Button
        ttk.Button(buttons_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("calibration")).pack(side="right", padx=5)


    def _set_new_calibration_factor(self, tap_index, popup_window):
        new_factor_str = self.flow_cal_new_factor_entries[tap_index].get().strip()
        
        try:
            new_factor = float(new_factor_str)
            if new_factor <= 0:
                messagebox.showerror("Input Error", "Calibration factor must be a positive number.", parent=popup_window)
                return
            
            # 1. Update the list of factors
            factors = self.settings_manager.get_flow_calibration_factors()
            factors[tap_index] = new_factor
            
            # 2. Save the new factors list
            self.settings_manager.save_flow_calibration_factors(factors)
            
            # 3. Update the Current Cal Factor display on the popup
            self.flow_cal_current_factors[tap_index].set(f"{new_factor:.2f}")
            
            # 4. Clear the new factor entry field (as per implementation note)
            self.flow_cal_new_factor_entries[tap_index].set("")
            
            # 5. Force SensorLogic to update its factors
            if hasattr(self, 'sensor_logic') and self.sensor_logic:
                self.sensor_logic.force_recalculation()
                
            messagebox.showinfo("Success", f"Tap {tap_index + 1}: New Calibration Factor saved: {new_factor:.2f}.", parent=popup_window)
            
        except ValueError:
            messagebox.showerror("Input Error", "Calibration factor must be a valid number.", parent=popup_window)

    def _close_and_save_manual_cal_popup(self, popup_window, notes_text_widget):
        # 1. Get notes content
        new_notes = notes_text_widget.get("1.0", tk.END).strip()
        
        # 2. Save notes (only the notes value)
        self.settings_manager.save_flow_calibration_settings(notes=new_notes)
        
        # 3. Destroy popup
        popup_window.destroy()
        
    # --- System Settings Popup Logic (MODIFIED: Added Pour Volume) ---
    
    def _open_system_settings_popup(self, *args, **kwargs):
        popup = tk.Toplevel(self.root)
        popup.withdraw() 
        popup.title("System Settings")
        popup.transient(self.root)
        popup.protocol("WM_DELETE_WINDOW", popup.destroy)
        
        form_frame = ttk.Frame(popup, padding="10"); form_frame.pack(expand=True, fill="both")
        
        # 1. Load Stored Values
        pour_settings = self.settings_manager.get_pour_volume_settings()
        self.system_settings_pour_ml_var.set(str(pour_settings['metric_pour_ml']))
        self.system_settings_pour_oz_var.set(str(pour_settings['imperial_pour_oz']))

        def sync_input_to_storage(*args):
            current_unit = self.system_settings_unit_var.get()
            val = self.system_settings_pour_size_display_var.get()
            if "Metric" in current_unit:
                self.system_settings_pour_ml_var.set(val)
            else:
                self.system_settings_pour_oz_var.set(val)

        def update_ui_from_storage(event=None):
            self._update_conditional_threshold_units()
            current_unit = self.system_settings_unit_var.get()
            if "Metric" in current_unit:
                self.system_settings_pour_size_display_var.set(self.system_settings_pour_ml_var.get())
                self.system_settings_pour_unit_label_var.set("ml")
            else:
                self.system_settings_pour_size_display_var.set(self.system_settings_pour_oz_var.get())
                self.system_settings_pour_unit_label_var.set("oz (US Fluid)")

        try:
            if hasattr(self, '_pour_trace_id'):
                self.system_settings_pour_size_display_var.trace_remove('write', self._pour_trace_id)
        except: pass
        self._pour_trace_id = self.system_settings_pour_size_display_var.trace_add('write', sync_input_to_storage)

        row_idx = 0
        
        # --- UI Mode Selection (UPDATED) ---
        ttk.Label(form_frame, text="Tap Display Detail:").grid(row=row_idx, column=0, padx=5, pady=5, sticky="w")
        
        # NEW OPTIONS
        ui_mode_options = ["Detailed (All Info)", "Basic (Vital Stats Only)"]
        current_ui_mode = self.settings_manager.get_ui_mode()
        
        # Map internal key to display string
        display_value = ui_mode_options[0] if current_ui_mode == "detailed" else ui_mode_options[1]
        self.system_settings_ui_mode_var.set(display_value)
        
        ui_mode_dropdown = ttk.Combobox(form_frame, textvariable=self.system_settings_ui_mode_var, values=ui_mode_options, state="readonly", width=25)
        ui_mode_dropdown.grid(row=row_idx, column=1, padx=5, pady=5, sticky="ew"); row_idx += 1
        
        # --- Units ---
        ttk.Label(form_frame, text="Volume Display Units:").grid(row=row_idx, column=0, padx=5, pady=5, sticky="w")
        unit_options = ["Metric (liters/kilograms)", "US Imperial (gallons/pounds)"]
        current_units_setting = self.settings_manager.get_display_units()
        display_value = unit_options[0] if current_units_setting == "metric" else unit_options[1]
            
        self.system_settings_unit_var.set(display_value)
        
        unit_dropdown = ttk.Combobox(form_frame, textvariable=self.system_settings_unit_var, values=unit_options, state="readonly", width=25)
        unit_dropdown.grid(row=row_idx, column=1, padx=5, pady=5, sticky="ew"); row_idx += 1
        unit_dropdown.bind("<<ComboboxSelected>>", update_ui_from_storage)
        
        # --- Taps ---
        ttk.Label(form_frame, text="Taps to Display:").grid(row=row_idx, column=0, padx=5, pady=5, sticky="w")
        tap_count_options = [str(i) for i in range(1, self.num_sensors + 1)]
        self.system_settings_taps_var.set(str(self.settings_manager.get_displayed_taps()))
        ttk.Combobox(form_frame, textvariable=self.system_settings_taps_var, values=tap_count_options, state="readonly", width=5).grid(row=row_idx, column=1, padx=5, pady=5, sticky="w"); row_idx += 1
        
        if IS_RASPBERRY_PI_MODE:
            self.system_settings_autostart_var.set(self.settings_manager.get_autostart_enabled())
            ttk.Checkbutton(form_frame, text="Autostart KegLevel Monitor on Raspberry Pi startup/reboot", variable=self.system_settings_autostart_var).grid(row=row_idx, column=0, columnspan=2, padx=5, pady=5, sticky="w"); row_idx += 1
            self.system_settings_launch_workflow_var.set(self.settings_manager.get_launch_workflow_on_start())
            ttk.Checkbutton(form_frame, text="Launch KegLevel Workflow when KegLevel Monitor is started", variable=self.system_settings_launch_workflow_var).grid(row=row_idx, column=0, columnspan=2, padx=5, pady=5, sticky="w"); row_idx += 1
            
            is_terminal_enabled = self.settings_manager.get_terminal_setting_state()
            self.system_settings_terminal_var.set(is_terminal_enabled)
            ttk.Checkbutton(form_frame, text="Enable Terminal window in background (Debugging)", variable=self.system_settings_terminal_var).grid(row=row_idx, column=0, columnspan=2, padx=5, pady=5, sticky="w"); row_idx += 1

            self.system_settings_numlock_var.set(self.settings_manager.get_force_numlock())
            ttk.Checkbutton(form_frame, text="Force Num Lock ON while app is running", variable=self.system_settings_numlock_var).grid(row=row_idx, column=0, columnspan=2, padx=5, pady=5, sticky="w"); row_idx += 1

        ttk.Separator(form_frame, orient='horizontal').grid(row=row_idx, column=0, columnspan=2, sticky='ew', pady=10); row_idx += 1
        
        # --- Pour Volume ---
        ttk.Label(form_frame, text="Pour Volume", font=('TkDefaultFont', 10, 'bold')).grid(row=row_idx, column=0, columnspan=2, pady=(0, 5), sticky="w"); row_idx += 1
        pour_frame = ttk.Frame(form_frame); pour_frame.grid(row=row_idx, column=0, columnspan=2, sticky='ew'); 
        ttk.Label(pour_frame, text="Pour Size:", width=20, anchor="w").pack(side="left", padx=(5, 5), pady=5, anchor="w")
        ttk.Entry(pour_frame, textvariable=self.system_settings_pour_size_display_var, width=10).pack(side="left", padx=(0, 5), pady=5)
        ttk.Label(pour_frame, textvariable=self.system_settings_pour_unit_label_var).pack(side="left", padx=(0, 5), pady=5)
        row_idx += 1

        update_ui_from_storage()

        ttk.Separator(form_frame, orient='horizontal').grid(row=row_idx, column=0, columnspan=2, sticky='ew', pady=10); row_idx += 1
        
        # --- Temp Sensor ---
        ttk.Label(form_frame, text="Temperature Sensor Assignment", font=('TkDefaultFont', 10, 'bold')).grid(row=row_idx, column=0, columnspan=2, pady=(0, 5), sticky="w"); row_idx += 1
        
        available_sensors = []
        if hasattr(self, 'temp_logic') and self.temp_logic: available_sensors = self.temp_logic.detect_ds18b20_sensors()
        sensor_options = available_sensors if available_sensors else ["No sensors found"]

        ttk.Label(form_frame, text="Ambient Temp Sensor:").grid(row=row_idx, column=0, padx=5, pady=5, sticky="w")
        self.sensor_ambient_var.set(self.settings_manager.get_system_settings().get('ds18b20_ambient_sensor', ''))
        ttk.Combobox(form_frame, textvariable=self.sensor_ambient_var, values=sensor_options, state="readonly", width=30).grid(row=row_idx, column=1, padx=5, pady=5, sticky="ew"); row_idx += 1

        form_frame.grid_columnconfigure(1, weight=1)

        buttons_frame = ttk.Frame(popup, padding="10"); buttons_frame.pack(fill="x", side="bottom")
        ttk.Button(buttons_frame, text="Save", command=lambda p=popup: self._save_system_settings(p)).pack(side="right", padx=5)
        ttk.Button(buttons_frame, text="Cancel", command=popup.destroy).pack(side="right", padx=5)
        ttk.Button(buttons_frame, text="Help", width=8, command=lambda: self._open_help_popup("system_settings")).pack(side="right", padx=5)
        ttk.Button(buttons_frame, text="Dev Tools", width=10, command=lambda: self._open_dev_warning_popup(popup)).pack(side="left", padx=5)

        self._center_popup(popup, 450, 480)
        popup.grab_set()
        if ui_mode_dropdown: ui_mode_dropdown.focus_set()

    def _save_system_settings(self, popup_window):
        selected_unit_display = self.system_settings_unit_var.get()
        
        try:
            new_pour_ml = int(self.system_settings_pour_ml_var.get())
            new_pour_oz = int(self.system_settings_pour_oz_var.get())
            if new_pour_ml <= 0 or new_pour_oz <= 0:
                 messagebox.showerror("Input Error", "Pour volume must be a positive whole number.", parent=popup_window)
                 return
            self.settings_manager.save_pour_volume_settings(new_pour_ml, new_pour_oz)
        except ValueError:
            messagebox.showerror("Input Error", "Pour volume fields must be valid whole numbers.", parent=popup_window)
            return
        
        new_unit_setting = "metric" if "Metric" in selected_unit_display else "imperial"
        
        # --- NEW: Map Display String -> Internal Key ---
        selected_ui_mode_display = self.system_settings_ui_mode_var.get()
        new_ui_mode_setting = "detailed" if "Detailed" in selected_ui_mode_display else "basic"
        # -----------------------------------------------
        
        new_ambient_sensor_id = self.sensor_ambient_var.get()
        new_autostart_enabled = self.system_settings_autostart_var.get()
        new_launch_workflow_on_start = self.system_settings_launch_workflow_var.get()
        
        self.settings_manager.save_display_units(new_unit_setting)
        self.settings_manager.save_ui_mode(new_ui_mode_setting) 
        self.settings_manager.set_ds18b20_ambient_sensor(new_ambient_sensor_id)
        
        old_autostart_enabled = self.settings_manager.get_autostart_enabled()
        self.settings_manager.save_autostart_enabled(new_autostart_enabled)
        
        if IS_RASPBERRY_PI_MODE and old_autostart_enabled != new_autostart_enabled:
            action = 'add' if new_autostart_enabled else 'remove'
            manage_autostart_file(action)
        
        if IS_RASPBERRY_PI_MODE:
            enable_terminal = self.system_settings_terminal_var.get()
            success, msg = self.settings_manager.save_terminal_setting_state(enable_terminal)
            if not success: messagebox.showwarning("Settings Warning", f"Could not update Terminal setting:\n{msg}", parent=popup_window)

        if IS_RASPBERRY_PI_MODE:
            new_numlock_enabled = self.system_settings_numlock_var.get()
            self.settings_manager.save_force_numlock(new_numlock_enabled)
            if new_numlock_enabled:
                try: subprocess.Popen(['numlockx', 'on'])
                except Exception: pass

        self.settings_manager.save_launch_workflow_on_start(new_launch_workflow_on_start)
        
        try:
            new_displayed_taps = int(self.system_settings_taps_var.get())
            self.settings_manager.save_displayed_taps(new_displayed_taps)
            
            if hasattr(self, 'temp_logic') and self.temp_logic:
                self.temp_logic.get_assigned_sensor() 
                if self.temp_logic.ambient_sensor and self.temp_logic.ambient_sensor != 'unassigned':
                    temp_f = self.temp_logic.read_ambient_temperature()
                    if temp_f is not None:
                        display_units = self.settings_manager.get_display_units()
                        if display_units == "imperial": self.update_temperature_display(temp_f, "F")
                        else: self.update_temperature_display((temp_f - 32) * (5/9), "C")
                        self.temp_logic.last_known_temp_f = temp_f
                    else: self.update_temperature_display(None, "No Sensor")
                else:
                    self.update_temperature_display(None, "No Sensor")
                    self.temp_logic.last_known_temp_f = None
                if not self.temp_logic._running: self.temp_logic.start_monitoring()

            print("UIManager: System settings saved.")
            popup_window.destroy()

            # Dynamic UI Refresh (Mode change logic)
            mode_changed = (new_ui_mode_setting != self.ui_mode)
            if mode_changed:
                self.rebuild_ui()
            else:
                self._refresh_ui_for_settings_or_resume()
                 
        except ValueError: messagebox.showerror("Input Error", "Invalid number for taps display.", parent=popup_window)

    def _open_dev_warning_popup(self, parent_popup):
        """Shows the warning disclaimer before accessing Dev Tools."""
        warn_popup = tk.Toplevel(parent_popup)
        warn_popup.title("Developer Tools Warning")
        
        self._center_popup(warn_popup, 500, 280)
        warn_popup.transient(parent_popup)
        
        # --- FIX: Moved grab_set to end ---
        
        def restore_parent():
            warn_popup.destroy()
            if parent_popup.winfo_exists():
                parent_popup.grab_set()
                parent_popup.focus_set()

        warn_popup.protocol("WM_DELETE_WINDOW", restore_parent)

        main_frame = ttk.Frame(warn_popup, padding="20")
        main_frame.pack(expand=True, fill="both")

        ttk.Label(main_frame, text="⚠ WARNING", foreground="red", font=('TkDefaultFont', 14, 'bold')).pack(pady=(0, 10))
        
        msg = (
            "The tools on this popup are for developer use only. "
            "Using these tools may cause the app to become unstable or unusable. "
            "This could require full deletion and reinstallation of the app.\n\n"
            "DO NOT proceed unless you are willing to assume these risks."
        )
        ttk.Label(main_frame, text=msg, wraplength=450, justify="center").pack(pady=(0, 20))

        btn_frame = ttk.Frame(warn_popup, padding="10")
        btn_frame.pack(fill="x", side="bottom")
        
        # Proceed: destroys current, opens next (which takes grab), so we don't restore parent yet
        def proceed():
            warn_popup.destroy()
            self._open_dev_tools_popup(parent_popup)

        ttk.Button(btn_frame, text="Proceed", command=proceed).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="Cancel", command=restore_parent).pack(side="right", padx=10)
        
        # --- FIX: Grab last ---
        warn_popup.grab_set()

    def _open_dev_tools_popup(self, parent_popup):
        """The actual simulation control window."""
        dev_popup = tk.Toplevel(parent_popup)
        dev_popup.title("Developer Tools - Simulation")
        self._center_popup(dev_popup, 400, 350)
        dev_popup.transient(parent_popup)
        
        # --- FIX: Moved grab_set to end ---

        def restore_parent():
            dev_popup.destroy()
            if parent_popup.winfo_exists():
                parent_popup.grab_set()
                parent_popup.focus_set()

        dev_popup.protocol("WM_DELETE_WINDOW", restore_parent)

        main_frame = ttk.Frame(dev_popup, padding="20")
        main_frame.pack(expand=True, fill="both")

        ttk.Label(main_frame, text="Virtual Pour Simulator", font=('TkDefaultFont', 12, 'bold')).pack(pady=(0, 15))

        # 1. Tap Selection
        select_frame = ttk.Frame(main_frame); select_frame.pack(fill="x", pady=5)
        ttk.Label(select_frame, text="Select Tap:", width=15).pack(side="left")
        
        tap_options = [f"Tap {i+1}" for i in range(self.num_sensors)]
        tap_var = tk.StringVar(value=tap_options[0])
        ttk.Combobox(select_frame, textvariable=tap_var, values=tap_options, state="readonly", width=10).pack(side="left")

        # 2. Volume (Unit-Aware)
        display_units = self.settings_manager.get_display_units()
        is_metric = (display_units == "metric")
        
        vol_frame = ttk.Frame(main_frame); vol_frame.pack(fill="x", pady=5)
        ttk.Label(vol_frame, text="Volume to Pour:", width=15).pack(side="left")
        
        # Set defaults based on unit system
        default_vol = "500" if is_metric else "16"
        unit_label = "ml" if is_metric else "oz"
        
        vol_var = tk.StringVar(value=default_vol) 
        ttk.Entry(vol_frame, textvariable=vol_var, width=10).pack(side="left")
        ttk.Label(vol_frame, text=unit_label).pack(side="left", padx=5)

        # 3. Flow Rate (Always L/min)
        rate_frame = ttk.Frame(main_frame); rate_frame.pack(fill="x", pady=5)
        ttk.Label(rate_frame, text="Flow Rate:", width=15).pack(side="left")
        
        rate_var = tk.StringVar(value="2.00") # Default 2.0 LPM
        ttk.Entry(rate_frame, textvariable=rate_var, width=10).pack(side="left")
        ttk.Label(rate_frame, text="L/min").pack(side="left", padx=5)
        
        # 4. Deduct Volume Checkbox
        deduct_frame = ttk.Frame(main_frame); deduct_frame.pack(fill="x", pady=(10, 5))
        deduct_var = tk.BooleanVar(value=True) # Default Checked
        ttk.Checkbutton(deduct_frame, text="Deduct measured volume from tap?", variable=deduct_var).pack(side="left")

        # 5. Action
        status_label = ttk.Label(main_frame, text="", foreground="blue")
        status_label.pack(pady=10)

        def do_sim():
            try:
                # Parse inputs
                tap_idx = int(tap_var.get().split(" ")[1]) - 1
                user_vol = float(vol_var.get())
                rate = float(rate_var.get())
                should_deduct = deduct_var.get()
                
                if user_vol <= 0 or rate <= 0:
                    messagebox.showerror("Error", "Volume and Rate must be positive.", parent=dev_popup)
                    return

                # Convert input to Liters for the Logic layer
                if is_metric:
                    vol_liters = user_vol / 1000.0
                else:
                    vol_liters = user_vol * OZ_TO_LITERS

                # Send command to logic
                if hasattr(self, 'sensor_logic') and self.sensor_logic:
                    self.sensor_logic.simulate_pour(tap_idx, vol_liters, rate, deduct_volume=should_deduct)
                    action_text = "DEDUCTING" if should_deduct else "TEST ONLY (Reverting)"
                    
                    # Update status with user's units
                    status_label.config(text=f"Simulating {user_vol} {unit_label} on Tap {tap_idx+1} ({action_text})...", foreground="green")
                else:
                     status_label.config(text="Sensor Logic not connected.", foreground="red")
                     
            except ValueError:
                messagebox.showerror("Error", "Invalid numeric input.", parent=dev_popup)

        btn_frame = ttk.Frame(dev_popup, padding="10")
        btn_frame.pack(fill="x", side="bottom")
        
        ttk.Button(btn_frame, text="Start Simulation", command=do_sim).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Close", command=restore_parent).pack(side="right", padx=5)
        
        # --- FIX: Grab last ---
        dev_popup.grab_set()
        
    def _update_conditional_threshold_units(self):
        current_units = self.settings_manager.get_display_units()
        
        try:
            current_volume_value_str = self.msg_conditional_threshold_var.get()
            current_volume_value = float(current_volume_value_str) if current_volume_value_str else None
            current_low_temp_str = self.msg_conditional_low_temp_var.get()
            current_low_temp = float(current_low_temp_str) if current_low_temp_str else None
            current_high_temp_str = self.msg_conditional_high_temp_var.get()
            current_high_temp = float(current_high_temp_str) if current_high_temp_str else None
        except ValueError: current_volume_value = None; current_low_temp = None; current_high_temp = None

        if current_units == "imperial":
            self.msg_conditional_threshold_units_var.set("Gallons")
            if self.last_units_for_threshold == "metric" and current_volume_value is not None:
                self.msg_conditional_threshold_var.set(f"{current_volume_value * LITERS_TO_GALLONS:.2f}")

            self.msg_conditional_threshold_label_text.set("Notify when temperature is outside the range (low-high F)")
            if self.last_units_for_threshold == "metric":
                if current_low_temp is not None: self.msg_conditional_low_temp_var.set(f"{(current_low_temp * 9/5) + 32:.1f}")
                if current_high_temp is not None: self.msg_conditional_high_temp_var.set(f"{(current_high_temp * 9/5) + 32:.1f}")
        else:
            self.msg_conditional_threshold_units_var.set("Liters")
            if self.last_units_for_threshold == "imperial" and current_volume_value is not None:
                self.msg_conditional_threshold_var.set(f"{current_volume_value / LITERS_TO_GALLONS:.2f}")
            
            self.msg_conditional_threshold_label_text.set("Notify when temperature is outside the range (low-high C)")
            if self.last_units_for_threshold == "imperial":
                if current_low_temp is not None: self.msg_conditional_low_temp_var.set(f"{(current_low_temp - 32) * (5/9):.1f}")
                if current_high_temp is not None: self.msg_conditional_high_temp_var.set(f"{(current_high_temp - 32) * (5/9):.1f}")

        self.last_units_for_threshold = current_units

    def _toggle_email_fields_state(self, *args):
        """
        Enables or disables all fields based on the state of the master checkboxes.
        """
        try:
            push_enabled = self.msg_push_enabled_var.get()
            cond_enabled = self.msg_conditional_enabled_var.get()
            req_enabled = self.status_req_enable_var.get()
            # --- NEW ---
            update_enabled = self.msg_notify_on_update_var.get()

            # 1. Outbound Alerts Section (Shared Recipient)
            # Enabled if ANY outbound notification is ON
            outbound_active = push_enabled or cond_enabled or update_enabled
            outbound_state = 'normal' if outbound_active else 'disabled'
            
            if hasattr(self, 'shared_recipient_entry'):
                self.shared_recipient_entry.config(state=outbound_state)

            # 2. Push Specific
            push_state = 'normal' if push_enabled else 'disabled'
            if hasattr(self, 'freq_dropdown'):
                self.freq_dropdown.config(state=push_state)
                
            # 3. Conditional Specific
            cond_state = 'normal' if cond_enabled else 'disabled'
            if hasattr(self, 'cond_vol_entry'): self.cond_vol_entry.config(state=cond_state)
            if hasattr(self, 'cond_low_entry'): self.cond_low_entry.config(state=cond_state)
            if hasattr(self, 'cond_high_entry'): self.cond_high_entry.config(state=cond_state)

            # 4. Inbound Control Section
            req_state = 'normal' if req_enabled else 'disabled'
            if hasattr(self, 'req_sender_entry'):
                self.req_sender_entry.config(state=req_state)

            # 5. RPi Config Tab (Dependencies)
            
            # SMTP/Creds needed if ANY feature is ON
            smtp_needed = push_enabled or cond_enabled or req_enabled or update_enabled
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
            
    def _save_message_settings(self, popup_window):
        try:
            # 1. Validate Ports
            push_on = self.msg_push_enabled_var.get()
            cond_on = self.msg_conditional_enabled_var.get()
            req_on = self.status_req_enable_var.get()
            update_on = self.msg_notify_on_update_var.get()
            
            smtp_port_val = self.msg_smtp_port_var.get()
            smtp_port_to_save = int(smtp_port_val) if smtp_port_val.strip() else ""
            
            # Check if any outbound feature is on
            any_outbound = push_on or cond_on or update_on
            
            if (any_outbound or req_on) and smtp_port_to_save and not (0 < smtp_port_to_save <= 65535):
                messagebox.showerror("Input Error", "SMTP Port must be 1-65535.", parent=popup_window); return

            imap_port_val = self.status_req_imap_port_var.get()
            imap_port_to_save = int(imap_port_val) if imap_port_val.strip() else ""
            
            if req_on and imap_port_to_save and not (0 < imap_port_to_save <= 65535):
                messagebox.showerror("Input Error", "IMAP Port must be 1-65535.", parent=popup_window); return

            # 2. Parse Conditional Thresholds
            cond_threshold_val = self.msg_conditional_threshold_var.get()
            low_temp_val = self.msg_conditional_low_temp_var.get()
            high_temp_val = self.msg_conditional_high_temp_var.get()
            
            try:
                cond_threshold_display = float(cond_threshold_val) if cond_threshold_val else None
                low_temp_display = float(low_temp_val) if low_temp_val else None
                high_temp_display = float(high_temp_val) if high_temp_val else None
            except ValueError: 
                messagebox.showerror("Input Error", "Conditional Thresholds must be valid numbers.", parent=popup_window); return
            
            cond_threshold_liters = cond_threshold_display
            if self.settings_manager.get_display_units() == "imperial" and cond_threshold_liters is not None:
                cond_threshold_liters = cond_threshold_liters / LITERS_TO_GALLONS

            low_temp_f = low_temp_display; high_temp_f = high_temp_display
            if self.settings_manager.get_display_units() == "metric":
                if low_temp_f is not None: low_temp_f = (low_temp_f * 9/5) + 32
                if high_temp_f is not None: high_temp_f = (high_temp_f * 9/5) + 32

            # 3. Construct Settings Objects
            push_type = "Email" if push_on else "None"
            push_settings = {
                "notification_type": push_type, 
                "frequency": self.msg_frequency_var.get(),
                "server_email": self.msg_server_email_var.get().strip(), 
                "server_password": self.msg_server_password_var.get(),
                "email_recipient": self.msg_email_recipient_var.get().strip(), 
                "smtp_server": self.msg_smtp_server_var.get().strip(),
                "smtp_port": smtp_port_to_save,
                "sms_number": "", "sms_carrier_gateway": "",
                # --- SAVE NEW SETTING ---
                "notify_on_update": update_on
                # ------------------------
            }

            cond_type = "Email" if cond_on else "None"
            cond_settings = {
                "notification_type": cond_type, 
                "threshold_liters": cond_threshold_liters,
                "low_temp_f": low_temp_f, 
                "high_temp_f": high_temp_f,
                "sent_notifications": self.settings_manager.get_conditional_notification_settings().get("sent_notifications", [False] * self.num_sensors),
                "temp_sent_timestamps": self.settings_manager.get_conditional_notification_settings().get("temp_sent_timestamps", []),
                "error_reported_times": self.settings_manager.get_conditional_notification_settings().get("error_reported_times", {})
            }
            
            status_settings = {
                "enable_status_request": req_on,
                "authorized_sender": self.status_req_sender_var.get().strip(),
                "rpi_email_address": self.msg_server_email_var.get().strip(),
                "rpi_email_password": self.msg_server_password_var.get(),
                "imap_server": self.status_req_imap_server_var.get().strip(),
                "imap_port": imap_port_to_save,
                "smtp_server": self.msg_smtp_server_var.get().strip(),
                "smtp_port": smtp_port_to_save
            }

            # 4. Save All
            self.settings_manager.save_push_notification_settings(push_settings)
            self.settings_manager.save_conditional_notification_settings(cond_settings)
            self.settings_manager.save_status_request_settings(status_settings)
            
            print("UIManager: Message settings saved.")
            
            # 5. Trigger Service Reschedule
            if hasattr(self, 'notification_service') and self.notification_service: 
                self.notification_service.force_reschedule()
                self.notification_service.stop_status_request_listener()
                self.notification_service.start_status_request_listener()

            if hasattr(self, 'sensor_logic') and self.sensor_logic: 
                self.sensor_logic.force_recalculation()

            popup_window.destroy()
            
        except ValueError: messagebox.showerror("Input Error", "Port must be a valid number.", parent=popup_window)
        except Exception as e: messagebox.showerror("Error", f"An unexpected error occurred while saving: {e}", parent=popup_window)

    def _execute_reset_log_and_refresh(self, popup_window):
        if messagebox.askyesno("Confirm Reset", "Are you sure you want to reset all temperature log data? This cannot be undone.", parent=popup_window):
            if hasattr(self, 'temp_logic') and self.temp_logic:
                self.temp_logic.reset_log()
                messagebox.showinfo("Log Reset", "Temperature log has been reset.", parent=popup_window)
                popup_window.destroy()
                self._open_temperature_log_popup() 
            else: messagebox.showerror("Error", "Temperature logic service is not available.", parent=popup_window)

    def _open_temperature_log_popup(self):
        popup = tk.Toplevel(self.root); popup.title("Temperature Log"); popup.geometry("450x450"); popup.transient(self.root); popup.grab_set()

        # Get Data
        log_data = self.temp_logic.get_temperature_log() if hasattr(self, 'temp_logic') and self.temp_logic else {"keg": {}, "rpi": {}}
        unit_char = "F" if self.settings_manager.get_display_units() == "imperial" else "C"

        frame = ttk.Frame(popup, padding="15"); frame.pack(expand=True, fill="both")

        # --- SECTION 1: KEGERATOR TEMP ---
        ttk.Label(frame, text="Kegerator Temperature Records", font=('TkDefaultFont', 12, 'bold')).pack(pady=(0, 10))

        headers_frame = ttk.Frame(frame); headers_frame.pack(fill='x')
        ttk.Label(headers_frame, text="Period", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, padx=5, pady=2, sticky='w')
        ttk.Label(headers_frame, text="High", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=1, padx=5, pady=2, sticky='w')
        ttk.Label(headers_frame, text="Low", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=2, padx=5, pady=2, sticky='w')
        ttk.Label(headers_frame, text="Average", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=3, padx=5, pady=2, sticky='w')

        keg_periods = [("Day", log_data["keg"].get("day", {})), ("Week", log_data["keg"].get("week", {})), ("Month", log_data["keg"].get("month", {}))]

        for i, (period_name, data) in enumerate(keg_periods):
            row = i + 1
            ttk.Label(headers_frame, text=period_name).grid(row=row, column=0, padx=5, pady=2, sticky='w')
            high_val = f"{data.get('high'):.1f} {unit_char}" if data.get('high') is not None else "--.-"
            low_val = f"{data.get('low'):.1f} {unit_char}" if data.get('low') is not None else "--.-"
            avg_val = f"{data.get('avg'):.1f} {unit_char}" if data.get('avg') is not None else "--.-"
            ttk.Label(headers_frame, text=high_val).grid(row=row, column=1, padx=5, pady=2, sticky='w')
            ttk.Label(headers_frame, text=low_val).grid(row=row, column=2, padx=5, pady=2, sticky='w')
            ttk.Label(headers_frame, text=avg_val).grid(row=row, column=3, padx=5, pady=2, sticky='w')

        for col_idx in range(4): headers_frame.grid_columnconfigure(col_idx, weight=1)

        # --- SEPARATOR ---
        ttk.Separator(frame, orient='horizontal').pack(fill='x', pady=20)

        # --- SECTION 2: RPi INTERNAL TEMP ---
        ttk.Label(frame, text="RPi Internal Temperature Records", font=('TkDefaultFont', 12, 'bold')).pack(pady=(0, 10))

        rpi_headers_frame = ttk.Frame(frame); rpi_headers_frame.pack(fill='x')
        ttk.Label(rpi_headers_frame, text="Period", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, padx=5, pady=2, sticky='w')
        ttk.Label(rpi_headers_frame, text="High", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=1, padx=5, pady=2, sticky='w')
        ttk.Label(rpi_headers_frame, text="Low", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=2, padx=5, pady=2, sticky='w')
        ttk.Label(rpi_headers_frame, text="Average", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=3, padx=5, pady=2, sticky='w')

        rpi_periods = [("Day", log_data["rpi"].get("day", {})), ("Week", log_data["rpi"].get("week", {})), ("Month", log_data["rpi"].get("month", {}))]

        for i, (period_name, data) in enumerate(rpi_periods):
            row = i + 1
            ttk.Label(rpi_headers_frame, text=period_name).grid(row=row, column=0, padx=5, pady=2, sticky='w')
            high_val = f"{data.get('high'):.1f} {unit_char}" if data.get('high') is not None else "--.-"
            low_val = f"{data.get('low'):.1f} {unit_char}" if data.get('low') is not None else "--.-"
            avg_val = f"{data.get('avg'):.1f} {unit_char}" if data.get('avg') is not None else "--.-"
            ttk.Label(rpi_headers_frame, text=high_val).grid(row=row, column=1, padx=5, pady=2, sticky='w')
            ttk.Label(rpi_headers_frame, text=low_val).grid(row=row, column=2, padx=5, pady=2, sticky='w')
            ttk.Label(rpi_headers_frame, text=avg_val).grid(row=row, column=3, padx=5, pady=2, sticky='w')

        for col_idx in range(4): rpi_headers_frame.grid_columnconfigure(col_idx, weight=1)

        # --- FOOTER ---
        button_frame = ttk.Frame(popup); button_frame.pack(fill='x', pady=10, side="bottom")
        ttk.Button(button_frame, text="Reset Log", command=lambda p=popup: self._execute_reset_log_and_refresh(p)).pack(side='left', padx=10)
        ttk.Button(button_frame, text="Close", command=popup.destroy).pack(side='right', padx=10)
        
        # NEW Help Button
        ttk.Button(button_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("temp_log")).pack(side="right", padx=5)

    # --- Reset to Defaults Popup Logic (Unchanged) ---
    
    def _open_reset_to_defaults_popup(self):
        popup = tk.Toplevel(self.root); popup.title("Reset All Settings"); popup.geometry("450x180"); popup.transient(self.root); popup.grab_set()

        main_frame = ttk.Frame(popup, padding="15"); main_frame.pack(expand=True, fill="both")

        message_text = ("Reset clears ALL settings including message settings, keg settings, "
                        "system settings, and the **entire Beverage Library**. ALL are reset to their default values.")
        ttk.Label(main_frame, text=message_text, wraplength=400, justify="left").pack(pady=(0, 20))

        buttons_frame = ttk.Frame(popup, padding="10"); buttons_frame.pack(fill="x", side="bottom")

        ttk.Button(buttons_frame, text="Cancel", command=popup.destroy).pack(side="right", padx=(10,0))
        ttk.Button(buttons_frame, text="Save (Reset)", command=lambda p=popup: self._execute_reset_to_defaults(p)).pack(side="right", padx=(0,10))
        
        # NEW Help Button
        ttk.Button(buttons_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("section:reset_to_defaults")).pack(side="right", padx=5)

    def _execute_reset_to_defaults(self, popup_window):
        if not messagebox.askyesno("Confirm Reset",
                                   "Are you sure you want to reset ALL settings (including the Beverage Library) to their original defaults?\nThis action cannot be undone.",
                                   parent=popup_window): return

        print("UIManager: Executing reset to default settings...")
        
        autostart_was_enabled = self.settings_manager.get_autostart_enabled()
        if IS_RASPBERRY_PI_MODE and autostart_was_enabled:
            manage_autostart_file('remove')
        
        if self.settings_manager: self.settings_manager.reset_all_settings_to_defaults()

        self._load_initial_ui_settings()
        self._refresh_ui_for_settings_or_resume()

        if hasattr(self, 'notification_service') and self.notification_service: self.notification_service.force_reschedule()

        messagebox.showinfo("Settings Reset", "All settings have been reset to their default values.", parent=self.root)
        popup_window.destroy()

    # --- Wiring Diagram Popup Logic (Unchanged) ---
    def _open_wiring_diagram_popup(self):
        try:
            # 1. Scan for Wiring Images (Carousel Logic)
            assets_dir = os.path.join(self.base_dir, "assets")
            if not os.path.exists(assets_dir):
                messagebox.showerror("Error", f"Assets directory not found:\n{assets_dir}", parent=self.root)
                return

            all_files = os.listdir(assets_dir)
            wiring_images = sorted([f for f in all_files if f.startswith("wiring") and f.endswith(".gif")])
            
            if not wiring_images:
                messagebox.showerror("Error", "No wiring diagram images found (wiring*.gif).", parent=self.root)
                return

            # State variables for carousel
            current_image_index = 0
            total_images = len(wiring_images)
            
            # 2. Check for PDF File
            pdf_filename = "Wiring-Diagram.pdf"
            pdf_path = os.path.join(assets_dir, pdf_filename)
            has_pdf = os.path.exists(pdf_path)

            # 3. Create Popup
            popup = tk.Toplevel(self.root)
            popup.title("Wiring Diagram")
            
            # Set explicit size to prevent clipping
            self._center_popup(popup, 800, 600)
            
            popup.transient(self.root)
            popup.grab_set()

            # Main Frame
            main_frame = ttk.Frame(popup, padding="10")
            main_frame.pack(expand=True, fill="both")

            # --- IMAGE AREA ---
            image_container = ttk.Frame(main_frame)
            image_container.pack(expand=True, fill="both", padx=10, pady=10)
            
            image_label = ttk.Label(image_container)
            image_label.pack(anchor="center", expand=True)
            
            self._current_wiring_image_obj = None 

            def load_image(index):
                try:
                    file_name = wiring_images[index]
                    full_path = os.path.join(assets_dir, file_name)
                    img_obj = tk.PhotoImage(file=full_path)
                    image_label.configure(image=img_obj)
                    image_label.image = img_obj 
                    self._current_wiring_image_obj = img_obj 
                    
                    # Update Label
                    page_label.config(text=f"Page {index + 1} of {total_images}")
                    
                    # Update Buttons
                    prev_btn.config(state="normal" if index > 0 else "disabled")
                    next_btn.config(state="normal" if index < total_images - 1 else "disabled")
                    
                except Exception as e:
                    image_label.config(text=f"Error loading {file_name}:\n{e}")

            # --- NAVIGATION CONTROLS ---
            nav_frame = ttk.Frame(main_frame)
            nav_frame.pack(fill="x", pady=(0, 10))
            
            def go_prev():
                nonlocal current_image_index
                if current_image_index > 0:
                    current_image_index -= 1
                    load_image(current_image_index)

            def go_next():
                nonlocal current_image_index
                if current_image_index < total_images - 1:
                    current_image_index += 1
                    load_image(current_image_index)

            center_nav_container = ttk.Frame(nav_frame)
            center_nav_container.pack(anchor="center")

            prev_btn = ttk.Button(center_nav_container, text="<< Prev", command=go_prev)
            prev_btn.pack(side="left", padx=5)
            
            page_label = ttk.Label(center_nav_container, text=f"Page 1 of {total_images}", font=('TkDefaultFont', 10, 'bold'))
            page_label.pack(side="left", padx=10)
            
            next_btn = ttk.Button(center_nav_container, text="Next >>", command=go_next)
            next_btn.pack(side="left", padx=5)
            
            if total_images <= 1:
                nav_frame.pack_forget()

            # --- FOOTER ACTIONS ---
            footer_frame = ttk.Frame(popup, padding=(10, 0, 10, 10))
            footer_frame.pack(fill="x", side="bottom")

            # Close Button (Right)
            ttk.Button(footer_frame, text="Close", command=popup.destroy).pack(side="right", padx=5)
            
            # NEW Help Button
            ttk.Button(footer_frame, text="Help", width=8,
                       command=lambda: self._open_help_popup("wiring")).pack(side="right", padx=5)

            # PDF Actions (Left)
            if has_pdf:
                ttk.Button(footer_frame, text="Open PDF", 
                           command=lambda: self._open_wiring_pdf(pdf_path, popup)).pack(side="left", padx=5)

            # Initial Load
            load_image(0)

        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred while opening wiring diagram:\n{e}", parent=self.root)

    def _open_wiring_pdf(self, source_path, parent_popup):
        """Helper to open the PDF in the system default viewer (xdg-open)."""
        try:
            # Use xdg-open to launch the default application for PDF
            subprocess.Popen(['xdg-open', source_path], 
                             stderr=subprocess.DEVNULL, 
                             stdout=subprocess.DEVNULL)
        except Exception as e:
            messagebox.showerror("Open Error", f"Could not launch PDF viewer:\n{e}", parent=parent_popup)
    
    def _on_link_click(self, url):
        """
        Handles link clicks.
        - If url starts with 'section:', loads that section into the EXISTING window (no flicker).
        - If url starts with 'pdf:', opens the PDF from the assets folder in the system viewer.
        - Otherwise, opens in the default web browser.
        """
        if url.startswith("section:"):
            section_name = url.split(":", 1)[1]
            
            # DIRECTLY load the new section. 
            # Do NOT destroy the window here. _open_help_popup will handle the refresh.
            self._open_help_popup(section_name)
            
        elif url.startswith("pdf:"):
            # Extract filename from "pdf:filename.pdf"
            filename = url.split(":", 1)[1]
            
            # Construct full path to assets directory
            pdf_path = os.path.join(self.base_dir, "assets", filename)
            
            if os.path.exists(pdf_path):
                try:
                    # Use xdg-open to launch the default application for PDF (Evince/qpdfview)
                    subprocess.Popen(['xdg-open', pdf_path], 
                                     stderr=subprocess.DEVNULL, 
                                     stdout=subprocess.DEVNULL)
                except Exception as e:
                    # Try to find a parent window for the error, fallback to root
                    parent = self.root.focus_get().winfo_toplevel() if self.root.focus_get() else self.root
                    messagebox.showerror("Open Error", f"Could not launch PDF viewer:\n{e}", parent=parent)
            else:
                parent = self.root.focus_get().winfo_toplevel() if self.root.focus_get() else self.root
                messagebox.showerror("File Not Found", f"The requested PDF file was not found:\n{filename}\n\nExpected at:\n{pdf_path}", parent=parent)

        else:
            try:
                webbrowser.open_new(url)
            except Exception as e:
                print(f"Error opening link: {e}")
    def _get_help_section(self, section_name):
        """
        Loads the consolidated help.md file and extracts a specific section.
        Sections are defined by [SECTION: section_name].
        """
        try:
            # Path is src/assets/help.md
            help_file_path = os.path.join(self.base_dir, "assets", "help.md")
            
            with open(help_file_path, 'r', encoding='utf-8') as f:
                full_help_text = f.read()
            
            # Use regex to find the section
            # Pattern: [SECTION: section_name] ...content... [SECTION: ...or EOF
            # re.S (DOTALL) makes '.' match newlines
            pattern = re.compile(r'\[SECTION:\s*' + re.escape(section_name) + r'\](.*?)(?=\[SECTION:|\Z)', re.S)
            match = pattern.search(full_help_text)
            
            if match:
                return match.group(1).strip() # Return the content
            else:
                return f"## ERROR ##\nSection '[SECTION: {section_name}]' not found in help.md."
                
        except FileNotFoundError:
            return "## ERROR ##\nConsolidated 'help.md' file not found in assets folder."
        except Exception as e:
            return f"## ERROR ##\nAn error occurred loading the help file:\n{e}"

    def _display_help_content(self, title, help_text):
        """
        Smart function to display help text.
        - Reuses existing window if open.
        - Temporarily releases the 'grab' (lock) of the parent popup so user can type.
        - Restores the 'grab' to the parent popup when Help closes.
        """
        
        # 1. Check if we have an active, valid Help Window
        if hasattr(self, '_help_popup_window') and self._help_popup_window and self._help_popup_window.winfo_exists():
            # REUSE EXISTING WINDOW
            popup = self._help_popup_window
            popup.title(title)
            
            # Lift it to top just in case it got buried
            popup.lift()
            
            text_widget = self._help_text_widget
            
            # Enable editing to clear old text
            text_widget.config(state='normal')
            text_widget.delete('1.0', tk.END)
            
            # Reset scrollbar to top
            text_widget.yview_moveto(0)
            
        else:
            # CREATE NEW WINDOW
            
            # --- NEW: GRAB HANDOFF LOGIC ---
            # Check if any window currently holds the lock (e.g. Notification Settings)
            current_grab_window = self.root.grab_current()
            
            # Store it so we can restore it later
            self._temp_grab_owner = current_grab_window
            
            # If a window is locked, release it so the user can type in it AND read Help
            if current_grab_window:
                current_grab_window.grab_release()
            # -------------------------------

            popup = tk.Toplevel(self.root)
            self._help_popup_window = popup # Store reference
            
            popup.title(title)
            popup.transient(self.root)
            
            # --- MODIFIED: Do NOT set grab on Help. Keep it Modeless. ---
            # popup.grab_set() 
            
            # Handle closing to restore the previous lock
            def on_close():
                # 1. Restore Grab to the previous owner (e.g. Notification Settings)
                if hasattr(self, '_temp_grab_owner') and self._temp_grab_owner:
                    try:
                        if self._temp_grab_owner.winfo_exists():
                            self._temp_grab_owner.grab_set()
                    except Exception:
                        pass # Window might have been closed by user; ignore
                    self._temp_grab_owner = None

                # 2. Cleanup Self
                self._help_popup_window = None
                popup.destroy()
                
            popup.protocol("WM_DELETE_WINDOW", on_close)

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
            
            self._help_text_widget = text_widget # Store reference

            # --- Define Formatting Tags (One-time setup) ---
            text_widget.tag_configure("heading", font=(default_family, default_size + 2, 'bold', 'underline'), spacing1=5, spacing3=10)
            text_widget.tag_configure("bold", font=(default_family, default_size, 'bold'))
            text_widget.tag_configure("bullet", lmargin1=20, lmargin2=20, offset=10)
            text_widget.tag_configure("link", font=(default_family, default_size, 'underline'), foreground="blue")
            
            btn_frame = ttk.Frame(popup, padding=(10, 0, 10, 10))
            btn_frame.pack(fill="x", side="bottom")
            ttk.Button(btn_frame, text="Close", command=on_close).pack(side="right")
            
            # Initial Center
            popup.withdraw()
            popup.update_idletasks()
            self._center_popup(popup, 720, 550)

        # 2. Render the Content (Runs for both New and Reused windows)
        
        # Re-fetch font info for tag configuration inside the loop
        try:
            default_font = tkfont.nametofont("TkDefaultFont")
            default_family = default_font.actual("family")
            default_size = default_font.actual("size")
        except:
            default_family = "TkDefaultFont"
            default_size = 10

        link_regex = r'\[(.*?)\]\((.*?)\)'
        bold_regex = r'(\*\*.*?\*\*)'
        
        # Helper to handle dynamic link tags
        link_counter = 0 
        
        def parse_line_content(line_str, base_tags=()):
            nonlocal link_counter
            parts = re.split(r'(\[.*?\]\(.*?\))', line_str) 
            
            for part in parts:
                link_match = re.match(link_regex, part)
                
                if link_match:
                    link_text = link_match.group(1)
                    link_url = link_match.group(2)
                    
                    # Create a unique tag for this specific link
                    tag_name = f"dynamic_link_{link_counter}"
                    link_counter += 1
                    
                    all_tags = base_tags + (tag_name,)
                    
                    # Configure the tag behavior
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

        # Process lines
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
        
        # Lock widget again
        text_widget.config(state='disabled')

    def _open_help_popup(self, section_name="main"):
        """
        Loads the help text for a specific section. 
        Defaults to 'main' table of contents.
        """
        help_text = self._get_help_section(section_name)
        
        # Map internal section names to human-readable window titles
        titles = {
            "main": "KegLevel Monitor - Help",
            "keg_settings": "Help: Keg Settings",
            "beverage_library": "Help: Beverage Library",
            "notifications": "Help: Notifications",
            "calibration": "Help: Flow Calibration",
            "system_settings": "Help: System Settings",
            "workflow": "Help: Workflow",
            "temp_log": "Help: Temperature Log",
            "wiring": "Help: Wiring Diagram"
        }
        
        title = titles.get(section_name, "KegLevel Help")
        
        # Call the smart display function that reuses the window
        self._display_help_content(title, help_text)
        
    # --- EULA / SUPPORT POPUP ---

    def _load_support_image(self):
        """Loads the QR code image and stores it."""
        if self.support_qr_image:
            return # Already loaded
            
        try:
            # base_dir is self.base_dir, which is ~/keglevel/src/
            # Path is now src/assets/support.gif
            image_path = os.path.join(self.base_dir, "assets", "support.gif")
            
            # Use tk.PhotoImage directly, which supports GIF natively
            self.support_qr_image = tk.PhotoImage(file=image_path)
            
        except FileNotFoundError:
            print("Error: support.gif image not found.")
            self.support_qr_image = None # Ensure it's None
        except tk.TclError as e:
            # This is the error tk.PhotoImage throws for bad files
            print(f"Error loading support.gif (is it a valid GIF?): {e}")
            self.support_qr_image = None
        except Exception as e:
            print(f"Error loading support image: {e}")
            self.support_qr_image = None
            
    def _center_popup(self, popup, width, height):
        """
        Centers a popup window on the screen with a specific width and height.
        Uses withdraw/deiconify to force the Window Manager to respect the position.
        """
        # Ensure window is hidden while we calculate and set position
        popup.withdraw() 
        popup.update_idletasks()
        
        # Use screen dimensions directly
        screen_width = popup.winfo_screenwidth()
        screen_height = popup.winfo_screenheight()
        
        # Calculate center
        x = int((screen_width / 2) - (width / 2))
        y = int((screen_height / 2) - (height / 2))
        
        # Ensure positive coordinates (safety check)
        x = max(0, x)
        y = max(0, y)
        
        # Apply geometry
        popup.geometry(f"{width}x{height}+{x}+{y}")
        
        # Force update to apply geometry before showing
        popup.update_idletasks()
        
        # Now show the window at the correct location
        popup.deiconify()


    def _show_disagree_dialog(self):
        """Shows the final confirmation dialog when user disagrees with EULA."""
        if messagebox.askokcancel("EULA Disagreement",
                                "You chose to not agree with the End User License Agreement, so the app will terminate when you click OK.\n\n"
                                "Click Cancel to return to the agreement or click OK to exit the app."):
            print("EULA Disagreement: User clicked OK. Terminating application.")
            self.root.destroy()
        else:
            # User clicked Cancel -> Re-open the EULA popup
            self._open_eula_popup(is_launch=True)
            
            
    def _open_uninstall_app_popup(self):
        popup = tk.Toplevel(self.root)
        popup.title("Uninstall Application")
        popup.geometry("500x480") # Increased height for checkboxes
        popup.transient(self.root)
        popup.grab_set()
        
        # Center popup
        self._center_popup(popup, 500, 480)

        main_frame = ttk.Frame(popup, padding="20")
        main_frame.pack(expand=True, fill="both")

        # Warning Icon/Header
        ttk.Label(main_frame, text="⚠ WARNING: Permanent Deletion", 
                  foreground="red", font=('TkDefaultFont', 12, 'bold')).pack(pady=(0, 10))

        # Selection Variables (Default False as requested)
        delete_app_var = tk.BooleanVar(value=False)
        delete_data_var = tk.BooleanVar(value=False)

        # Selection Frame
        select_frame = ttk.LabelFrame(main_frame, text="Select items to remove:", padding=10)
        select_frame.pack(fill="x", pady=(0, 15))

        # Checkbox 1: App
        app_chk = ttk.Checkbutton(select_frame, text="Application Files", variable=delete_app_var)
        app_chk.pack(anchor="w")
        ttk.Label(select_frame, text="Removes ~/keglevel, shortcuts, and autostart.", 
                  font=('TkDefaultFont', 10, 'italic'), foreground="#555").pack(anchor="w", padx=(20, 0), pady=(0, 5))

        # Checkbox 2: Data
        data_chk = ttk.Checkbutton(select_frame, text="User Data & Settings", variable=delete_data_var)
        data_chk.pack(anchor="w")
        ttk.Label(select_frame, text="Removes ~/keglevel-data (Libraries, Logs, Settings).", 
                  font=('TkDefaultFont', 10, 'italic'), foreground="#555").pack(anchor="w", padx=(20, 0))

        # Confirmation Entry
        confirm_frame = ttk.Frame(main_frame)
        confirm_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(confirm_frame, text="Type 'YES' to confirm:").pack(side="left", padx=(0, 10))
        
        confirm_var = tk.StringVar()
        entry = ttk.Entry(confirm_frame, textvariable=confirm_var, width=10)
        entry.pack(side="left")
        entry.focus_set()
        
        # Reset Hint Text
        reset_text = (
            "To reset all settings to their default values without uninstalling, click Cancel "
            "and select 'Reset to Defaults' from the settings menu."
        )
        ttk.Label(main_frame, text=reset_text, wraplength=450, justify="left", 
                  font=('TkDefaultFont', 8)).pack(pady=(0, 10))

        # Buttons
        btn_frame = ttk.Frame(popup, padding="10")
        btn_frame.pack(fill="x", side="bottom")

        # Uninstall Button (Initially Disabled)
        uninstall_btn = ttk.Button(btn_frame, text="Uninstall Selected", state="disabled",
                                   command=lambda: self._execute_uninstall_app(popup, confirm_var, delete_app_var, delete_data_var))
        uninstall_btn.pack(side="right", padx=5)
        
        ttk.Button(btn_frame, text="Cancel", command=popup.destroy).pack(side="right", padx=5)
        
        # NEW Help Button
        ttk.Button(btn_frame, text="Help", width=8,
                   command=lambda: self._open_help_popup("uninstall_app")).pack(side="right", padx=5)

        # Trace to enable button only when "YES" is typed AND at least one box is checked
        def check_input(*args):
            is_yes = (confirm_var.get() == "YES")
            is_selection_made = (delete_app_var.get() or delete_data_var.get())
            
            if is_yes and is_selection_made:
                uninstall_btn.config(state="normal")
            else:
                uninstall_btn.config(state="disabled")
                
        confirm_var.trace_add("write", check_input)
        delete_app_var.trace_add("write", check_input)
        delete_data_var.trace_add("write", check_input)

    def _execute_uninstall_app(self, popup_window, confirm_var, delete_app_var, delete_data_var):
        if confirm_var.get() != "YES":
            return
            
        delete_app = delete_app_var.get()
        delete_data = delete_data_var.get()
        
        if not delete_app and not delete_data:
            return # Should be blocked by UI, but safety check

        try:
            print("Uninstall: Starting uninstallation process...")
            
            # 1. Define Paths
            app_src_dir = self.base_dir
            app_root_dir = os.path.abspath(os.path.join(app_src_dir, "..")) # ~/keglevel
            data_dir = self.settings_manager.get_data_dir() # ~/keglevel-data
            
            actions_taken = []

            # 2. Remove App Files
            if delete_app:
                # Remove Autostart
                if IS_RASPBERRY_PI_MODE:
                    try:
                        # remove from autostart using main.py utility
                        manage_autostart_file('remove')
                        print("Uninstall: Autostart entry removed.")
                    except Exception as e:
                        print(f"Uninstall Warning: Could not remove autostart: {e}")

                # Delete App Directory
                if os.path.exists(app_root_dir):
                    shutil.rmtree(app_root_dir)
                    actions_taken.append("Application Files")
                    print(f"Uninstall: Deleted app directory: {app_root_dir}")
                    
            # 3. Remove Data Files
            if delete_data:
                if os.path.exists(data_dir):
                    shutil.rmtree(data_dir)
                    actions_taken.append("User Data")
                    print(f"Uninstall: Deleted data directory: {data_dir}")

            # 4. Success & Exit
            msg = f"Selected items have been removed:\n- {', '.join(actions_taken)}\n\nThe program will now exit."
            messagebox.showinfo("Uninstall Complete", msg, parent=popup_window)
            
            popup_window.destroy()
            self._on_closing_ui() 
            sys.exit(0) 

        except Exception as e:
            messagebox.showerror("Uninstall Error", 
                                 f"An error occurred during uninstallation:\n{e}\n\n"
                                 "Some files may need to be deleted manually.", 
                                 parent=popup_window)
            print(f"Uninstall Critical Error: {e}")

    
