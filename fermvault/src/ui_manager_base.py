"""
fermvault app  
ui_manager_base.py
"""

import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont 
import math
import time
import queue
import os
from datetime import datetime
import threading
from tkinter import scrolledtext
import subprocess

# Define a placeholder for UI Update Queue Handler (needed for the mixin/composed class)
class MainUIBase:
    
    # Placeholder for constants/variables that will be shared across files
    UNASSIGNED_SENSOR = "unassigned" 
    
    def __init__(self, root, settings_manager_instance, temp_controller_instance, api_manager_instance, notification_manager_instance, app_version_string):
        self.root = root
        self.settings_manager = settings_manager_instance
        self.temp_controller = temp_controller_instance
        self.api_manager = api_manager_instance
        self.notification_manager = notification_manager_instance
        
        # This queue is now primarily for system logging only
        self.ui_update_queue = queue.Queue() 
        self.app_version_string = app_version_string

        # --- FIX: Initialize Option Lists Here ---
        # --- MODIFICATION: Use new, shorter display names ---
        self.control_mode_options = ["Ambient", "Beer", "Ramp", "Crash"]
        # --- END MODIFICATION ---
        
        # --- MODIFICATION START: Updated Action Options ---
        self.action_options = [
            "Send Status Message", "Update API Data", "Update Temperature Data", 
            "Reload Brew Sessions", "Run FG Calculator", "Check for Updates", "Reset to Defaults"
        ]
        # --- MODIFICATION END ---
        
        # --- MODIFICATION: Updated Popup List ---
        self.popup_list = ["Temperature Setpoints", "PID & Tuning", "Notification Settings", "API & FG Settings", 
                           "Brew Sessions", "System Settings", "Wiring Diagram", "Help", "About", "Support this App"]
        # --- END MODIFICATION ---
        
        self.root.title("Fermentation Vault")
        self.root.geometry("800x600") # Fixed small size
        self.root.resizable(False, False)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing_ui) 

        # --- Primary UI Variables ---
        saved_title = settings_manager_instance.get("brew_session_title", "")
        self.brew_session_var = tk.StringVar(value=saved_title)

        saved_api_service = settings_manager_instance.get("active_api_service", "OFF")
        self.api_service_var = tk.StringVar(value=saved_api_service)
        
        self.control_mode_var = tk.StringVar()
        self.monitoring_var = tk.StringVar(value="OFF")

        # --- NEW: Load Aux Relay Mode with fallback migration ---
        saved_aux = settings_manager_instance.get("aux_relay_mode")
        if not saved_aux:
            # Fallback for migration: Check old key
            old_fan = settings_manager_instance.get("fan_control_mode", "Auto")
            if old_fan == "Auto": saved_aux = "Monitoring"
            elif old_fan == "ON": saved_aux = "Always ON"
            elif old_fan == "OFF": saved_aux = "Always OFF"
            else: saved_aux = "Monitoring"
            
            # Save the migrated value immediately
            settings_manager_instance.set("aux_relay_mode", saved_aux)
            
        self.aux_mode_var = tk.StringVar(value=saved_aux)
        # --- END NEW ---
        
        # --- Data Display Variables ---
        self.beer_setpoint_var = tk.StringVar(value="--.-")
        self.beer_actual_var = tk.StringVar(value="--.-")
        self.beer_timestamp_var = tk.StringVar(value="--:--:--")

        self.amb_setpoint_min_var = tk.StringVar(value="--.-")
        self.amb_actual_var = tk.StringVar(value="--.-")
        self.amb_timestamp_var = tk.StringVar(value="--:--:--")
        
        self.og_display_var = tk.StringVar(value="--.---")
        self.og_timestamp_var = tk.StringVar(value="--:--:--")
        
        self.sg_display_var = tk.StringVar(value="--.---")
        self.sg_timestamp_var = tk.StringVar(value="--:--:--")

        self.fg_status_var = tk.StringVar(value="--.---") # This is now the VALUE field
        self.fg_message_var = tk.StringVar(value="--:--:--") # This is now the MESSAGE field
        
        self.ramp_end_target_var = tk.StringVar(value="")
        
        self.heartbeat_toggle = False
        
        self.heat_state_var = tk.StringVar(value="Heating OFF") 
        self.cool_state_var = tk.StringVar(value="Cooling OFF") 
        
        self.cool_restriction_var = tk.StringVar(value="")
        
        self.system_messages_var = tk.StringVar(value="System Initialized.")
        
        self.ui_ready = False
        
        self.root.after_idle(self._create_widgets)
        self._poll_ui_update_queue()
    
    def _create_widgets(self):
        # Configure styles
        s = ttk.Style(self.root)
        s.configure('Header.TFrame', background='#e0e0e0')
        s.configure('Red.TLabel', background='lightcoral', foreground='black')
        s.configure('Blue.TLabel', background='lightblue1', foreground='black')
        s.configure('Gray.TLabel', background='gainsboro', foreground='black')
        s.configure('Green.TLabel', background='springgreen', foreground='black')
        s.configure('Yellow.TLabel', background='khaki1', foreground='black')
        s.configure('DarkGreen.TLabel', background='green', foreground='white')
        
        s.configure('AlertRed.TLabel', background='red', foreground='white', font=('TkDefaultFont', 10, 'bold'))
        s.configure('MediumGreen.TLabel', background='#3CB371', foreground='black')

        # --- Custom Combobox Styles ---
        s.map('Red.TCombobox', fieldbackground=[('readonly', 'lightcoral')]) 
        s.map('MediumGreen.TCombobox', fieldbackground=[('readonly', '#3CB371')])
        s.map('DarkGreen.TCombobox', fieldbackground=[('readonly', 'green')])

        s.configure('Center.TLabel', anchor='center')

        # --- Grid Setup ---
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill="both", expand=True)
        
        # --- Column Definitions ---
        NARROW_FIELD_WIDTH = 55
        UNIT_FIELD_WIDTH = 15 
        WIDE_TIMESTAMP_WIDTH = 150
        DATA_LABEL_MIN_WIDTH = 100
        
        self.main_frame.grid_columnconfigure(0, weight=0, minsize=80)    # Col 0: Control Labels
        self.main_frame.grid_columnconfigure(1, weight=0, minsize=110)   # Col 1: Control Dropdowns/Buttons
        self.main_frame.grid_columnconfigure(2, weight=0, minsize=DATA_LABEL_MIN_WIDTH) # Col 2: Data Labels 
        self.main_frame.grid_columnconfigure(3, weight=0, minsize=NARROW_FIELD_WIDTH) # Col 3: Setpoint Data
        self.main_frame.grid_columnconfigure(4, weight=0, minsize=UNIT_FIELD_WIDTH) # Col 4: Setpoint Unit
        self.main_frame.grid_columnconfigure(5, weight=0, minsize=NARROW_FIELD_WIDTH) # Col 5: Actual Data
        self.main_frame.grid_columnconfigure(6, weight=0, minsize=UNIT_FIELD_WIDTH) # Col 6: Actual Unit
        self.main_frame.grid_columnconfigure(7, weight=1, minsize=WIDE_TIMESTAMP_WIDTH) # Col 7: Timestamp
        
        # --- Header Frame ---
        self.header_frame = ttk.Frame(self.main_frame)
        self.header_frame.grid(row=0, column=0, columnspan=8, sticky='ew')
        
        self.header_frame.grid_columnconfigure(0, weight=0, minsize=80)    
        self.header_frame.grid_columnconfigure(1, weight=1, minsize=240)   
        self.header_frame.grid_columnconfigure(2, weight=0, minsize=0)     
        self.header_frame.grid_columnconfigure(3, weight=0, minsize=0)     
        self.header_frame.grid_columnconfigure(4, weight=1)               
        self.header_frame.grid_columnconfigure(5, weight=0, minsize=338)   
        
        row_idx = 0 
        
        # --- Row 0 & 1: Header Dropdowns ---
        ttk.Label(self.header_frame, text="API Service").grid(row=row_idx, column=0, sticky='w', pady=(5, 5))
        self.api_dropdown = ttk.Combobox(self.header_frame, textvariable=self.api_service_var, values=list(self.api_manager.available_services.keys()), state="readonly")
        self.api_dropdown.grid(row=row_idx, column=1, sticky='ew', padx=5, pady=(5, 5))
        self.api_dropdown.bind("<<ComboboxSelected>>", self._handle_api_selection_change)

        # Row 1
        ttk.Label(self.header_frame, text="Brew Session").grid(row=row_idx + 1, column=0, sticky='w', pady=(5, 5))
        self.session_dropdown = ttk.Combobox(self.header_frame, textvariable=self.brew_session_var, values=[], state="readonly")
        self.session_dropdown.grid(row=row_idx + 1, column=1, sticky='ew', padx=5, pady=(5, 5))
        self.session_dropdown.bind("<<ComboboxSelected>>", self._handle_brew_session_change)
        
        # Menu Container
        self.menu_container = ttk.Frame(self.header_frame)
        self.menu_container.grid(row=0, column=5, rowspan=2, sticky='ne', padx=5, pady=0)
        self.menu_container.grid_columnconfigure(0, weight=1) 
        
        try:
            default_font = tkfont.nametofont("TkDefaultFont")
            bold_font = default_font.copy()
            bold_font.config(weight="bold")
            self.menu_heading_font = bold_font
        except:
            self.menu_heading_font = ('TkDefaultFont', 10, 'bold')

        # === SINGLE MENU: SETTINGS ===
        self.settings_menubutton = ttk.Menubutton(self.menu_container, text="Settings", width=20)
        self.settings_menubutton.grid(row=0, column=0, sticky='ew', padx=2, pady=(5, 5))
        
        settings_menu = tk.Menu(self.settings_menubutton, tearoff=0, disabledforeground="black")
        self.settings_menubutton["menu"] = settings_menu
        
        # 1. Configuration Header
        settings_menu.add_command(label="Configuration", font=self.menu_heading_font, state="disabled")
        
        config_items = [
            "Temperature Setpoints", "PID & Tuning", "Notification Settings", 
            "API & FG Settings", "Brew Sessions", "System Settings"
        ]
        for item in config_items:
            if item in self.popup_list:
                settings_menu.add_command(label=item, command=lambda choice=item: self._open_popup_by_name(choice))
        
        settings_menu.add_separator()
        
        # 2. Utilities Header
        settings_menu.add_command(label="Utilities", font=self.menu_heading_font, state="disabled")
        # settings_menu.add_command(label="Update Temperature Data", command=lambda: self._handle_actions_menu("Update Temperature Data"))
        settings_menu.add_command(label="Update API Data", command=lambda: self._handle_actions_menu("Update API Data"))
        settings_menu.add_command(label="Run FG Calculator", command=lambda: self._handle_actions_menu("Run FG Calculator"))
        settings_menu.add_command(label="Reload Brew Sessions", command=lambda: self._handle_actions_menu("Reload Brew Sessions"))
        
        settings_menu.add_separator()
        
        # 3. Maintenance Header
        settings_menu.add_command(label="Maintenance", font=self.menu_heading_font, state="disabled")
        settings_menu.add_command(label="Check for Updates", command=lambda: self._handle_actions_menu("Check for Updates"))
        settings_menu.add_command(label="Reset to Defaults", command=lambda: self._handle_actions_menu("Reset to Defaults"))
        
        # --- NEW: Uninstall Menu Item ---
        settings_menu.add_command(label="Uninstall App", command=lambda: self._handle_actions_menu("Uninstall App"))
        # --- END NEW ---
        
        settings_menu.add_separator()
        
        # 4. App Info Header
        settings_menu.add_command(label="App Info", font=self.menu_heading_font, state="disabled")
        
        if "Wiring Diagram" in self.popup_list:
             settings_menu.add_command(label="Wiring Diagram", command=lambda: self._open_popup_by_name("Wiring Diagram"))
        
        if "Help" in self.popup_list:
             settings_menu.add_command(label="Help", command=lambda: self._open_popup_by_name("Help"))

        if "Support this App" in self.popup_list:
             settings_menu.add_command(label="Support this App", command=lambda: self._open_popup_by_name("Support this App"))

        if "About" in self.popup_list:
             settings_menu.add_command(label="About...", command=lambda: self._open_popup_by_name("About"))
        
        row_idx = 0 
        
        # --- Horizontal Separator ---
        main_grid_row_idx = 1
        ttk.Separator(self.main_frame, orient='horizontal').grid(row=main_grid_row_idx, column=0, columnspan=8, sticky='ew', pady=(5, 10))
        main_grid_row_idx += 1
        
        # --- Data Grid Headers ---
        ttk.Label(self.main_frame, text="Control Mode").grid(row=main_grid_row_idx, column=0, sticky='w', padx=5, pady=5)
        self.control_mode_dropdown = ttk.Combobox(self.main_frame, textvariable=self.control_mode_var, values=self.control_mode_options, state="readonly", width=13)
        self.control_mode_dropdown.grid(row=main_grid_row_idx, column=1, sticky='w', padx=5, pady=5)
        self.control_mode_dropdown.bind("<<ComboboxSelected>>", self._handle_control_mode_change)
        
        ttk.Label(self.main_frame, text="Setpoint", style='Center.TLabel').grid(row=main_grid_row_idx, column=3, columnspan=2, padx=5, pady=5)
        ttk.Label(self.main_frame, text="Actual", style='Center.TLabel').grid(row=main_grid_row_idx, column=5, columnspan=2, padx=5, pady=5)
        
        main_grid_row_idx += 1
        VERTICAL_PADDING = (6, 6) 
        
        # --- DATA ROW 1: Ambient ---
        ttk.Label(self.main_frame, text="Monitoring").grid(row=main_grid_row_idx, column=0, sticky='w', padx=5, pady=VERTICAL_PADDING)
        self.monitoring_button = ttk.Combobox(self.main_frame, textvariable=self.monitoring_var, values=["OFF", "ON"], state="readonly", width=13, style="Red.TCombobox")
        self.monitoring_button.grid(row=main_grid_row_idx, column=1, sticky='w', padx=5, pady=VERTICAL_PADDING)
        self.monitoring_button.bind("<<ComboboxSelected>>", lambda event: self._toggle_monitoring())

        ttk.Label(self.main_frame, text="Ambient").grid(row=main_grid_row_idx, column=2, sticky='e', padx=5, pady=VERTICAL_PADDING)
        self.amb_target_label = ttk.Label(self.main_frame, textvariable=self.amb_setpoint_min_var, style='Gray.TLabel', relief='sunken', anchor='center', width=7)
        self.amb_target_label.grid(row=main_grid_row_idx, column=3, sticky='ew', padx=5, pady=VERTICAL_PADDING)
        ttk.Label(self.main_frame, text="F").grid(row=main_grid_row_idx, column=4, sticky='w', pady=VERTICAL_PADDING) 
        self.amb_actual_label = ttk.Label(self.main_frame, textvariable=self.amb_actual_var, style='Gray.TLabel', relief='sunken', anchor='center', width=7)
        self.amb_actual_label.grid(row=main_grid_row_idx, column=5, sticky='ew', padx=5, pady=VERTICAL_PADDING)
        ttk.Label(self.main_frame, text="F").grid(row=main_grid_row_idx, column=6, sticky='w', pady=VERTICAL_PADDING) 
        self.amb_timestamp_label = ttk.Label(self.main_frame, textvariable=self.amb_timestamp_var, relief='sunken', anchor='center')
        self.amb_timestamp_label.grid(row=main_grid_row_idx, column=7, sticky='ew', padx=5, pady=VERTICAL_PADDING)

        main_grid_row_idx += 1
        
        # --- DATA ROW 2: Beer & Aux Relay ---
        ttk.Label(self.main_frame, text="Aux Relay Follows").grid(row=main_grid_row_idx, column=0, sticky='w', padx=5, pady=VERTICAL_PADDING)
        
        aux_options = ["Always OFF", "Always ON", "Monitoring", "Heating", "Cooling", "Crashing"]
        self.aux_dropdown = ttk.Combobox(self.main_frame, textvariable=self.aux_mode_var, values=aux_options, state="readonly", width=13)
        self.aux_dropdown.grid(row=main_grid_row_idx, column=1, sticky='w', padx=5, pady=VERTICAL_PADDING)
        self.aux_dropdown.bind("<<ComboboxSelected>>", self._handle_aux_mode_change)

        ttk.Label(self.main_frame, text="Beer").grid(row=main_grid_row_idx, column=2, sticky='e', padx=5, pady=VERTICAL_PADDING)
        self.beer_target_label = ttk.Label(self.main_frame, textvariable=self.beer_setpoint_var, style='Gray.TLabel', relief='sunken', anchor='center', width=7)
        self.beer_target_label.grid(row=main_grid_row_idx, column=3, sticky='ew', padx=5, pady=VERTICAL_PADDING)
        ttk.Label(self.main_frame, text="F").grid(row=main_grid_row_idx, column=4, sticky='w', pady=VERTICAL_PADDING)
        self.beer_actual_label = ttk.Label(self.main_frame, textvariable=self.beer_actual_var, style='Gray.TLabel', relief='sunken', anchor='center', width=7)
        self.beer_actual_label.grid(row=main_grid_row_idx, column=5, sticky='ew', padx=5, pady=VERTICAL_PADDING)
        ttk.Label(self.main_frame, text="F").grid(row=main_grid_row_idx, column=6, sticky='w', pady=VERTICAL_PADDING)
        self.ramp_end_target_label = ttk.Label(self.main_frame, textvariable=self.ramp_end_target_var, relief='sunken', anchor='center')
        self.ramp_end_target_label.grid(row=main_grid_row_idx, column=7, sticky='ew', padx=5, pady=VERTICAL_PADDING)
        
        main_grid_row_idx += 1
        
        # --- DATA ROW 3: OG ---
        self.heat_label = ttk.Label(self.main_frame, textvariable=self.heat_state_var, style='Gray.TLabel', anchor='center', relief='sunken')
        self.heat_label.grid(row=main_grid_row_idx, column=0, columnspan=2, sticky='ew', padx=5, pady=VERTICAL_PADDING)

        ttk.Label(self.main_frame, text="OG").grid(row=main_grid_row_idx, column=2, sticky='e', padx=5, pady=VERTICAL_PADDING) 
        ttk.Label(self.main_frame, text="").grid(row=main_grid_row_idx, column=3, sticky='ew', padx=5, pady=VERTICAL_PADDING) 
        ttk.Label(self.main_frame, text="").grid(row=main_grid_row_idx, column=4, sticky='w', pady=VERTICAL_PADDING) 
        self.og_display_label = ttk.Label(self.main_frame, textvariable=self.og_display_var, relief='sunken', anchor='center', width=7)
        self.og_display_label.grid(row=main_grid_row_idx, column=5, sticky='ew', padx=5, pady=VERTICAL_PADDING)
        ttk.Label(self.main_frame, text="").grid(row=main_grid_row_idx, column=6, sticky='w', pady=VERTICAL_PADDING) 
        self.og_timestamp_label = ttk.Label(self.main_frame, textvariable=self.og_timestamp_var, relief='sunken', anchor='center')
        self.og_timestamp_label.grid(row=main_grid_row_idx, column=7, sticky='ew', padx=5, pady=VERTICAL_PADDING)

        main_grid_row_idx += 1
        
        # --- DATA ROW 4: SG ---
        self.cool_label = ttk.Label(self.main_frame, textvariable=self.cool_state_var, style='Gray.TLabel', anchor='center', relief='sunken')
        self.cool_label.grid(row=main_grid_row_idx, column=0, columnspan=2, sticky='ew', padx=5, pady=VERTICAL_PADDING)

        ttk.Label(self.main_frame, text="SG").grid(row=main_grid_row_idx, column=2, sticky='e', padx=5, pady=VERTICAL_PADDING) 
        ttk.Label(self.main_frame, text="").grid(row=main_grid_row_idx, column=3, sticky='ew', padx=5, pady=VERTICAL_PADDING) 
        ttk.Label(self.main_frame, text="").grid(row=main_grid_row_idx, column=4, sticky='w', pady=VERTICAL_PADDING) 
        self.sg_display_label = ttk.Label(self.main_frame, textvariable=self.sg_display_var, relief='sunken', anchor='center', width=7)
        self.sg_display_label.grid(row=main_grid_row_idx, column=5, sticky='ew', padx=5, pady=VERTICAL_PADDING)
        ttk.Label(self.main_frame, text="").grid(row=main_grid_row_idx, column=6, sticky='w', pady=VERTICAL_PADDING) 
        self.sg_timestamp_label = ttk.Label(self.main_frame, textvariable=self.sg_timestamp_var, relief='sunken', anchor='center')
        self.sg_timestamp_label.grid(row=main_grid_row_idx, column=7, sticky='ew', padx=5, pady=VERTICAL_PADDING)

        main_grid_row_idx += 1
        
        # --- DATA ROW 5: FG ---
        self.cool_restriction_label = ttk.Label(self.main_frame, textvariable=self.cool_restriction_var, style='Gray.TLabel', anchor='center', relief='sunken')
        self.cool_restriction_label.grid(row=main_grid_row_idx, column=0, columnspan=2, sticky='ew', padx=5, pady=VERTICAL_PADDING)
        
        ttk.Label(self.main_frame, text="FG").grid(row=main_grid_row_idx, column=2, sticky='e', padx=5, pady=VERTICAL_PADDING) 
        ttk.Label(self.main_frame, text="").grid(row=main_grid_row_idx, column=3, sticky='ew', padx=5, pady=VERTICAL_PADDING) 
        ttk.Label(self.main_frame, text="").grid(row=main_grid_row_idx, column=4, sticky='w', pady=VERTICAL_PADDING) 
        self.fg_label = ttk.Label(self.main_frame, textvariable=self.fg_status_var, style='Gray.TLabel', relief='sunken', anchor='center', width=7)
        self.fg_label.grid(row=main_grid_row_idx, column=5, sticky='ew', padx=5, pady=VERTICAL_PADDING)
        ttk.Label(self.main_frame, text="").grid(row=main_grid_row_idx, column=6, sticky='w', pady=VERTICAL_PADDING) 
        
        self.fg_timestamp_label = ttk.Label(self.main_frame, textvariable=self.fg_message_var, relief='sunken', anchor='center')
        self.fg_timestamp_label.grid(row=main_grid_row_idx, column=7, sticky='ew', padx=5, pady=VERTICAL_PADDING) 

        main_grid_row_idx += 1
        
        # --- Horizontal Separator ---
        ttk.Separator(self.main_frame, orient='horizontal').grid(row=main_grid_row_idx, column=0, columnspan=8, sticky='ew', pady=(10, 5))
        main_grid_row_idx += 1
        
        # --- System Messages Area ---
        ttk.Label(self.main_frame, text="System Messages:").grid(row=main_grid_row_idx, column=0, sticky='w', pady=5)
        
        log_frame = ttk.Frame(self.main_frame)
        log_frame.grid(row=main_grid_row_idx + 1, column=0, columnspan=8, sticky='nsew', padx=5, pady=5)
        
        log_frame.grid_rowconfigure(0, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)
        
        self.log_scrollbar = ttk.Scrollbar(log_frame, orient='vertical')
        self.log_scrollbar.grid(row=0, column=1, sticky='ns')
        
        self.system_message_area = tk.Text(log_frame, height=5, state='disabled', relief='sunken', wrap='word',
                                           yscrollcommand=self.log_scrollbar.set)
        self.system_message_area.grid(row=0, column=0, sticky='nsew')
        
        self.log_scrollbar.config(command=self.system_message_area.yview)
        
        self.main_frame.grid_rowconfigure(main_grid_row_idx + 1, weight=1)

        self._refresh_ui_bindings()
        self._populate_brew_session_dropdown()
        
        if self.notification_manager:
            self.notification_manager.start_scheduler()
            
        self.ui_ready = True
        self.root.after(5000, self._background_sensor_check)
        
        show_on_launch = self.settings_manager.get("show_eula_on_launch", True)
        if show_on_launch:
            self.root.after(100, lambda: self._open_support_popup(is_launch=True))
            
    def _handle_aux_mode_change(self, event):
        selected_mode = self.aux_mode_var.get()
        self.settings_manager.set("aux_relay_mode", selected_mode)
        
        # --- FIX: Force immediate update if Monitoring is OFF ---
        # If monitoring is running, the loop picks up the change in <5s.
        # If monitoring is OFF, we must manually trigger the relay update
        # to apply "Always ON" or "Always OFF" immediately.
        if self.ui.monitoring_var.get() == "OFF":
             # Calling set_desired_states with all OFF ensures safe Heat/Cool state
             # but allows the new Aux logic to evaluate and switch the relay immediately.
             self.temp_controller.relay_control.set_desired_states(desired_heat=False, desired_cool=False, control_mode="OFF")

    def _refresh_ui_bindings(self):
        # Set initial background colors
        self._update_relay_status_colors()

        # --- MODIFICATION: Add mapping from Internal Name to Display Name ---
        INTERNAL_TO_DISPLAY_MAP = {
            "Ambient Hold": "Ambient",
            "Beer Hold": "Beer",
            "Ramp-Up": "Ramp",
            "Fast Crash": "Crash",
        }
        
        # Read the full internal name (e.g., "Ramp-Up")
        initial_internal_mode = self.settings_manager.get("control_mode", "Beer Hold")
        
        # Look up the short display name (e.g., "Ramp")
        initial_display_mode = INTERNAL_TO_DISPLAY_MAP.get(initial_internal_mode, "Beer")

        if initial_display_mode in self.control_mode_options:
            self.control_mode_var.set(initial_display_mode)
        else:
            self.control_mode_var.set("Beer") # Default to "Beer"
        # --- END MODIFICATION ---
            
        # Traces for status display color change
        self.heat_state_var.trace_add("write", self._update_relay_status_colors)
        self.cool_state_var.trace_add("write", self._update_relay_status_colors)
        
        # --- NEW FIX: Load Setpoints on launch (Monitoring is OFF by default) ---
        
        # 1. Force a single pass of the controller to populate transient settings
        #    This call is now the *only* one responsible for the initial UI data push,
        #    which includes the "Ramp pre-condition" message.
        self.temp_controller.update_control_logic_and_ui_data()
        
        # 2. Call the comprehensive update which also handles static setpoints when OFF
        # --- THIS IS THE FIX for the "Flashing Message" BUG ---
        # The call below was redundant and was wiping the message. It is now removed.
        # self._update_data_display(is_startup=True) 
        # --- END FIX ---
        
        # --- MODIFICATION: Removed call to _update_monitoring_button_color ---
        
    def _update_relay_status_colors(self, *args):
        # Update HEATING/COOLING display colors
        heat_state = self.heat_state_var.get()
        cool_state = self.cool_state_var.get()
        
        heat_bg = 'lightcoral' if heat_state == "HEATING" else 'gainsboro'
        
        # --- MODIFICATION: Simple ON/OFF logic ---
        cool_bg = 'lightblue1' if cool_state == "COOLING" else 'gainsboro'
        # -------------------------------------------
        
        if self.heat_label: self.heat_label.config(background=heat_bg)
        if self.cool_label: self.cool_label.config(background=cool_bg)
        if self.cool_label: self.cool_label.config(background=cool_bg)

    # --- HANDLERS (PLACEHOLDERS) ---
    def _handle_api_selection_change(self, event):
        selected_api = self.api_service_var.get()
        self.api_manager.set_active_service(selected_api)
        self.settings_manager.set("active_api_service", selected_api) # Ensure the setting is saved immediately
        
        # --- THIS IS THE FIX ---
        if selected_api == "OFF":
            # If the API is turned OFF, clear all API-related data from 
            # BOTH the UI (StringVar) AND the SettingsManager (persistent)
            
            # 1. Clear UI Variables
            self.og_display_var.set("-.---")
            self.og_timestamp_var.set("--:--:--")
            self.sg_display_var.set("-.---")
            self.sg_timestamp_var.set("--:--:--")
            self.fg_status_var.set("-.---") # The value
            self.fg_message_var.set("")      # The message
            
            # 2. Clear SettingsManager Variables
            self.settings_manager.set("og_display_var", "-.---")
            self.settings_manager.set("og_timestamp_var", "--:--:--")
            self.settings_manager.set("sg_display_var", "-.---")
            self.settings_manager.set("sg_timestamp_var", "--:--:--")
            self.settings_manager.set("fg_value_var", "-.---")
            self.settings_manager.set("fg_status_var", "")
            
            # Still repopulate the dropdown, which will now show the local sessions
            self._populate_brew_session_dropdown()
            
        else:
            # If an API service is selected, populate the brew session dropdown.
            # The dropdown's "on-complete" function will automatically trigger
            # the first API call for the selected session.
            self._populate_brew_session_dropdown()
        # --- END FIX ---

    def _handle_control_mode_change(self, event):
        # --- MODIFICATION: Add mapping from Display Name to Internal Name ---
        DISPLAY_TO_INTERNAL_MAP = {
            "Ambient": "Ambient Hold",
            "Beer": "Beer Hold",
            "Ramp": "Ramp-Up",
            "Crash": "Fast Crash",
        }
        
        selected_display_mode = self.control_mode_var.get()
        # Look up the internal name (e.g., "Ramp" -> "Ramp-Up")
        selected_internal_mode = DISPLAY_TO_INTERNAL_MAP.get(selected_display_mode, "Beer Hold")
        
        # Save the full internal name to settings for the controller
        self.settings_manager.set("control_mode", selected_internal_mode)
        # --- END MODIFICATION ---

        # --- ADDED FIX ---
        # If the user selects any mode *other* than Ramp-Up,
        # reset the controller's ramp state.
        if selected_internal_mode != "Ramp-Up":
            self.temp_controller.reset_ramp_state()
        # --- END FIX ---

        # --- NEW FIX: Always refresh setpoint display after changing mode ---
        self.refresh_setpoint_display()
        # -------------------------------------------------------------------
        
    def _handle_brew_session_change(self, event):
        """Saves the currently selected brew session title AND ID to settings."""
        selected_title = self.brew_session_var.get()
        # Find the ID associated with the title in the temporary storage
        selected_id = self.session_id_map.get(selected_title) 

        self.settings_manager.set("brew_session_title", selected_title)
        self.settings_manager.set("current_brew_session_id", selected_id) # CRITICAL: Save the ID for API calls
        
        # Action: Immediately fetch API data upon selecting a new session
        if self.notification_manager:
            self.notification_manager.fetch_api_data_now(selected_id)

    def _toggle_monitoring(self):
        # If the new state is 'ON', the user intended to START monitoring.
        if self.monitoring_var.get() == "ON":
            
            # --- CRITICAL SYNCHRONOUS WRITE ---
            # 1. Synchronously read sensors, calculate control logic, and WRITE initial data to SettingsManager.
            self.temp_controller.update_control_logic_and_ui_data() 
            # ----------------------------------
            
            # 2. Start the monitoring thread (which will periodically WRITE and QUEUE updates).
            self.temp_controller.start_monitoring()
            
            # --- CRITICAL SYNCHRONOUS READ (Final Solution) ---
            # 3. Force UI to READ the newly written data immediately. 
            self.root.after(100, self._update_data_display) # Read back data slightly delayed
            # -------------------------------------------------
        
        # If the new state is 'OFF', the user intended to STOP monitoring.
        else: 
            self.temp_controller.stop_monitoring()
            # --- MODIFICATION: Removed all calls to _update_data_display ---
            # The monitoring loop is now 100% responsible for sending
            # its own "DWELL" and final "OFF" messages.
            # ---------------------------------------------------------------

    def _handle_fan_mode_change(self, event):
        selected_mode = self.fan_var.get()
        self.settings_manager.set("fan_control_mode", selected_mode)
        if selected_mode == "ON":
            self.temp_controller.relay_control.turn_on_fan()
        elif selected_mode == "OFF":
            self.temp_controller.relay_control.turn_off_fan()

    def _handle_settings_menu(self, choice):
        if hasattr(self, '_open_popup_by_name'):
             self._open_popup_by_name(choice)

    def _handle_actions_menu(self, choice):
        print(f"Action triggered: {choice}")
        
        if choice == "Update API Data":
            current_id = self.settings_manager.get("current_brew_session_id")
            if self.notification_manager:
                self.notification_manager.fetch_api_data_now(current_id, is_scheduled=False) 
            
        elif choice == "Update Temperature Data":
            beer_sensor = self.settings_manager.get("ds18b20_beer_sensor")
            amb_sensor = self.settings_manager.get("ds18b20_ambient_sensor")
            
            if beer_sensor == "unassigned":
                self.log_system_message("Beer sensor is unassigned. Please set in System Settings.")
            
            if amb_sensor == "unassigned":
                self.log_system_message("Ambient sensor is unassigned. Please set in System Settings.")
            
            self.temp_controller.update_control_logic_and_ui_data()
            
        elif choice == "Send Status Message":
             if self.notification_manager:
                self.notification_manager.send_manual_status_message()
             
        elif choice == "Reload Brew Sessions":
             if self.settings_manager.get("active_api_service") == "OFF":
                 self.log_system_message("API service is OFF. Cannot fetch data.")
             self._populate_brew_session_dropdown()

        elif choice == "Run FG Calculator":
             if self.notification_manager:
                self.notification_manager.run_fg_calc_and_update_ui()
        
        elif choice == "Check for Updates":
             self._check_for_updates() 
                
        elif choice == "Reset to Defaults":
             self._confirm_and_reset_defaults()
             
        # --- NEW: Uninstall Handler ---
        elif choice == "Uninstall App":
             if hasattr(self, '_open_popup_by_name'):
                 # This will call the popup manager's method directly
                 # We assume 'Uninstall App' isn't in the name list but handled here or we expose it.
                 # Since UIManager inherits PopupManager, we can call it directly.
                 if hasattr(self, '_open_uninstall_app_popup'):
                     self._open_uninstall_app_popup()
        # --- END NEW ---
        
    def _populate_brew_session_dropdown(self):
        """
        [MODIFIED] This function now only sets a 'Loading' message
        and launches the background thread to fetch the data.
        """
        # Set a "loading" message immediately
        self.session_dropdown['values'] = ["Loading..."]
        self.brew_session_var.set("Loading...")
        
        # Start the background thread to do the real work
        threading.Thread(target=self._populate_brew_session_task, daemon=True).start()

    def _populate_brew_session_task(self):
        """
        [NEW] Worker thread to fetch brew sessions without freezing the UI.
        """
        selected_api = self.api_service_var.get()
        session_id_map = {} # New internal map to link titles to IDs
        
        if selected_api == "OFF":
            sessions_from_settings = self.settings_manager.brew_sessions
            sessions_to_display = [title for title in sessions_from_settings if title.strip()]
            # For OFF mode, the title is the ID
            session_id_map = {title: title for title in sessions_to_display}
            
            if not session_id_map:
                sessions_to_display = ["No Sessions Available (API OFF)"]
                session_id_map = {"No Sessions Available (API OFF)": None}
        else:
            # Load sessions via the active API Manager (THIS IS THE BLOCKING CALL)
            api_data = self.api_manager.get_api_data("list_sessions")
            
            # --- NEW ERROR CHECKING ---
            if isinstance(api_data, dict) and "error" in api_data:
                # Log the specific error to the UI's system messages
                self.root.after(0, self.log_system_message, f"API Error: {api_data['error']}")
                sessions_to_display = ["API Error"]
                session_id_map = {"API Error": None}
                # Skip the rest of the parsing
                self.root.after(0, lambda: self._update_session_dropdown_ui(sessions_to_display, session_id_map))
                return # Stop the thread
            # --- END NEW ERROR CHECKING ---
            
            sessions_to_display = []
            if api_data:
                for s in api_data:
                    title = s.get('recipe_title', s.get('id', 'Unknown'))
                    session_id = str(s.get('id'))
                    sessions_to_display.append(title)
                    session_id_map[title] = session_id # Store the actual ID
            
            if not sessions_to_display:
                sessions_to_display = ["API Fetch Failed/No Sessions"]
                session_id_map = {"API Fetch Failed/No Sessions": None}
        
        # Now that we have the data, schedule the UI update on the main thread
        self.root.after(0, lambda: self._update_session_dropdown_ui(sessions_to_display, session_id_map))

    def _update_session_dropdown_ui(self, sessions_to_display, session_id_map):
        """
        [NEW] Safely updates the brew session combobox from the main thread.
        """
        
        # Store the map for later use
        self.session_id_map = session_id_map
        
        # Update the Combobox options
        self.session_dropdown['values'] = sessions_to_display
        
        # --- MODIFICATION: Store the ID to fetch ---
        current_session_id_to_fetch = None
        # --- END MODIFICATION ---
        
        if sessions_to_display:
            current_session_title = self.settings_manager.get("brew_session_title", "")
            
            if not current_session_title or current_session_title not in self.session_id_map:
                 new_selection = sessions_to_display[0]
                 self.brew_session_var.set(new_selection)
                 
                 # Automatically save the new default selection's title and ID
                 self.settings_manager.set("brew_session_title", new_selection)
                 # --- MODIFICATION: Capture the ID ---
                 current_session_id_to_fetch = self.session_id_map.get(new_selection)
                 self.settings_manager.set("current_brew_session_id", current_session_id_to_fetch)
                 # --- END MODIFICATION ---
                 
            else:
                 # If the saved title is valid, ensure the variable is set to the correct title
                 self.brew_session_var.set(current_session_title) 
                 # And ensure the corresponding ID is saved
                 # --- MODIFICATION: Capture the ID ---
                 current_session_id_to_fetch = self.session_id_map.get(current_session_title)
                 self.settings_manager.set("current_brew_session_id", current_session_id_to_fetch)
                 # --- END MODIFICATION ---
        else:
             self.brew_session_var.set("")
             self.settings_manager.set("brew_session_title", "")
             self.settings_manager.set("current_brew_session_id", None)
             
        # --- MODIFICATION: Trigger API fetch on launch ---
        # After populating the list, if API is ON, fetch data for the selected session
        if self.api_service_var.get() != "OFF":
            if current_session_id_to_fetch and self.notification_manager:
                print(f"[UI] Triggering auto-fetch for session ID: {current_session_id_to_fetch}")
                # This function is already threaded and will log to the UI
                self.notification_manager.fetch_api_data_now(current_session_id_to_fetch)
            elif not current_session_id_to_fetch:
                self.log_system_message("Auto-fetch skipped: No valid brew session ID found.")
        # --- END MODIFICATION ---
    
    # --- QUEUE HANDLING ---
    def _poll_ui_update_queue(self):
        """Processes the queue for logging only, and reschedules itself."""
        try:
            while True:
                # Only check for log_message task
                task, args = self.ui_update_queue.get_nowait()
                if task == "log_message": self._log_system_message(*args)
                
                # NOTE: task "update_data" is ignored/removed here.
                
                self.ui_update_queue.task_done()
        except queue.Empty: pass
        finally:
            if self.root.winfo_exists(): 
                 # Final correct polling interval after previous testing
                 self.root.after(50, self._poll_ui_update_queue)    

    # --- FIX: LOGGING ORDER AND TIMESTAMP FORMAT ---
    def _log_system_message(self, message):
        # --- FIX: Check if the widget attribute exists before accessing it ---
        if hasattr(self, 'system_message_area') and self.system_message_area.winfo_exists():
        # --- END FIX ---
            # --- UPDATED TIMESTAMP FORMAT ---
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # --------------------------------
            log_entry = f"[{timestamp}] {message}\n"
            self.system_message_area.config(state='normal')
            self.system_message_area.insert("1.0", log_entry) # Insert at the top
            self.system_message_area.config(state='disabled')
            
            # --- FIX: Force immediate repaint ---
            # This ensures the text appears immediately even if the main loop is busy
            self.system_message_area.update_idletasks() 
            # ------------------------------------

    def log_system_message(self, message):
        """
        Public method to log messages from any thread (Main, Monitor, or API).
        Uses root.after() to safely schedule the update on the main UI thread.
        """
        if self.root and hasattr(self.root, 'after'):
            # Schedule the internal private method to run ASAP on the main thread
            self.root.after(0, self._log_system_message, message)

    def push_data_update(self, **kwargs):
        """
        [CRITICAL FIX] Bypasses queue.Queue and uses Tkinter's scheduler to force 
        execution of the data read on the main thread.
        
        This method receives the raw data directly from the background thread via kwargs.
        """
        if self.root.winfo_exists():
             # self.root.after(0, ...) is the most aggressive thread-safe way to update UI variables.
             # Pass the kwargs directly to the lambda wrapper, which calls _update_data_display(direct_data=kwargs)
             self.root.after(0, lambda: self._update_data_display(direct_data=kwargs))
             
    # --- UI REFRESH (COMBINED) ---
    def _update_data_display(self, is_startup=False, is_setpoint_change=False, is_stop=False, direct_data=None):
        """
        Pulls all data from SettingsManager OR uses direct_data to update UI variables.
        Called from the main thread via root.after(0).
        """
        
        # 1. Get Control Settings for unit conversion
        settings = self.settings_manager.get_all_control_settings()
        units = settings['temp_units']
        
        # --- CRITICAL FIX: Centralized data validation and display formatting ---
        def format_for_display(value, type_hint="temp"):
             if isinstance(value, str) and value in ["--.-", "-.---", "Pending", "--:--:--", "N/A"]:
                 return value
             # --- FIX: Added check for full timestamp string ---
             if isinstance(value, str) and len(value) > 10: # It's a full timestamp
                 return value
             # -------------------------------------------------
             try:
                 temp = float(value)
                 if type_hint == "temp":
                     # Apply F to C conversion if needed
                     display_val = temp if units == "F" else ((temp - 32) * 5/9)
                     return f"{display_val:.1f}"
                 elif type_hint == "sg":
                     # --- MODIFICATION: Handle non-SG values that are passed in ---
                     if value == 0.0 or value == 0: return "-.---"
                     if temp < 0.1: return "-.---" # Catch other invalid SG numbers
                     # --- END MODIFICATION ---
                     return f"{temp:.3f}"
                 else:
                     return str(value)
             except (ValueError, TypeError):
                 # Fallback for corrupted/invalid numeric data
                 # --- MODIFICATION: Return correct format for type ---
                 if type_hint == "sg": return "-.---"
                 else: return "--.-"
                 # --- END MODIFICATION ---
        # -----------------------------------------------------------------------

        # --- DATA RETRIEVAL (PRIORITIZE DIRECT PUSHED DATA) ---
        
        amb_timestamp = self.settings_manager.get("amb_temp_timestamp", "--:--:--")
        sg_timestamp = self.settings_manager.get("sg_timestamp_var", "----/--/-- --:--:--")
        og_timestamp = self.settings_manager.get("og_timestamp_var", "----/--/-- --:--:--")
        
        # --- MODIFICATION: Add map for mode translation ---
        INTERNAL_TO_DISPLAY_MAP = {
            "Ambient Hold": "Ambient",
            "Beer Hold": "Beer",
            "Ramp-Up": "Ramp",
            "Fast Crash": "Crash",
            "OFF": "OFF"
        }
        # --- END MODIFICATION ---
        
        # --- NEW: Define sensor_error variable ---
        sensor_error = ""
        # --- END NEW ---
        
        if direct_data and not is_stop:
            # Use data pushed directly from the Temperature Controller (Bypasses read failure)
            beer_actual = direct_data.get("beer_temp", "--.-")
            amb_actual = direct_data.get("amb_temp", "--.-")
            current_amb_min = direct_data.get("amb_min", "--.-")
            current_amb_max = direct_data.get("amb_max", "--.-") 
            current_amb_target = direct_data.get("amb_target", "--.-") 
            current_beer_setpoint = direct_data.get("beer_setpoint", "--.-")
            heat_state = direct_data.get("heat_state", "Heating OFF")
            cool_state = direct_data.get("cool_state", "Cooling OFF")
            
            # --- MODIFICATION: Translate internal mode to display mode ---
            internal_mode = direct_data.get("current_mode", self.control_mode_var.get())
            display_mode = INTERNAL_TO_DISPLAY_MAP.get(internal_mode, "Beer")
            # --- END MODIFICATION ---
            
            ramp_is_finished = direct_data.get("ramp_is_finished")
            
            # --- MODIFICATION: Get the pre-formatted message ---
            ramp_target_message = direct_data.get("ramp_target_message", "")
            # --- END MODIFICATION ---

            # --- NEW: Get sensor error message ---
            sensor_error = direct_data.get("sensor_error_message", "")
            # --- END NEW ---

        else:
            # Fallback for initial load (is_startup) or stop monitoring (is_stop)
            current_amb_min = self.settings_manager.get("amb_min_setpoint", settings.get("ambient_hold_f", "--.-"))
            current_amb_max = self.settings_manager.get("amb_max_setpoint", settings.get("ambient_hold_f", "--.-"))
            current_amb_target = self.settings_manager.get("amb_target_setpoint", settings.get("ambient_hold_f", "--.-")) 
            current_beer_setpoint = self.settings_manager.get("beer_setpoint_current", settings.get("beer_hold_f", "--.-"))
            
            beer_actual = self.settings_manager.get("beer_temp_actual", "--.-")
            amb_actual = self.settings_manager.get("amb_temp_actual", "--.-")

            heat_state = self.settings_manager.get("heat_state", "Heating OFF")
            cool_state = self.settings_manager.get("cool_state", "Cooling OFF")

            # --- MODIFICATION: Translate internal mode to display mode ---
            internal_mode = self.settings_manager.get("control_mode")
            display_mode = INTERNAL_TO_DISPLAY_MAP.get(internal_mode, "Beer")
            # --- END MODIFICATION ---
            
            ramp_is_finished = False
            ramp_target_message = "" # Clear message on stop

            # --- NEW: Get sensor error from settings ---
            sensor_error = self.settings_manager.get("sensor_error_message", "")
            if is_stop:
                sensor_error = "" # Clear error on stop
            # --- END NEW ---

        # --- 2. Format and Apply Final Setpoint Logic ---
        
        is_monitoring_on = self.monitoring_var.get() == "ON"

        # 2a. Get formatted values
        display_amb_target = format_for_display(current_amb_target)
        display_beer_setpoint = format_for_display(current_beer_setpoint)
        
        if is_monitoring_on:
            # --- MODIFICATION: Use display_mode ---
            if display_mode == "Ambient":
                display_beer_setpoint = "--.-"
            elif display_mode in ["Beer", "Ramp", "Crash"]:
                display_amb_target = "--.-"
            # --- END MODIFICATION ---
        
        # 2b. Set Ambient Setpoint
        self.amb_setpoint_min_var.set(display_amb_target)

        # 2c. Set Beer Setpoint
        self.beer_setpoint_var.set(display_beer_setpoint)

        # 2d. Set Actuals
        self.amb_actual_var.set(format_for_display(amb_actual))
        self.beer_actual_var.set(format_for_display(beer_actual))
        
        # 2e. Create Ambient Range String (e.g., "36.0 — 38.0")
        formatted_min = format_for_display(current_amb_min)
        formatted_max = format_for_display(current_amb_max)
        range_string = f"{formatted_min} – {formatted_max}"
        
        if formatted_min == "--.-" or formatted_max == "--.-":
            range_string = "--.-"
        elif formatted_min == "0.0" and formatted_max == "0.0":
             range_string = "--.-" # Handle the default 0.0/0.0 on init

        # 2f. Set Ambient Target Range
        # --- MODIFICATION: Check for Thermostatic Ramp ---
        if display_mode == "Ramp" and range_string == "--.-" and is_monitoring_on:
            self.amb_timestamp_var.set("N/A (Beer Control)")
        else:
            self.amb_timestamp_var.set(f"Target Range {range_string}") 
        # --- END MODIFICATION ---
        
        # 2g. Set Gravity Timestamps
        self.og_timestamp_var.set(og_timestamp) 
        self.sg_timestamp_var.set(sg_timestamp) 
        
        # --- 3. Apply Relay States ---
        if is_stop:
            self.heat_state_var.set("Heating OFF")
            self.cool_state_var.set("Cooling OFF")
        else:
            self.heat_state_var.set(heat_state)
            self.cool_state_var.set(cool_state)
        
        # 4. Apply Gravity Data (Always read from SettingsManager)
        self.sg_display_var.set(format_for_display(self.settings_manager.get("sg_display_var", "-.---"), type_hint="sg"))
        self.og_display_var.set(format_for_display(self.settings_manager.get("og_display_var", "-.---"), type_hint="sg"))
        
        # --- MODIFICATION: FG Display Logic ---
        fg_value = self.settings_manager.get("fg_value_var", "-.---")
        fg_status_message = self.settings_manager.get("fg_status_var", "")
        
        self.fg_status_var.set(format_for_display(fg_value, type_hint="sg"))
        self.fg_message_var.set(fg_status_message)
        
        # Set color
        if fg_status_message == "Stable":
            self.fg_label.config(style="MediumGreen.TLabel")
        else:
            self.fg_label.config(style="Gray.TLabel")
        # --- END MODIFICATION ---
        
        # --- NEW: Cooling Restriction Display Logic (MODIFIED) ---
        restriction_status = self.settings_manager.get("cool_restriction_status", "")
        
        # --- MODIFICATION: Clear expired messages if monitoring is OFF ---
        if not is_monitoring_on and restriction_status:
            # Check for a time-based message
            if " until " in restriction_status:
                try:
                    # Extract time string (e.g., "20:55:36")
                    time_str = restriction_status.rsplit(' ', 1)[-1]
                    
                    # Parse it
                    expire_time = datetime.strptime(time_str, "%H:%M:%S").time()
                    
                    # Check if it's in the past
                    if datetime.now().time() > expire_time:
                        restriction_status = "" # Clear the local variable
                        
                        # --- THIS IS THE FIX ---
                        self.settings_manager.set("cool_restriction_status", "")
                        # --- END FIX ---
                        
                except (ValueError, IndexError):
                    pass # Failed to parse, just show the old message
        # --- END MODIFICATION ---
        
        self.cool_restriction_var.set(restriction_status)
        
        # --- LOGIC RE-ORDERED: Prioritize Sensor Error ---
        if sensor_error:
            # Sensor error (highest priority)
            self.cool_restriction_label.config(style="AlertRed.TLabel")
            self.cool_restriction_var.set(sensor_error)
            
        elif "FAIL-SAFE" in restriction_status:
            # Red background, bold white text
            self.cool_restriction_label.config(style="AlertRed.TLabel")
        
        # --- THIS IS THE FIX ---
        # Corrected typo from "restriction_s" to "restriction_status"
        elif "DWELL" in restriction_status:
        # --- END FIX ---
            # Yellow background, black text
            self.cool_restriction_label.config(style="Yellow.TLabel")
        else:
            # No restriction, default gray background, no text
            self.cool_restriction_label.config(style="Gray.TLabel")
            self.cool_restriction_var.set("") # Ensure no residual text
        # --- END NEW LOGIC ---

        # --- 5. MODIFICATION: Set Ramp-Up Target Field ---
        
        # --- THIS IS THE FIX ---
        # The redundant "if ramp_is_finished:" check is removed.
        # We now *only* trust the message from the controller.
        if display_mode == "Ramp" and (is_monitoring_on or (direct_data and not is_stop)):
            # Just set the message provided by the controller
            # This will be "Ramp pre-condition", "Target...", "Ramp Landing...", or "Ramp Finished"
            self.ramp_end_target_var.set(ramp_target_message)
        else:
            self.ramp_end_target_var.set("") # Clear if not in ramp mode
        # --- END FIX ---
        
        # --- 5b. MODIFICATION: Set Actual Temp Field Colors ---
        
        # Default to Gray
        amb_style = 'Gray.TLabel'
        beer_style = 'Gray.TLabel'

        if is_monitoring_on:
            try:
                # Convert all needed values to float for comparison
                f_amb_actual = float(amb_actual)
                f_beer_actual = float(beer_actual)

                # --- Ambient Logic ---
                # Only apply if ambient min/max are valid (not 0.0)
                f_amb_min = float(current_amb_min)
                f_amb_max = float(current_amb_max)
                if f_amb_min != 0.0 or f_amb_max != 0.0:
                    if f_amb_actual > f_amb_max:
                        amb_style = 'Red.TLabel'
                    elif f_amb_actual < f_amb_min:
                        amb_style = 'Blue.TLabel'

                # --- Beer Logic (Conditional) ---
                # --- MODIFICATION: Only run Beer logic if mode is NOT Ambient Hold ---
                if display_mode != "Ambient":
                    # Only apply if beer setpoint is valid (not 0.0)
                    f_beer_setpoint = float(current_beer_setpoint)
                    if f_beer_setpoint != 0.0:
                        deadband = 0.1 # Deadband for float comparison
                        if f_beer_actual > (f_beer_setpoint + deadband):
                            beer_style = 'Red.TLabel'
                        elif f_beer_actual < (f_beer_setpoint - deadband):
                            beer_style = 'Blue.TLabel'
                # --- END MODIFICATION ---

            except (ValueError, TypeError):
                # This catches cases where values are "--.-" or other non-floats
                pass # Styles will remain 'Gray.TLabel'
        
        # Apply the determined styles
        self.amb_actual_label.config(style=amb_style)
        self.beer_actual_label.config(style=beer_style)
        # --- END MODIFICATION ---
        
        # --- 6. MODIFICATION: Set NEW Monitoring Indicator (Integrated into Combobox) ---
        if self.monitoring_button: # Check if Combobox exists
            if is_monitoring_on:
                # --- NEW: If sensor error, force RED ---
                if sensor_error:
                    self.monitoring_button.config(style="Red.TCombobox")
                # --- END NEW ---
                else:
                    self.heartbeat_toggle = not self.heartbeat_toggle
                    # Use the new MediumGreen style for the lighter pulse
                    new_style = "MediumGreen.TCombobox" if self.heartbeat_toggle else "DarkGreen.TCombobox"
                    self.monitoring_button.config(style=new_style)
            else:
                # When monitoring is off, force to Red Combobox style
                self.monitoring_button.config(style="Red.TCombobox")
        # --- END MODIFICATION ---
        
    # --- UI REFRESH HELPER ---
    def refresh_setpoint_display(self):
        """Forces an update of only static setpoints from SettingsManager."""
        if self.root.winfo_exists():
            # Use root.after(0) for safe, main-thread execution
            
            # --- MODIFICATION START: Force controller to re-calc and push ---
            # This forces the controller to re-read the settings *now*
            # and push a new update, solving any race conditions.
            if self.temp_controller:
                self.temp_controller.update_control_logic_and_ui_data()
            # --- MODIFICATION END ---
            
            # This call ensures the UI updates even if monitoring is OFF.
            self.root.after(0, lambda: self._update_data_display(is_setpoint_change=True))
            
    def _on_closing_ui(self):
        print("UIManager: Initiating shutdown sequence...")
        if self.root and hasattr(self.root, 'winfo_exists') and self.root.winfo_exists(): self.root.destroy()
        
    def _background_sensor_check(self):
        """
        [NEW] Periodically calls the controller to read sensors and push UI data,
        but ONLY when monitoring is OFF. This is to clear stale sensor errors.
        """
        try:
            if self.root.winfo_exists():
                # Only run this check if monitoring is OFF
                if self.monitoring_var.get() == "OFF":
                    # This function only reads sensors and pushes data,
                    # it does NOT control relays.
                    if self.temp_controller:
                        self.temp_controller.update_control_logic_and_ui_data()
                
                # Reschedule itself to run again in 5 seconds
                self.root.after(5000, self._background_sensor_check)
        except Exception as e:
            print(f"Error in background sensor check: {e}")
            # Try to reschedule anyway
            if self.root.winfo_exists():
                self.root.after(5000, self._background_sensor_check)
                
    def _confirm_and_reset_defaults(self):
        """
        [NEW] Displays a confirmation dialog before resetting all settings.
        If confirmed, resets settings and forces the application to close.
        """
        title = "Confirm Reset to Defaults"
        message = (
            "Reset to Defaults will clear all custom entries and settings and reset all to defaults. "
            "ALL custom settings including Notification settings, API & FG settings, and Brew Sessions settings "
            "will be cleared and reset. Do you wish to proceed?"
        )
        
        # Use askokcancel (OK/Cancel), consistent with PID & Tuning
        if messagebox.askokcancel(title, message):
            try:
                # 1. Call the fixed reset function
                self.settings_manager.reset_all_settings_to_defaults()
                
                # 2. Inform user and shut down
                messagebox.showinfo(
                    "Reset Complete",
                    "All settings have been reset to defaults. The application will now close. Please restart it."
                )
                
                # 3. Trigger the clean shutdown sequence
                if self.root:
                    self.root.destroy()
                    
            except Exception as e:
                messagebox.showerror("Error", f"An error occurred during reset: {e}")
                
    def _check_for_updates(self):
        """
        Opens the update window and starts Phase 1 (Check).
        Replaces the old immediate-update logic.
        """
        # Calculate base_dir relative to this file (src/)
        base_dir = os.path.dirname(os.path.abspath(__file__))
        script_path = os.path.join(base_dir, "..", "update.sh")
        
        if not os.path.exists(script_path):
            messagebox.showerror("Error", f"Update script not found at:\n{script_path}", parent=self.root)
            return

        # 1. Create the Log Window
        status_popup = tk.Toplevel(self.root)
        status_popup.title("System Update")
        status_popup.geometry("650x450")
        status_popup.transient(self.root)
        status_popup.grab_set()
        
        # 2. Text Area for Logging
        text_area = scrolledtext.ScrolledText(status_popup, wrap=tk.WORD, height=20, width=80)
        text_area.pack(padx=10, pady=10, fill="both", expand=True)
        
        text_area.tag_config("info", foreground="black")
        text_area.tag_config("success", foreground="green")
        text_area.tag_config("warning", foreground="#FF8C00") 
        text_area.tag_config("error", foreground="red")
        
        text_area.insert(tk.END, "Initializing update check...\n", "info")
        text_area.config(state="disabled")

        # 3. Button Frame
        btn_frame = ttk.Frame(status_popup, padding=(0, 0, 0, 10))
        btn_frame.pack(fill="x")
        
        # Define Buttons (Pack order: Right to Left)
        
        # A. Close (Window only)
        close_btn = ttk.Button(btn_frame, text="Close", state="disabled", command=status_popup.destroy)
        close_btn.pack(side="right", padx=5)
        
        # B. Close App (Shutdown app for restart) - Initially Disabled
        close_app_btn = ttk.Button(btn_frame, text="Close App (Restart)", state="disabled", 
                                   command=lambda: [status_popup.destroy(), self._on_closing_ui()])
        close_app_btn.pack(side="right", padx=5)
        
        # C. Install Updates - Initially Disabled
        install_btn = ttk.Button(btn_frame, text="Install Updates", state="disabled")
        install_btn.pack(side="right", padx=5)

        # 4. Start Phase 1: The Check
        threading.Thread(
            target=self._run_update_check_phase,
            args=(text_area, install_btn, close_btn, close_app_btn, script_path, status_popup),
            daemon=True
        ).start()

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
        
        # Project dir is one level up from src
        base_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.dirname(base_dir)
        
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
