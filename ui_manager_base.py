# keglevel app
#
# ui_manager_base.py
import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont 
import math
import time
import queue
import os
import uuid 
import subprocess 
import sys      

# --- NEW: Import platform flag from sensor_logic ---
# FIX: IS_RASPBERRY_PI_MODE is still needed, keep import.
try:
    from sensor_logic import IS_RASPBERRY_PI_MODE
except ImportError:
    IS_RASPBERRY_PI_MODE = False
# ------------------------------------

# FIX: Import UNASSIGNED_KEG_ID from settings_manager module
try:
    from settings_manager import UNASSIGNED_KEG_ID
except ImportError:
    UNASSIGNED_KEG_ID = "unassigned_keg_id"


# --- NEW: Application Revision Variable ---
APP_REVISION = "20251004.01 Beta" 
# ------------------------------------------

LITERS_TO_GALLONS = 0.264172
# CONSTANT: Ratio of US Fluid Ounces to Liters
OZ_TO_LITERS = 0.0295735

# --- BASE CLASS: Contains main window layout and update logic ---
class MainUIBase:
    def __init__(self, root, settings_manager_instance, sensor_logic_instance, notification_service_instance, temp_logic_instance, num_sensors, app_version_string):
        self.root = root
        self.settings_manager = settings_manager_instance
        self.sensor_logic = sensor_logic_instance
        self.notification_service = notification_service_instance
        self.temp_logic = temp_logic_instance
        self.num_sensors = num_sensors
        self.num_keg_definitions = 6 # Only 6 definitions are displayed in the UI, even if 20 are stored
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.app_version_string = app_version_string

        self.ui_mode = self.settings_manager.get_system_settings().get('ui_mode', 'full') 
        self.is_full_mode = (self.ui_mode == 'full')

        self.ui_update_queue = queue.Queue()

        self.root.title("KegLevel Monitor")
        
        if self.is_full_mode:
            self.root.geometry("1920x430+0+36") 
            self.root.resizable(True, True) 
        else:
            self.root.geometry("800x536+0+36") 
            self.root.resizable(False, False)
            
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing_ui) 

        # --- Primary UI Variables ---
        self.sensor_name_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        # MODIFIED: Flow rate L/min (Uses the 'lidar' variables from the old structure)
        self.flow_rate_label_texts = [tk.StringVar(value="Flow rate L/min:") for _ in range(self.num_sensors)] 
        self.flow_rate_value_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        self.volume1_label_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        self.volume1_value_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        self.volume2_label_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        self.volume2_value_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        # REMOVED: self.monitoring_text = tk.StringVar(value="Monitoring")
        self.temperature_text = tk.StringVar(value="Temp: --.- F")
        self.notification_status_text = tk.StringVar(value="Notifications: Idle")
        
        # --- Tap-specific Control Variables ---
        self.sensor_beverage_selection_vars = [tk.StringVar() for _ in range(self.num_sensors)]
        self.sensor_beverage_dropdowns = [None] * self.num_sensors
        self.sensor_keg_selection_vars = [tk.StringVar() for _ in range(self.num_sensors)]
        self.sensor_keg_dropdowns = [None] * self.num_sensors

        # --- Full Mode Metadata Variables (Unchanged) ---
        self.beverage_metadata_texts = []
        for _ in range(self.num_sensors):
            self.beverage_metadata_texts.append({
                'name': tk.StringVar(),
                'bjcp': tk.StringVar(),
                'abv': tk.StringVar(),
                'ibu': tk.StringVar(),
                'description': tk.StringVar()
            })
        
        # --- Internal State Variables (Unchanged) ---
        self.header_is_animating = False
        self.header_animation_base_text = ""
        self.current_animation_frame = 0
        self.header_animation_job_id = None
        self.sensor_progressbars = [None] * self.num_sensors
        self.progressbar_styles_defined = False
        self.was_stable_before_pause = [False] * self.num_sensors
        self.sensor_is_actively_connected = [False] * self.num_sensors
        self.last_known_average_mm = [None] * self.num_sensors
        self.last_known_remaining_liters = [None] * self.num_sensors
        
        self.workflow_app = None 
        
        self.sensor_column_frames = [None] * self.num_sensors
        self.settings_menubutton = None 
        # REMOVED: self.pause_resume_button = None
        # REMOVED: self.monitoring_label = None
        self.temperature_label = None
        self.notification_status_label = None

        self._create_widgets()
        self._load_initial_ui_settings()
        # _refresh_ui_for_settings_or_resume will be called as part of _load_initial_ui_settings, 
        # which now correctly applies the labels.
        self._poll_ui_update_queue()
        
    def _define_progressbar_styles(self):
        if not self.progressbar_styles_defined:
            s = ttk.Style(self.root)
            try: s.theme_use('default')
            except tk.TclError: print("UIManager Warning: 'default' theme not available.")

            common_opts = {'troughcolor': '#E0E0E0', 'borderwidth': 1, 'relief': 'sunken'}
            s.configure("green.Horizontal.TProgressbar", background='green', **common_opts)
            # (3) Red and Yellow styles defined but not used for fill now
            s.configure("red.Horizontal.TProgressbar", background='#DC143C', **common_opts) 
            s.configure("yellow.Horizontal.TProgressbar", background='#FFDB58', **common_opts)
            s.configure("gray.Horizontal.TProgressbar", background='#a0a0a0', **common_opts)
            s.configure("default.Horizontal.TProgressbar", background='#007bff', **common_opts)
            
            # (3) NEW: Define a neutral style for non-critical non-stable states
            s.configure("neutral.Horizontal.TProgressbar", background='#C0C0C0', **common_opts)
            
            self.progressbar_styles_defined = True
            return s
        return ttk.Style(self.root)

    def _create_widgets(self):
        s = self._define_progressbar_styles()
        s.configure('Tap.Bold.TLabel', font=('TkDefaultFont', 10, 'bold'))
        s.configure('Metadata.Bold.TLabel', font=('TkDefaultFont', 9, 'bold'))
        s.configure('LightGray.TFrame', background='#F0F0F0')
        
        self.header_frame = ttk.Frame(self.root)
        self.header_frame.pack(padx=10, pady=(10,0), fill="x", anchor="n")
        
        # --- Header Layout Logic ---
        
        # (1) REMOVED: Status area (monitoring_label_container and monitoring_label)
        
        action_buttons_frame = ttk.Frame(self.header_frame)
        # Shift action buttons to the left now that the monitoring label is gone.
        # This keeps the settings button grouped with the temp display on the right.
        action_buttons_frame.pack(side="right", padx=0, pady=0)
        
        # 3. Settings Dropdown (rightmost)
        self.settings_menubutton = ttk.Menubutton(action_buttons_frame, text="Settings", width=12)
        default_font = tkfont.nametofont("TkMenuFont")
        self.menu_heading_font = tkfont.Font(family=default_font['family'], size=default_font['size'], weight="bold")
        
        # --- FIX: Added disabledforeground="black" so headers appear black ---
        self.settings_menu = tk.Menu(self.settings_menubutton, tearoff=0, disabledforeground="black")
        # ---------------------------------------------------------------------
        
        self.settings_menubutton["menu"] = self.settings_menu
        self.settings_menubutton.pack(side="right", padx=(0, 0), pady=0) 

        # (2) REMOVED: Pause/Resume Button
        # self.pause_resume_button = ttk.Button(action_buttons_frame,text="Pause Monitoring",command=self._toggle_pause_resume, width=16); 
        # self.pause_resume_button.pack(side="right", padx=(0, 17), pady=0)

        # 5. Temperature Label (Temp area)
        # Note: The temperature area now takes up the space previously occupied by Pause/Resume and Status area
        if self.is_full_mode: temp_label_container = ttk.Frame(self.header_frame, width=120, height=26)
        else: temp_label_container = ttk.Frame(self.header_frame, width=200, height=26)
            
        # Place the Temperature Label immediately to the left of the Settings button
        temp_label_container.pack_propagate(False); temp_label_container.pack(side="right", padx=(0, 10), pady=0)
        self.temperature_label = ttk.Label(temp_label_container, textvariable=self.temperature_text, relief="sunken", padding=(5, 2), anchor=tk.W)
        self.temperature_label.pack(fill='both', expand=True)
        
        # --- Main Column Frame ---
        self.main_columns_frame = ttk.Frame(self.root); 
        self.main_columns_frame.pack(padx=10, pady=(20, 0), fill="both", expand=True)
        cols_per_row = 5
        for col_idx in range(cols_per_row): self.main_columns_frame.grid_columnconfigure(col_idx, weight=1, minsize=150)
        self.main_columns_frame.grid_rowconfigure(0, weight=1); self.main_columns_frame.grid_rowconfigure(1, weight=1)

        # --- TAP COLUMN CREATION LOOP (Unchanged) ---
        WRAPLENGTH_TAP_COLUMN = 300 
        
        for i in range(self.num_sensors):
            column_frame = ttk.Frame(self.main_columns_frame, padding=(3,3)); self.sensor_column_frames[i] = column_frame
            
            # 1. Tap Number/Beverage Name/Dropdown area
            if self.is_full_mode:
                name_frame = ttk.Frame(column_frame)
                name_frame.pack(anchor="w", pady=(0, 2), fill="x")
                ttk.Label(name_frame, text=f"Tap {i + 1}:", style='Tap.Bold.TLabel').pack(side="left", padx=(0, 5))
            else:
                tap_num_frame = ttk.Frame(column_frame)
                tap_num_frame.pack(anchor="w", pady=(0, 2), fill="x")
                ttk.Label(tap_num_frame, text=f"Tap {i + 1}:", style='Tap.Bold.TLabel').pack(side="left", padx=(0, 5))
                name_frame = ttk.Frame(column_frame)
                name_frame.pack(anchor="w", pady=(0, 2), fill="x")
                
            beverage_dropdown = ttk.Combobox(name_frame, textvariable=self.sensor_beverage_selection_vars[i], state="readonly", width=16) 
            beverage_dropdown.pack(side="left", fill="x", expand=True); 
            beverage_dropdown.bind("<<ComboboxSelected>>", lambda event, idx=i: self._handle_beverage_selection_change(idx))
            self.sensor_beverage_dropdowns[i] = beverage_dropdown

            # 2. Beverage Metadata Display (Unchanged structure)
            if self.is_full_mode:
                METADATA_HEIGHT = 160 
                metadata_container = ttk.Frame(column_frame, height=METADATA_HEIGHT, style='LightGray.TFrame') 
                metadata_container.pack_propagate(False); metadata_container.pack(anchor="w", pady=(2, 5), fill="x")
                metadata_frame = ttk.Frame(metadata_container, padding=(5, 5), relief='flat', style='LightGray.TFrame') 
                metadata_frame.pack(fill="both", expand=True) 
                
                metadata_row1 = ttk.Frame(metadata_frame, style='LightGray.TFrame'); metadata_row1.pack(anchor="w", fill="x")
                ttk.Label(metadata_row1, text="BJCP:", style='Metadata.Bold.TLabel', background='#F0F0F0').pack(side="left", padx=(0, 2))
                ttk.Label(metadata_row1, textvariable=self.beverage_metadata_texts[i]['bjcp'], background='#F0F0F0').pack(side="left", padx=(0, 10), anchor='w')

                ibu_frame = ttk.Frame(metadata_row1, style='LightGray.TFrame'); ibu_frame.pack(side="right", anchor='e')
                ttk.Label(ibu_frame, textvariable=self.beverage_metadata_texts[i]['ibu'], anchor='e', background='#F0F0F0').pack(side="right")
                ttk.Label(ibu_frame, text="IBU:", style='Metadata.Bold.TLabel', background='#F0F0F0').pack(side="right", padx=(0, 2))
                
                abv_frame = ttk.Frame(metadata_row1, style='LightGray.TFrame'); abv_frame.pack(side="right", anchor='e', padx=(20, 10)) 
                ttk.Label(abv_frame, textvariable=self.beverage_metadata_texts[i]['abv'], anchor='e', background='#F0F0F0').pack(side="right")
                ttk.Label(abv_frame, text="ABV:", style='Metadata.Bold.TLabel', background='#F0F0F0').pack(side="right", padx=(0, 2))

                description_label = ttk.Label(metadata_frame, textvariable=self.beverage_metadata_texts[i]['description'], 
                                              anchor='nw', font=('TkDefaultFont', 11, 'italic'), justify=tk.LEFT,
                                              wraplength=WRAPLENGTH_TAP_COLUMN, background='#F0F0F0') 
                description_label.pack(anchor="w", fill="both", expand=True, pady=(5, 5)) 
            
            # --- LITE MODE METADATA DISPLAY (Unchanged structure) ---
            else: 
                metadata_line_frame = ttk.Frame(column_frame)
                metadata_line_frame.pack(anchor="w", pady=(2, 0), fill="x")

                ttk.Label(metadata_line_frame, text="ABV:", style='Metadata.Bold.TLabel').pack(side="left", padx=(0, 5))
                ttk.Label(metadata_line_frame, textvariable=self.beverage_metadata_texts[i]['abv']).pack(side="left", anchor="w")

                ttk.Label(metadata_line_frame, textvariable=self.beverage_metadata_texts[i]['ibu']).pack(side="right", anchor="e")
                ttk.Label(metadata_line_frame, text="IBU:", style='Metadata.Bold.TLabel').pack(side="right", padx=(5, 2))
            # --- END LITE MODE METADATA DISPLAY ---
            
            # 3. Progress Bar (Unchanged)
            pb = ttk.Progressbar(column_frame, orient="horizontal", mode="determinate", maximum=100, style="red.Horizontal.TProgressbar")
            pb.pack(pady=(10,5), fill='x', expand=False); self.sensor_progressbars[i] = pb
            
            # 4. Measurements (MODIFIED: Flow Rate L/min)
            lidar_frame = ttk.Frame(column_frame); lidar_frame.pack(anchor="w", fill="x", pady=1)
            ttk.Label(lidar_frame, textvariable=self.flow_rate_label_texts[i]).pack(side="left", padx=(0, 2))
            ttk.Label(lidar_frame, textvariable=self.flow_rate_value_texts[i], width=15, anchor="w").pack(side="left", padx=(0,0)) 
            
            vol1_frame = ttk.Frame(column_frame); vol1_frame.pack(anchor="w", fill="x", pady=1)
            ttk.Label(vol1_frame, textvariable=self.volume1_label_texts[i]).pack(side="left", padx=(0, 2))
            ttk.Label(vol1_frame, textvariable=self.volume1_value_texts[i], width=5, anchor="w").pack(side="left", padx=(0,0))
            
            vol2_frame = ttk.Frame(column_frame); vol2_frame.pack(anchor="w", fill="x", pady=1)
            ttk.Label(vol2_frame, textvariable=self.volume2_label_texts[i]).pack(side="left", padx=(0, 2))
            ttk.Label(vol2_frame, textvariable=self.volume2_value_texts[i], width=5, anchor="w").pack(side="left", padx=(0,0))
            
            # 5. Keg Dropdown (MODIFIED: Added "Keg:" label)
            dropdowns_frame = ttk.Frame(column_frame); dropdowns_frame.pack(anchor="w", fill="x", pady=(10, 5)) 
            
            # NEW LABEL: "Keg:"
            ttk.Label(dropdowns_frame, text="Keg:").pack(side="left", padx=(0, 5))

            keg_dropdown = ttk.Combobox(dropdowns_frame, textvariable=self.sensor_keg_selection_vars[i], state="readonly", width=12)
            
            if self.is_full_mode:
                keg_dropdown.pack(side="left", fill="x", expand=True, padx=(0, 5)) 
            else:
                keg_dropdown.pack(fill="x", expand=True)

            keg_dropdown.bind("<<ComboboxSelected>>", lambda event, idx=i: self._handle_keg_selection_change(idx))
            self.sensor_keg_dropdowns[i] = keg_dropdown
            
        # --- Bottom Status Bar (Unchanged) ---
        notification_label_container = ttk.Frame(self.root, height=26)
        notification_label_container.pack_propagate(False); notification_label_container.pack(side="bottom", fill="x", padx=10, pady=(5,5))
        self.notification_status_label = ttk.Label(notification_label_container, textvariable=self.notification_status_text, anchor="w", relief="sunken", padding=(5,2))
        self.notification_status_label.pack(fill='both', expand=True)

    def _load_initial_ui_settings(self):
        loaded_sensor_labels = self.settings_manager.get_sensor_labels()
        for i in range(self.num_sensors):
            self.sensor_name_texts[i].set(loaded_sensor_labels[i])
            self.flow_rate_value_texts[i].set("Init...")
            self.volume1_value_texts[i].set("Init...")
            self.volume2_value_texts[i].set("Init...")
            self.sensor_is_actively_connected[i] = False
            self.was_stable_before_pause[i] = False
            if self.sensor_progressbars[i]:
                 self._do_update_sensor_stability_display(i, "Acquiring data...")
        self._populate_keg_dropdowns()
        self._populate_beverage_dropdowns()
        self._refresh_beverage_metadata()
        
        # CRITICAL FIX: Ensure full UI refresh after initial load to set correct labels/units
        self._refresh_ui_for_settings_or_resume()


    def _poll_ui_update_queue(self):
        try:
            while True:
                task, args = self.ui_update_queue.get_nowait()
                if task == "update_sensor_data": self._do_update_sensor_data_display(*args)
                elif task == "update_sensor_stability": self._do_update_sensor_stability_display(*args)
                elif task == "update_header_status": self._do_update_header_status(*args)
                elif task == "update_notification_status": self._do_update_notification_status_display(*args)
                elif task == "update_sensor_connection": self._do_update_sensor_connection_status(*args)
                elif task == "update_temp_display": self._do_update_temperature_display(*args)
                # --- NEW: Calibration Data Handler ---
                # FIX: Route the queue task to the mixin's update method
                elif task == "update_cal_data": self._update_single_cal_data(*args)
                # ------------------------------------
                self.ui_update_queue.task_done()
        except queue.Empty: pass
        finally:
            if self.root.winfo_exists(): self.root.after(100, self._poll_ui_update_queue)    

    def update_temperature_display(self, temp_value, unit):
        self.ui_update_queue.put(("update_temp_display", (temp_value, unit)))

    def _do_update_temperature_display(self, temp_value, unit):
        # (3) UPDATED: Temp display logic to only show value or --.-
        if not self.root.winfo_exists(): return
        
        # Check if temp_value is a valid number
        is_valid_temp = isinstance(temp_value, (int, float)) and temp_value is not None
        
        if is_valid_temp:
            # Determine the unit to display (C or F)
            current_display_unit = self.settings_manager.get_display_units()
            
            unit_char = unit
            # This logic block seems inverted and complex. Simplifying unit selection based on settings.
            if current_display_unit == "imperial":
                unit_char = "F"
                # If the input temp was provided in C (unit == "C"), convert it to F for display
                if unit == "C":
                    temp_value = (temp_value * 9/5) + 32
            else: # metric
                unit_char = "C"
                # If the input temp was provided in F (unit == "F"), convert it to C for display
                if unit == "F":
                    temp_value = (temp_value - 32) * (5/9)
            
            # Final display formatting
            self.temperature_text.set(f"Temp: {temp_value:.1f} {unit_char}")
        else:
            # If not a valid temperature (None, "No Sensor", "Error", etc.), display dashes and the expected unit
            # Determine the expected unit based on settings for display
            current_display_unit = self.settings_manager.get_display_units()
            unit_char = "F" if current_display_unit == "imperial" else "C"
            self.temperature_text.set(f"Temp: --.- {unit_char}")

    # MODIFIED: flow_rate_lpm replaces current_average_mm_float
    def update_sensor_data_display(self, sensor_index, flow_rate_lpm, remaining_liters_float, status_string):
        self.ui_update_queue.put(("update_sensor_data", (sensor_index, flow_rate_lpm, remaining_liters_float, status_string)))

    # MODIFIED: flow_rate_lpm replaces current_average_mm_float
    def _do_update_sensor_data_display(self, sensor_index, flow_rate_lpm, remaining_liters_float, status_string):
        if not self.root.winfo_exists() or not (0 <= sensor_index < self.num_sensors): return
        
        # --- Status strings for flow sensor are simplified ---
        if status_string == "Hardware Fault" or status_string == "Error" or status_string == "Missing" or status_string == "Sensor Unplugged":
            self.flow_rate_label_texts[sensor_index].set("Flow rate L/min:") # Reset label
            self.flow_rate_value_texts[sensor_index].set("-- (Error/Missing)")
            self.volume1_value_texts[sensor_index].set("--"); self.volume2_value_texts[sensor_index].set("--")
            self.last_known_remaining_liters[sensor_index] = None
            self.sensor_is_actively_connected[sensor_index] = False
            self._do_update_sensor_stability_display(sensor_index, "Acquiring data...")
            return
        
        # --- Nominal Data (Status: Nominal) ---
        self.sensor_is_actively_connected[sensor_index] = True
        self.flow_rate_label_texts[sensor_index].set("Flow rate L/min:")

        # Flow Rate L/min (always display in L/min)
        flow_rate_display = f"{flow_rate_lpm:.2f}" if flow_rate_lpm is not None else "0.00"
        self.flow_rate_value_texts[sensor_index].set(flow_rate_display)
        
        if remaining_liters_float is not None: 
             self.last_known_remaining_liters[sensor_index] = remaining_liters_float
        
        display_units = self.settings_manager.get_display_units()
        if remaining_liters_float is not None:
            # Get configured pour volumes
            pour_settings = self.settings_manager.get_pour_volume_settings()
            
            if display_units == "imperial":
                gallons = remaining_liters_float * LITERS_TO_GALLONS
                
                # Use configured imperial pour size (oz)
                pour_oz = pour_settings['imperial_pour_oz']
                # Convert pour size (oz) to Liters to get the division factor
                liters_per_pour = pour_oz * OZ_TO_LITERS
                
                # Calculate servings: Remaining Liters / Liters per Pour
                servings_remaining = math.floor(remaining_liters_float / liters_per_pour) if liters_per_pour > 0 else 0
                
                self.volume1_value_texts[sensor_index].set(f"{gallons:.2f}")
                self.volume2_value_texts[sensor_index].set(f"{int(servings_remaining)}")
            else:
                liters = remaining_liters_float
                
                # Use configured metric pour size (ml)
                pour_ml = pour_settings['metric_pour_ml']
                # Convert pour size (ml) to Liters to get the division factor
                liters_per_pour = pour_ml / 1000.0
                
                # Calculate servings: Remaining Liters / Liters per Pour
                servings_remaining = math.floor(liters / liters_per_pour) if liters_per_pour > 0 else 0
                
                self.volume1_value_texts[sensor_index].set(f"{liters:.2f}")
                self.volume2_value_texts[sensor_index].set(f"{int(servings_remaining)}")
        else:
            self.flow_rate_value_texts[sensor_index].set("Init...")
            self.volume1_value_texts[sensor_index].set("Init..."); self.volume2_value_texts[sensor_index].set("Init...")

    def update_sensor_stability_display(self, sensor_index, status_text_from_logic):
        self.ui_update_queue.put(("update_sensor_stability", (sensor_index, status_text_from_logic)))

    # ui_manager_base.py (Complete, Fixed Function)

    def _do_update_sensor_stability_display(self, sensor_index, status_text_from_logic):
        if not self.root.winfo_exists() or not (0 <= sensor_index < self.num_sensors): return
        pb = self.sensor_progressbars[sensor_index]
        if not pb: return

        # IMPORTANT: Keep the Paused check here for when sensor_logic is paused, 
        # even if the Pause/Resume button is removed.
        if self.sensor_logic and self.sensor_logic.is_paused and status_text_from_logic != "Paused": return

        current_percentage = 0
        liters_val = self.last_known_remaining_liters[sensor_index]
        if liters_val is not None:
            keg_id = self.settings_manager.get_sensor_keg_assignments()[sensor_index]
            keg_params = self.settings_manager.get_keg_by_id(keg_id)
            
            # Use the keg's starting_volume_liters as the max for the progress bar
            # FIX: Use imported UNASSIGNED_KEG_ID
            if keg_params and keg_params.get('id') != UNASSIGNED_KEG_ID:
                
                # --- CRITICAL FIX: Use 'maximum_full_volume_liters' (18.93L) for the 100% reference ---
                total_keg_volume_liters_for_100_percent = float(keg_params.get('maximum_full_volume_liters', 0))
                
                if total_keg_volume_liters_for_100_percent > 0:
                    percentage_calc = (liters_val / total_keg_volume_liters_for_100_percent) * 100
                    current_percentage = max(0, min(percentage_calc, 100))
                # ----------------------------------------------------------------------------------------
                
            # If keg is unassigned, progress bar stays at 0 (implicitly handled by current_percentage=0)

        current_style = pb.cget('style')
        new_style = current_style
        new_value = pb['value']

        if status_text_from_logic == "Data stable":
            new_style = "green.Horizontal.TProgressbar"
            new_value = current_percentage
            self.was_stable_before_pause[sensor_index] = True
            
        elif status_text_from_logic == "Acquiring data...":
            if self.sensor_is_actively_connected[sensor_index]:
                # (3) Changed from "yellow.Horizontal.TProgressbar" to neutral/gray
                new_style = "neutral.Horizontal.TProgressbar" 
                new_value = 100
            else:
                # (3) Changed from "red.Horizontal.TProgressbar" to neutral/gray
                new_style = "neutral.Horizontal.TProgressbar" 
                new_value = 100
                
            self.was_stable_before_pause[sensor_index] = False
            
        elif status_text_from_logic == "Hardware Fault":
            # (3) Changed from "red.Horizontal.TProgressbar" to neutral/gray
            new_style = "neutral.Horizontal.TProgressbar" 
            new_value = 100
            self.was_stable_before_pause[sensor_index] = False
             
        elif status_text_from_logic == "Error":
             # (3) Changed from "yellow.Horizontal.TProgressbar" to neutral/gray
             new_style = "neutral.Horizontal.TProgressbar" 
             new_value = 100 
             self.was_stable_before_pause[sensor_index] = False
             
        elif status_text_from_logic == "Paused":
            new_style = "gray.Horizontal.TProgressbar"
            if self.was_stable_before_pause[sensor_index]: new_value = current_percentage
            else: new_value = 100
            self.flow_rate_value_texts[sensor_index].set("Paused")
            
        else: 
            # (3) Changed from "red.Horizontal.TProgressbar" to neutral/gray
            new_style = "neutral.Horizontal.TProgressbar"
            new_value = 100
            self.was_stable_before_pause[sensor_index] = False

        if current_style != new_style or abs(pb['value'] - new_value) > 0.1 :
            pb.config(style=new_style); pb['value'] = new_value

    def update_sensor_connection_status(self, sensor_index, is_connected):
        self.ui_update_queue.put(("update_sensor_connection", (sensor_index, is_connected)))
        
    def _do_update_sensor_connection_status(self, sensor_index, is_connected):
        if not self.root.winfo_exists() or not (0 <= sensor_index < self.num_sensors): return
        previous_connection_state = self.sensor_is_actively_connected[sensor_index]
        self.sensor_is_actively_connected[sensor_index] = is_connected
        connection_state_changed = (previous_connection_state != is_connected)
        current_style_is_gray = False
        pb = self.sensor_progressbars[sensor_index]
        if pb:
            current_style_name = pb.cget('style')
            if "gray" in str(current_style_name).lower(): current_style_is_gray = True

        if self.sensor_logic and not self.sensor_logic.is_paused:
            if connection_state_changed or current_style_is_gray: self._do_update_sensor_stability_display(sensor_index, "Acquiring data...")

    def update_header_status(self, animate, base_text, is_animating_flag_val_unused):
        # NOTE: This function is still needed as it is called by SensorLogic (see sensor_logic.py:126, 137, 240)
        # Even though the status area is removed, we must maintain the function signature to prevent crashes.
        # However, as per user instruction (1), the status area logic is now a no-op inside here.
        self.ui_update_queue.put(("update_header_status", (animate, base_text, is_animating_flag_val_unused)))
        
    def _do_update_header_status(self, animate, base_text, is_animating_flag_val_unused):
        # (1) REMOVED: Status display functionality is removed, this function is now a NO-OP
        pass
        
    def _animate_header_text(self):
        # Animation disabled
        pass

    def update_notification_status_display(self, message):
        self.ui_update_queue.put(("update_notification_status", (message,)))
    def _do_update_notification_status_display(self, message):
        if hasattr(self, 'notification_status_text') and self.root.winfo_exists():
            current_time = time.strftime("%m/%d/%y %H:%M:%S")
            self.notification_status_text.set(f"[{current_time}] {message}")

    def _populate_keg_dropdowns(self):
        # Get the 6 displayable kegs from the full library, sorted by title
        all_keg_defs = self.settings_manager.get_keg_definitions()
        
        # Sort all kegs alphabetically by title
        sorted_keg_defs = sorted(all_keg_defs, key=lambda k: k.get('title', '').lower())

        # The displayed list includes "Offline" + the first N sorted entries
        display_kegs = sorted_keg_defs[:self.num_keg_definitions]
        
        # (1) Change "Unassigned" to "Offline"
        unassigned_id = UNASSIGNED_KEG_ID
        unassigned_title = "Offline" 
        
        keg_titles = [unassigned_title] + [keg.get('title', f"Keg {i+1:02}") for i, keg in enumerate(display_kegs)]
        keg_id_to_title = {unassigned_id: unassigned_title}
        keg_id_to_title.update({keg['id']: keg['title'] for keg in display_kegs})
        
        # Get the assigned Keg IDs (strings)
        current_assignments_ids = self.settings_manager.get_sensor_keg_assignments()
        
        for i in range(self.num_sensors):
            assigned_id = current_assignments_ids[i]
            assigned_title = keg_id_to_title.get(assigned_id) # Look up title from ID
            
            if self.sensor_keg_dropdowns[i]:
                self.sensor_keg_dropdowns[i]['values'] = keg_titles
                
                if assigned_title:
                    # Assign the Keg Title (string) directly to the StringVar
                    self.sensor_keg_selection_vars[i].set(assigned_title)
                else:
                    # If assignment is invalid, set to Offline and save that change
                    self.sensor_keg_selection_vars[i].set(unassigned_title)
                    self.settings_manager.save_sensor_keg_assignment(i, unassigned_id)
            
    def _populate_beverage_dropdowns(self):
        beverage_library = self.settings_manager.get_beverage_library()
        beverage_list = beverage_library.get('beverages', [])
        beverage_names = [b.get('name', 'Untitled Beverage') for b in beverage_list]
        beverage_ids = [b.get('id') for b in beverage_list]
        current_assignments = self.settings_manager.get_sensor_beverage_assignments()
        id_to_name = {b.get('id'): b.get('name', 'Untitled') for b in beverage_list}

        for i in range(self.num_sensors):
            if self.sensor_beverage_dropdowns[i]: self.sensor_beverage_dropdowns[i]['values'] = beverage_names
            assigned_id = current_assignments[i] if i < len(current_assignments) else None
            assigned_name = id_to_name.get(assigned_id)
            
            if assigned_name and assigned_name in beverage_names:
                self.sensor_beverage_selection_vars[i].set(assigned_name)
            elif beverage_names:
                self.sensor_beverage_selection_vars[i].set(beverage_names[0])
                self.settings_manager.save_sensor_beverage_assignment(i, beverage_ids[0])
            else:
                self.sensor_beverage_selection_vars[i].set("No Beverages")

    def _handle_beverage_selection_change(self, sensor_idx):
        selected_beverage_name = self.sensor_beverage_selection_vars[sensor_idx].get()
        beverage_library = self.settings_manager.get_beverage_library()
        beverage_list = beverage_library.get('beverages', [])
        selected_beverage = next((b for b in beverage_list if b.get('name') == selected_beverage_name), None)
        
        if selected_beverage:
            selected_id = selected_beverage.get('id')
            self.settings_manager.save_sensor_beverage_assignment(sensor_idx, selected_id)
            print(f"UIManager: Tap {sensor_idx+1} assigned to Beverage: {selected_beverage_name} (ID {selected_id})")
            self._refresh_beverage_metadata()
        else:
            print(f"Error: Selected beverage '{selected_beverage_name}' not found.")

    def _refresh_beverage_metadata(self):
        
        beverage_library = self.settings_manager.get_beverage_library()
        beverage_list = beverage_library.get('beverages', [])
        assignments = self.settings_manager.get_sensor_beverage_assignments()
        id_to_beverage = {b.get('id'): b for b in beverage_list if 'id' in b}
        
        for i in range(self.num_sensors):
            if i < self.settings_manager.get_displayed_taps():
                assigned_id = assignments[i] if i < len(assignments) else None
                beverage_data = id_to_beverage.get(assigned_id)
            
                if beverage_data:
                    bjcp_style = beverage_data.get('bjcp', '').strip(); bjcp_text = bjcp_style if bjcp_style else "--"
                    self.beverage_metadata_texts[i]['bjcp'].set(bjcp_text)
                    abv_value = beverage_data.get('abv', '').strip()
                    if abv_value: self.beverage_metadata_texts[i]['abv'].set(f"{abv_value}%")
                    else: self.beverage_metadata_texts[i]['abv'].set('--')
                    ibu_value = beverage_data.get('ibu')
                    ibu_display = str(ibu_value) if ibu_value is not None and str(ibu_value).strip() else "--"
                    self.beverage_metadata_texts[i]['ibu'].set(ibu_display)
                    self.beverage_metadata_texts[i]['description'].set(beverage_data.get('description', ''))
                else:
                    self.beverage_metadata_texts[i]['bjcp'].set('No Beverage Selected')
                    self.beverage_metadata_texts[i]['abv'].set('--'); self.beverage_metadata_texts[i]['ibu'].set('--')
                    self.beverage_metadata_texts[i]['description'].set('')
            else:
                for key in self.beverage_metadata_texts[i]: self.beverage_metadata_texts[i][key].set("")

    def _handle_keg_selection_change(self, sensor_idx):
        selected_keg_title = self.sensor_keg_selection_vars[sensor_idx].get()
        
        # (1) Change "Unassigned" to "Offline"
        if selected_keg_title == "Offline":
            selected_keg_id = UNASSIGNED_KEG_ID
        else:
            all_keg_defs = self.settings_manager.get_keg_definitions()
            # Find the Keg ID associated with the selected title
            selected_keg = next((keg for keg in all_keg_defs if keg.get('title') == selected_keg_title), None)
            
            if not selected_keg:
                print(f"Error: Selected keg title '{selected_keg_title}' not found in library.")
                return 

            selected_keg_id = selected_keg['id']
            
        # 1. Save the new assignment
        self.settings_manager.save_sensor_keg_assignment(sensor_idx, selected_keg_id)
        print(f"UIManager: Tap {sensor_idx+1} assigned to Keg ID: {selected_keg_id}")
        
        # 2. Refresh UI elements (dropdowns, data)
        self._refresh_ui_for_settings_or_resume()
        
        # 3. CRITICAL FIX: Force SensorLogic to immediately reload the dispensed volume 
        #    for *all* sensors (which includes the one that just changed).
        if self.sensor_logic: 
            # Note: The pause/resume function is removed from the UI, but the SensorLogic functions remain in case 
            # they are called elsewhere or needed for maintenance.
            self.sensor_logic.force_recalculation()
            
    def _update_sensor_column_visibility(self):
        displayed_taps_count = self.settings_manager.get_displayed_taps()
        cols_per_row = 5
        for i in range(self.num_sensors):
            column_frame = self.sensor_column_frames[i]
            if column_frame:
                if i < displayed_taps_count:
                    grid_row = i // cols_per_row
                    grid_col = i % cols_per_row
                    is_last_in_visual_row = (grid_col == cols_per_row - 1) or (i == displayed_taps_count - 1)
                    column_padx = (0, 0 if is_last_in_visual_row else 5)
                    total_rows_for_displayed_taps = math.ceil(displayed_taps_count / cols_per_row)
                    is_in_last_displayed_row_visually = (grid_row == total_rows_for_displayed_taps - 1)
                    column_pady = (0, 0 if is_in_last_displayed_row_visually else 5)
                    column_frame.grid(row=grid_row, column=grid_col, padx=column_padx, pady=column_pady, sticky="nsew")
                else: column_frame.grid_remove()

    def _refresh_ui_for_settings_or_resume(self):
        self._update_sensor_column_visibility()
        self._refresh_beverage_metadata()
        self._populate_beverage_dropdowns()
        
        display_units = self.settings_manager.get_display_units()
        displayed_taps_count = self.settings_manager.get_displayed_taps()
        
        # Get configured pour volumes to update labels
        pour_settings = self.settings_manager.get_pour_volume_settings()
        pour_ml = pour_settings['metric_pour_ml']
        pour_oz = pour_settings['imperial_pour_oz']

        for i in range(self.num_sensors):
            if i < displayed_taps_count:
                if display_units == "imperial": 
                    # UPDATED LABELS: "Gallons:" -> "Gal remaining:", "Pints:" -> "Pint servings:"
                    self.volume1_label_texts[i].set("Gal remaining:")
                    # Label now uses configured oz value
                    self.volume2_label_texts[i].set(f"{pour_oz} oz pours:")
                else: 
                    # UPDATED LABELS: "Liters:" -> "Liters remaining:", "500 ml:" -> "400 ml servings:"
                    self.volume1_label_texts[i].set("Liters remaining:")
                    # Label now uses configured ml value
                    self.volume2_label_texts[i].set(f"{pour_ml} ml pours:")
                
                effective_stability_status = "Acquiring data..."
                if self.sensor_logic and self.sensor_logic.is_paused: effective_stability_status = "Paused"
                elif self.last_known_remaining_liters[i] is None and self.sensor_is_actively_connected[i]: effective_stability_status = "Acquiring data..."
                self._do_update_sensor_stability_display(i, effective_stability_status)
                
                # Flow sensors only update when flow occurs or state changes. Ensure volume is displayed if known.
                if self.last_known_remaining_liters[i] is not None and not (self.sensor_logic and self.sensor_logic.is_paused):
                    # Calling _do_update_sensor_data_display here with 0.0 flow rate forces the remaining volume display to update
                    self._do_update_sensor_data_display(i, 0.0, self.last_known_remaining_liters[i], "Nominal")
                elif not (self.sensor_logic and self.sensor_logic.is_paused):
                    self.flow_rate_value_texts[i].set("Init...")
                    self.volume1_value_texts[i].set("Init..."); self.volume2_value_texts[i].set("Init...")
            else:
                self.flow_rate_value_texts[i].set(""); self.volume1_label_texts[i].set(""); self.volume1_value_texts[i].set("");
                self.volume2_label_texts[i].set(""); self.volume2_value_texts[i].set("");
                if i < len(self.sensor_progressbars) and self.sensor_progressbars[i]:
                    self.sensor_progressbars[i].config(style="default.Horizontal.TProgressbar")
                    self.sensor_progressbars[i]['value'] = 0
                if i < len(self.sensor_keg_selection_vars): self.sensor_keg_selection_vars[i].set("")
        self._populate_keg_dropdowns()


    # (2) REMOVED: _toggle_pause_resume method removed
    # def _toggle_pause_resume(self):
    #    ...

    def _open_restart_confirmation_dialog(self):
        """Opens a dialog confirming the need for restart with a restart button."""
        popup = tk.Toplevel(self.root)
        popup.title("Restart Required")
        popup.geometry("350x180")
        popup.transient(self.root)
        popup.grab_set()
        
        frame = ttk.Frame(popup, padding="15"); frame.pack(expand=True, fill="both")
        
        ttk.Label(frame, text="The UI Display Mode has been changed. Please quit and restart the application manually for the changes to take full effect.", 
                  wraplength=300, justify=tk.CENTER).pack(pady=(0, 20))
        
        buttons_frame = ttk.Frame(popup, padding="10"); buttons_frame.pack(fill="x", side="bottom")
        
        ttk.Button(buttons_frame, text="Quit Application", command=lambda: [popup.destroy(), self._on_closing_ui()]).pack(side="right", padx=5)
        ttk.Button(buttons_frame, text="Close", command=popup.destroy).pack(side="right")

    def _on_closing_ui(self):
        print("UIManager: Closing application...")
        current_sensor_names = [sv.get() for sv in self.sensor_name_texts]
        self.settings_manager.save_sensor_labels(current_sensor_names) 

        if self.notification_service: self.notification_service.stop_scheduler()
        if self.sensor_logic: self.sensor_logic.stop_monitoring()
        if self.temp_logic: self.temp_logic.stop_monitoring()

        self.header_is_animating = False
        if self.header_animation_job_id:
            try: self.root.after_cancel(self.header_animation_job_id)
            except tk.TclError: pass
            self.header_animation_job_id = None
        if self.root and hasattr(self.root, 'winfo_exists') and self.root.winfo_exists(): self.root.destroy()
        print("UIManager: Application closed.")

    def run(self):
        self.root.mainloop()
