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
try:
    from sensor_logic import IS_RASPBERRY_PI_MODE
except ImportError:
    IS_RASPBERRY_PI_MODE = False
# ------------------------------------

# FIX: Import UNASSIGNED_KEG_ID and UNASSIGNED_BEVERAGE_ID from settings_manager module
try:
    from settings_manager import UNASSIGNED_KEG_ID, UNASSIGNED_BEVERAGE_ID
except ImportError:
    UNASSIGNED_KEG_ID = "unassigned_keg_id"
    UNASSIGNED_BEVERAGE_ID = "unassigned_beverage_id"


# --- NEW: Application Revision Variable ---
APP_REVISION = "20251004.03 Fixed" 
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
        
        # State variable to prevent redundant X11 calls (Fixes X connection crash)
        self._last_applied_geometry = None

        self.root.title("KegLevel Monitor")
        
        # Apply geometry logic immediately on startup
        self._apply_window_geometry(set_position=True)
            
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing_ui) 

        # --- Primary UI Variables ---
        self.sensor_name_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        self.flow_rate_label_texts = [tk.StringVar(value="Flow rate L/min:") for _ in range(self.num_sensors)] 
        self.flow_rate_value_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        self.volume1_label_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        self.volume1_value_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        self.volume2_label_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        self.volume2_value_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        self.temperature_text = tk.StringVar(value="Temp: --.- F")
        self.notification_status_text = tk.StringVar(value="Notifications: Idle")
        
        # --- Tap-specific Control Variables ---
        self.sensor_beverage_selection_vars = [tk.StringVar() for _ in range(self.num_sensors)]
        self.sensor_beverage_dropdowns = [None] * self.num_sensors
        self.sensor_keg_selection_vars = [tk.StringVar() for _ in range(self.num_sensors)]
        self.sensor_keg_dropdowns = [None] * self.num_sensors

        # --- Full Mode Metadata Variables ---
        self.beverage_metadata_texts = []
        for _ in range(self.num_sensors):
            self.beverage_metadata_texts.append({
                'name': tk.StringVar(),
                'bjcp': tk.StringVar(),
                'abv': tk.StringVar(),
                'ibu': tk.StringVar(),
                'description': tk.StringVar()
            })
        
        # --- Internal State Variables ---
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
        self.temperature_label = None
        self.notification_status_label = None

        self._create_widgets()
        self._load_initial_ui_settings()
        self._poll_ui_update_queue()

    def _apply_window_geometry(self, set_position=False):
        """
        Calculates and applies the window size based on the number of displayed taps.
        Checks for redundancy to prevent X11 crashes.
        NOTE: Uses self.ui_mode (startup state) to prevent on-the-fly switching.
        """
        # --- FIXED: Do NOT re-fetch ui_mode here. We stick to the startup mode 
        # so that if the user changes it, the app visually stays put until restart.

        if self.is_full_mode:
            displayed_taps = self.settings_manager.get_displayed_taps()
            
            CARD_WIDTH = 380
            PADDING = 20 
            
            # Calculate Width
            columns_to_show = min(displayed_taps, 5)
            effective_columns = max(1, columns_to_show) # Minimum 1 column
            
            width = (effective_columns * CARD_WIDTH) + PADDING
                
            # Calculate Height
            if displayed_taps > 5:
                height = 800 
            else:
                height = 430 
            
            # OPTIMIZATION: Prevent redundant X11 calls
            target_size_str = f"{width}x{height}"
            if not set_position and self._last_applied_geometry == target_size_str:
                return

            # Construct geometry string
            if set_position:
                geo_string = f"{width}x{height}+0+36"
            else:
                geo_string = f"{width}x{height}"
            
            try:
                self.root.geometry(geo_string) 
                self.root.resizable(False, False)
                self._last_applied_geometry = target_size_str
            except Exception:
                pass 
                
        else:
            # Compact Mode
            target_size_str = "800x536"
            if not set_position and self._last_applied_geometry == target_size_str:
                return

            if set_position:
                self.root.geometry("800x536+0+36")
            else:
                self.root.geometry("800x536")
                
            self.root.resizable(False, False)
            self._last_applied_geometry = target_size_str
        
    def _srm_to_hex(self, srm):
        """
        Converts an SRM value (float) to a Hex Color Code approximation.
        UPDATED: Uses a vibrant color palette based on visual brewing charts 
        (Davison/Mosher) which corresponds to the Morey SRM scale. 
        Prevents colors from becoming muddy/black too early in the range.
        """
        if srm is None: return None
        
        # Clamp between 0 and 40
        srm = max(0, min(40, int(srm)))
        
        # Custom Palette (0=White/Clear)
        # Source: Visual interpolation of standard SRM/Lovibond reference cards
        srm_colors = {
            0: "#FFFFFF",  # White / Clear
            1: "#FFE699",  # Pale Straw
            2: "#FFD878",  # Straw
            3: "#FFCA5A",  # Pale Gold
            4: "#FFBF42",  # Deep Gold
            5: "#FBB123",  # Golden Amber
            6: "#F8A600",  # Deep Amber
            7: "#F39C00",  # Amber
            8: "#EA8F00",  # Deep Amber / Light Copper
            9: "#E58500",  # Copper
            10: "#DE7C00", # Deep Copper
            11: "#D77200", # Light Brown / Red
            12: "#CF6900", # Medium Amber / Red-Orange
            13: "#CB6200", # Red-Brown
            14: "#C35900", # Red-Brown
            15: "#BB5100", # Deep Red-Brown
            16: "#B54C00", # Dark Amber
            17: "#B04500", # Deep Amber / Brown
            18: "#A63E00", # Brown-Red
            19: "#A13700", # Brown-Red
            20: "#9B3200", # Brown
            21: "#962D00", # Deep Brown
            22: "#8F2900", # Dark Brown
            23: "#882300", # Very Dark Brown
            24: "#821E00", # Ruby Brown
            25: "#7B1A00", # Deep Ruby Brown
            26: "#771900", # Dark Ruby
            27: "#701400", # Deep Red / Black
            28: "#6A0E00", # Dark Brown / Black
            29: "#660D00", # Deep Brown / Black
            30: "#5E0B00", # Black / Red tints
            31: "#5A0A02", # Deep Black / Red tints
            32: "#600903", # Black
            33: "#520907", # Black (Fixed Quotes)
            34: "#4C0505", # Black
            35: "#470606", # Black
            36: "#440607", # Black
            37: "#3F0708", # Black
            38: "#3B0607", # Black
            39: "#3A070B", # Black
            40: "#36080A"  # Black
        }
        
        return srm_colors.get(srm, "#E5A128")

    def _define_progressbar_styles(self):
        if not self.progressbar_styles_defined:
            s = ttk.Style(self.root)
            try: s.theme_use('default')
            except tk.TclError: print("UIManager Warning: 'default' theme not available.")

            common_opts = {'troughcolor': '#E0E0E0', 'borderwidth': 1, 'relief': 'sunken'}
            
            s.configure("green.Horizontal.TProgressbar", background='green', **common_opts)
            s.configure("neutral.Horizontal.TProgressbar", background='#C0C0C0', **common_opts)
            s.configure("red.Horizontal.TProgressbar", background='#DC143C', **common_opts) 
            s.configure("yellow.Horizontal.TProgressbar", background='#FFDB58', **common_opts)
            s.configure("gray.Horizontal.TProgressbar", background='#a0a0a0', **common_opts)
            s.configure("default.Horizontal.TProgressbar", background='#007bff', **common_opts)
            
            for i in range(self.num_sensors):
                style_name = f"Tap{i}.Horizontal.TProgressbar"
                s.configure(style_name, background='green', **common_opts)
            
            self.progressbar_styles_defined = True
            return s
        return ttk.Style(self.root)

    def _update_tap_progress_bar_colors(self):
        try:
            assignments = self.settings_manager.get_sensor_beverage_assignments()
            beverage_library = self.settings_manager.get_beverage_library().get('beverages', [])
            beverage_map = {b['id']: b for b in beverage_library if 'id' in b}
            s = ttk.Style()
            
            for i in range(self.num_sensors):
                bar_color = 'green'
                if i < len(assignments):
                    b_id = assignments[i]
                    if b_id == UNASSIGNED_BEVERAGE_ID:
                        bar_color = '#C0C0C0' 
                    else:
                        beverage = beverage_map.get(b_id)
                        if beverage:
                            srm_val = beverage.get('srm')
                            if srm_val is None: srm_val = 5
                            hex_color = self._srm_to_hex(srm_val)
                            if hex_color: bar_color = hex_color
                style_name = f"Tap{i}.Horizontal.TProgressbar"
                s.configure(style_name, background=bar_color)
        except Exception as e:
            print(f"UIManager Error updating progress bar colors: {e}")

    def _create_widgets(self):
        s = self._define_progressbar_styles()
        s.configure('Tap.Bold.TLabel', font=('TkDefaultFont', 10, 'bold'))
        s.configure('Metadata.Bold.TLabel', font=('TkDefaultFont', 9, 'bold'))
        s.configure('LightGray.TFrame', background='#F0F0F0')
        
        # --- 1. HEADER (PACKED) ---
        self.header_frame = ttk.Frame(self.root)
        self.header_frame.pack(side="top", fill="x", padx=10, pady=(10,0), anchor="n")
        
        action_buttons_frame = ttk.Frame(self.header_frame)
        action_buttons_frame.pack(side="right", padx=0, pady=0)
        
        # Settings Dropdown
        self.settings_menubutton = ttk.Menubutton(action_buttons_frame, text="Settings", width=12)
        default_font = tkfont.nametofont("TkMenuFont")
        self.menu_heading_font = tkfont.Font(family=default_font['family'], size=default_font['size'], weight="bold")
        self.settings_menu = tk.Menu(self.settings_menubutton, tearoff=0, disabledforeground="black")
        self.settings_menubutton["menu"] = self.settings_menu
        self.settings_menubutton.pack(side="right", padx=(0, 0), pady=0) 

        # Temperature Label
        if self.is_full_mode: temp_label_container = ttk.Frame(self.header_frame, width=120, height=26)
        else: temp_label_container = ttk.Frame(self.header_frame, width=200, height=26)
            
        temp_label_container.pack_propagate(False); temp_label_container.pack(side="right", padx=(0, 10), pady=0)
        self.temperature_label = ttk.Label(temp_label_container, textvariable=self.temperature_text, relief="sunken", padding=(5, 2), anchor=tk.W)
        self.temperature_label.pack(fill='both', expand=True)
        
        # --- 2. MAIN CONTENT CONTAINER (PACKED) ---
        self.tap_container_frame = ttk.Frame(self.root)
        self.tap_container_frame.pack(side="top", fill="both", expand=True, padx=10, pady=(20, 0))
        
        # --- 3. MAIN COLUMN FRAME (GRID) ---
        self.main_columns_frame = ttk.Frame(self.tap_container_frame)
        self.main_columns_frame.pack(fill="both", expand=True)
        
        cols_per_row = 5
        
        # --- DYNAMIC WIDGET SIZING ---
        if self.is_full_mode:
            grid_width = 380
            combo_width = 16
            keg_combo_width = 12
            val_width_large = 15 # For Flow Rate
            val_width_small = 5  # For Volume/Pours
        else:
            grid_width = 156
            combo_width = 10
            keg_combo_width = 8
            val_width_large = 6  # Fits "0.00" or "10.00"
            # FIXED: Increased from 4 to 6 to fit "19.00" without clipping
            val_width_small = 6  
            
        for col_idx in range(cols_per_row): 
            self.main_columns_frame.grid_columnconfigure(col_idx, weight=0, minsize=grid_width)
            
        self.main_columns_frame.grid_rowconfigure(0, weight=1) 
        self.main_columns_frame.grid_rowconfigure(1, weight=1)

        # --- TAP COLUMN CREATION LOOP ---
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
            
            # Apply conditional width
            beverage_dropdown = ttk.Combobox(name_frame, textvariable=self.sensor_beverage_selection_vars[i], state="readonly", width=combo_width) 
            beverage_dropdown.pack(side="left", fill="x", expand=True); 
            beverage_dropdown.bind("<<ComboboxSelected>>", lambda event, idx=i: self._handle_beverage_selection_change(idx))
            self.sensor_beverage_dropdowns[i] = beverage_dropdown

            # 2. Beverage Metadata Display
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
            
            # --- LITE MODE METADATA DISPLAY ---
            else: 
                metadata_line_frame = ttk.Frame(column_frame)
                metadata_line_frame.pack(anchor="w", pady=(2, 0), fill="x")

                ttk.Label(metadata_line_frame, text="ABV:", style='Metadata.Bold.TLabel').pack(side="left", padx=(0, 5))
                ttk.Label(metadata_line_frame, textvariable=self.beverage_metadata_texts[i]['abv']).pack(side="left", anchor="w")

                ttk.Label(metadata_line_frame, textvariable=self.beverage_metadata_texts[i]['ibu']).pack(side="right", anchor="e")
                ttk.Label(metadata_line_frame, text="IBU:", style='Metadata.Bold.TLabel').pack(side="right", padx=(5, 2))
            
            # 3. Progress Bar
            pb = ttk.Progressbar(column_frame, orient="horizontal", mode="determinate", maximum=100, style="default.Horizontal.TProgressbar")
            pb.pack(pady=(10,5), fill='x', expand=False); self.sensor_progressbars[i] = pb
            
            # 4. Measurements
            lidar_frame = ttk.Frame(column_frame); lidar_frame.pack(anchor="w", fill="x", pady=1)
            ttk.Label(lidar_frame, textvariable=self.flow_rate_label_texts[i]).pack(side="left", padx=(0, 2))
            ttk.Label(lidar_frame, textvariable=self.flow_rate_value_texts[i], width=val_width_large, anchor="w").pack(side="left", padx=(0,0)) 
            
            vol1_frame = ttk.Frame(column_frame); vol1_frame.pack(anchor="w", fill="x", pady=1)
            ttk.Label(vol1_frame, textvariable=self.volume1_label_texts[i]).pack(side="left", padx=(0, 2))
            ttk.Label(vol1_frame, textvariable=self.volume1_value_texts[i], width=val_width_small, anchor="w").pack(side="left", padx=(0,0))
            
            vol2_frame = ttk.Frame(column_frame); vol2_frame.pack(anchor="w", fill="x", pady=1)
            ttk.Label(vol2_frame, textvariable=self.volume2_label_texts[i]).pack(side="left", padx=(0, 2))
            ttk.Label(vol2_frame, textvariable=self.volume2_value_texts[i], width=val_width_small, anchor="w").pack(side="left", padx=(0,0))
            
            # 5. Keg Dropdown
            dropdowns_frame = ttk.Frame(column_frame); dropdowns_frame.pack(anchor="w", fill="x", pady=(10, 5)) 
            ttk.Label(dropdowns_frame, text="Keg:").pack(side="left", padx=(0, 5))

            # Apply conditional width
            keg_dropdown = ttk.Combobox(dropdowns_frame, textvariable=self.sensor_keg_selection_vars[i], state="readonly", width=keg_combo_width)
            if self.is_full_mode:
                keg_dropdown.pack(side="left", fill="x", expand=True, padx=(0, 5)) 
            else:
                keg_dropdown.pack(fill="x", expand=True)

            keg_dropdown.bind("<<ComboboxSelected>>", lambda event, idx=i: self._handle_keg_selection_change(idx))
            self.sensor_keg_dropdowns[i] = keg_dropdown
            
        # --- 4. Bottom Status Bar (PACKED) ---
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
                elif task == "update_cal_data": self._update_single_cal_data(*args)
                self.ui_update_queue.task_done()
        except queue.Empty: pass
        finally:
            if self.root.winfo_exists(): self.root.after(100, self._poll_ui_update_queue)     

    def update_temperature_display(self, temp_value, unit):
        self.ui_update_queue.put(("update_temp_display", (temp_value, unit)))

    def _do_update_temperature_display(self, temp_value, unit):
        if not self.root.winfo_exists(): return
        is_valid_temp = isinstance(temp_value, (int, float)) and temp_value is not None
        if is_valid_temp:
            current_display_unit = self.settings_manager.get_display_units()
            unit_char = unit
            if current_display_unit == "imperial":
                unit_char = "F"
                if unit == "C": temp_value = (temp_value * 9/5) + 32
            else:
                unit_char = "C"
                if unit == "F": temp_value = (temp_value - 32) * (5/9)
            self.temperature_text.set(f"Temp: {temp_value:.1f} {unit_char}")
        else:
            current_display_unit = self.settings_manager.get_display_units()
            unit_char = "F" if current_display_unit == "imperial" else "C"
            self.temperature_text.set(f"Temp: --.- {unit_char}")

    def update_sensor_data_display(self, sensor_index, flow_rate_lpm, remaining_liters_float, status_string):
        self.ui_update_queue.put(("update_sensor_data", (sensor_index, flow_rate_lpm, remaining_liters_float, status_string)))

    def _do_update_sensor_data_display(self, sensor_index, flow_rate_lpm, remaining_liters_float, status_string):
        if not self.root.winfo_exists() or not (0 <= sensor_index < self.num_sensors): return
        
        if status_string == "Hardware Fault" or status_string == "Error" or status_string == "Missing" or status_string == "Sensor Unplugged":
            # Use short label if compact
            lbl_flow = "Flow rate L/min:" if self.is_full_mode else "Flow:"
            self.flow_rate_label_texts[sensor_index].set(lbl_flow) 
            
            self.flow_rate_value_texts[sensor_index].set("-- (Err)") # Shortened Error
            self.volume1_value_texts[sensor_index].set("--"); self.volume2_value_texts[sensor_index].set("--")
            self.last_known_remaining_liters[sensor_index] = None
            self.sensor_is_actively_connected[sensor_index] = False
            self._do_update_sensor_stability_display(sensor_index, "Acquiring data...")
            return
        
        self.sensor_is_actively_connected[sensor_index] = True
        
        # --- FIXED: Shortened Flow Label for Compact Mode ---
        lbl_flow = "Flow rate L/min:" if self.is_full_mode else "Flow:"
        self.flow_rate_label_texts[sensor_index].set(lbl_flow)
        # ----------------------------------------------------
        
        flow_rate_display = f"{flow_rate_lpm:.2f}" if flow_rate_lpm is not None else "0.00"
        self.flow_rate_value_texts[sensor_index].set(flow_rate_display)
        
        if remaining_liters_float is not None: self.last_known_remaining_liters[sensor_index] = remaining_liters_float
        
        display_units = self.settings_manager.get_display_units()
        if remaining_liters_float is not None:
            pour_settings = self.settings_manager.get_pour_volume_settings()
            if display_units == "imperial":
                gallons = remaining_liters_float * LITERS_TO_GALLONS
                pour_oz = pour_settings['imperial_pour_oz']
                liters_per_pour = pour_oz * OZ_TO_LITERS
                servings_remaining = math.floor(remaining_liters_float / liters_per_pour) if liters_per_pour > 0 else 0
                self.volume1_value_texts[sensor_index].set(f"{gallons:.2f}")
                self.volume2_value_texts[sensor_index].set(f"{int(servings_remaining)}")
            else:
                liters = remaining_liters_float
                pour_ml = pour_settings['metric_pour_ml']
                liters_per_pour = pour_ml / 1000.0
                servings_remaining = math.floor(liters / liters_per_pour) if liters_per_pour > 0 else 0
                self.volume1_value_texts[sensor_index].set(f"{liters:.2f}")
                self.volume2_value_texts[sensor_index].set(f"{int(servings_remaining)}")
        else:
            self.flow_rate_value_texts[sensor_index].set("Init...")
            self.volume1_value_texts[sensor_index].set("Init..."); self.volume2_value_texts[sensor_index].set("Init...")

    def update_sensor_stability_display(self, sensor_index, status_text_from_logic):
        self.ui_update_queue.put(("update_sensor_stability", (sensor_index, status_text_from_logic)))

    def _do_update_sensor_stability_display(self, sensor_index, status_text_from_logic):
        if not self.root.winfo_exists() or not (0 <= sensor_index < self.num_sensors): return
        pb = self.sensor_progressbars[sensor_index]
        if not pb: return

        if self.sensor_logic and self.sensor_logic.is_paused and status_text_from_logic != "Paused": return

        current_percentage = 0
        liters_val = self.last_known_remaining_liters[sensor_index]
        if liters_val is not None:
            keg_id = self.settings_manager.get_sensor_keg_assignments()[sensor_index]
            keg_params = self.settings_manager.get_keg_by_id(keg_id)
            if keg_params and keg_params.get('id') != UNASSIGNED_KEG_ID:
                total_keg_volume_liters_for_100_percent = float(keg_params.get('maximum_full_volume_liters', 0))
                if total_keg_volume_liters_for_100_percent > 0:
                    percentage_calc = (liters_val / total_keg_volume_liters_for_100_percent) * 100
                    current_percentage = max(0, min(percentage_calc, 100))

        current_style = pb.cget('style')
        new_style = current_style
        new_value = pb['value']

        if status_text_from_logic == "Data stable":
            new_style = f"Tap{sensor_index}.Horizontal.TProgressbar"
            new_value = current_percentage
            self.was_stable_before_pause[sensor_index] = True
        elif status_text_from_logic == "Acquiring data..." or status_text_from_logic == "Hardware Fault" or status_text_from_logic == "Error":
             new_style = "neutral.Horizontal.TProgressbar" 
             new_value = 100
             self.was_stable_before_pause[sensor_index] = False
        elif status_text_from_logic == "Paused":
            new_style = "neutral.Horizontal.TProgressbar" 
            if self.was_stable_before_pause[sensor_index]: new_value = current_percentage
            else: new_value = 100
            self.flow_rate_value_texts[sensor_index].set("Paused")

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
        self.ui_update_queue.put(("update_header_status", (animate, base_text, is_animating_flag_val_unused)))
        
    def _do_update_header_status(self, animate, base_text, is_animating_flag_val_unused):
        pass
        
    def _animate_header_text(self):
        pass

    def update_notification_status_display(self, message):
        self.ui_update_queue.put(("update_notification_status", (message,)))
    def _do_update_notification_status_display(self, message):
        if hasattr(self, 'notification_status_text') and self.root.winfo_exists():
            current_time = time.strftime("%H:%M:%S") # Removed date for cleaner display
            self.notification_status_text.set(f"[{current_time}] {message}")

    def _populate_keg_dropdowns(self):
        all_keg_defs = self.settings_manager.get_keg_definitions()
        sorted_keg_defs = sorted(all_keg_defs, key=lambda k: k.get('title', '').lower())
        display_kegs = sorted_keg_defs[:self.num_keg_definitions]
        
        unassigned_id = UNASSIGNED_KEG_ID
        unassigned_title = "Offline" 
        special_action = "★ Keg Kicked - Calibrate"
        
        keg_titles = [special_action, unassigned_title] + [keg.get('title', f"Keg {i+1:02}") for i, keg in enumerate(display_kegs)]
        keg_id_to_title = {unassigned_id: unassigned_title}
        keg_id_to_title.update({keg['id']: keg['title'] for keg in display_kegs})
        
        current_assignments_ids = self.settings_manager.get_sensor_keg_assignments()
        
        for i in range(self.num_sensors):
            assigned_id = current_assignments_ids[i]
            assigned_title = keg_id_to_title.get(assigned_id)
            
            if self.sensor_keg_dropdowns[i]:
                self.sensor_keg_dropdowns[i]['values'] = keg_titles
                if assigned_title:
                    self.sensor_keg_selection_vars[i].set(assigned_title)
                else:
                    self.sensor_keg_selection_vars[i].set(unassigned_title)
                    self.settings_manager.save_sensor_keg_assignment(i, unassigned_id)
                    
    def _populate_beverage_dropdowns(self):
        beverage_library = self.settings_manager.get_beverage_library()
        beverage_list = beverage_library.get('beverages', [])
        beverage_names = [b.get('name', 'Untitled Beverage') for b in beverage_list]
        beverage_names.insert(0, "Offline")
        
        current_assignments = self.settings_manager.get_sensor_beverage_assignments()
        id_to_name = {b.get('id'): b.get('name', 'Untitled') for b in beverage_list}
        id_to_name[UNASSIGNED_BEVERAGE_ID] = "Offline"

        for i in range(self.num_sensors):
            if self.sensor_beverage_dropdowns[i]: 
                self.sensor_beverage_dropdowns[i]['values'] = beverage_names
            
            assigned_id = current_assignments[i] if i < len(current_assignments) else None
            assigned_name = id_to_name.get(assigned_id)
            
            if assigned_name:
                self.sensor_beverage_selection_vars[i].set(assigned_name)
            elif beverage_names:
                self.sensor_beverage_selection_vars[i].set(beverage_names[0])
                self.settings_manager.save_sensor_beverage_assignment(i, UNASSIGNED_BEVERAGE_ID)
            else:
                self.sensor_beverage_selection_vars[i].set("No Beverages")

    def _handle_beverage_selection_change(self, sensor_idx):
        selected_beverage_name = self.sensor_beverage_selection_vars[sensor_idx].get()
        if selected_beverage_name == "Offline":
            selected_id = UNASSIGNED_BEVERAGE_ID
            self.settings_manager.save_sensor_beverage_assignment(sensor_idx, selected_id)
            self._refresh_beverage_metadata()
            return

        beverage_library = self.settings_manager.get_beverage_library()
        beverage_list = beverage_library.get('beverages', [])
        selected_beverage = next((b for b in beverage_list if b.get('name') == selected_beverage_name), None)
        
        if selected_beverage:
            selected_id = selected_beverage.get('id')
            self.settings_manager.save_sensor_beverage_assignment(sensor_idx, selected_id)
            self._refresh_beverage_metadata()
        else:
            print(f"Error: Selected beverage '{selected_beverage_name}' not found.")

    def _refresh_beverage_metadata(self):
        self._update_tap_progress_bar_colors()
        beverage_library = self.settings_manager.get_beverage_library()
        beverage_list = beverage_library.get('beverages', [])
        assignments = self.settings_manager.get_sensor_beverage_assignments()
        id_to_beverage = {b.get('id'): b for b in beverage_list if 'id' in b}
        
        for i in range(self.num_sensors):
            if i < self.settings_manager.get_displayed_taps():
                assigned_id = assignments[i] if i < len(assignments) else None
                if assigned_id == UNASSIGNED_BEVERAGE_ID:
                    self.beverage_metadata_texts[i]['bjcp'].set('Offline')
                    self.beverage_metadata_texts[i]['abv'].set('--')
                    self.beverage_metadata_texts[i]['ibu'].set('--')
                    self.beverage_metadata_texts[i]['description'].set('')
                    continue

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
        
        if selected_keg_title.startswith("★"):
            current_assignments_ids = self.settings_manager.get_sensor_keg_assignments()
            assigned_id = current_assignments_ids[sensor_idx]
            keg = self.settings_manager.get_keg_by_id(assigned_id)
            if keg and keg.get('id') == UNASSIGNED_KEG_ID: previous_title = "Offline"
            elif keg: previous_title = keg.get('title', 'Unknown')
            else: previous_title = "Offline"
            self.sensor_keg_selection_vars[sensor_idx].set(previous_title)
            
            confirm = messagebox.askyesno(
                "Confirm Keg Kicked",
                f"Has the keg on Tap {sensor_idx+1} completely run dry?\n\nThis function is for calibrating the tap using a known full keg volume against the pulses recorded until empty.\n\nClick YES only if the keg is empty.",
                parent=self.root
            )
            if not confirm: return
            if hasattr(self, '_open_flow_calibration_popup'):
                self._open_flow_calibration_popup(initial_tab_index=1, initial_tap_index=sensor_idx, initial_keg_title=previous_title)
            return
        
        if selected_keg_title == "Offline":
            selected_keg_id = UNASSIGNED_KEG_ID
        else:
            all_keg_defs = self.settings_manager.get_keg_definitions()
            selected_keg = next((keg for keg in all_keg_defs if keg.get('title') == selected_keg_title), None)
            if not selected_keg: return 
            selected_keg_id = selected_keg['id']
            
        self.settings_manager.save_sensor_keg_assignment(sensor_idx, selected_keg_id)
        self._refresh_ui_for_settings_or_resume()
        if self.sensor_logic: 
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
        # 1. Update visibility (Grid placement)
        self._update_sensor_column_visibility()
        
        # 2. Force idle tasks to process so the grid is calculated BEFORE we resize window
        self.root.update_idletasks()
        
        # 3. Apply Dynamic Window Sizing (safely)
        self._apply_window_geometry(set_position=False)
        
        # 4. Standard Refresh Logic
        self._refresh_beverage_metadata()
        self._populate_beverage_dropdowns()
        
        display_units = self.settings_manager.get_display_units()
        displayed_taps_count = self.settings_manager.get_displayed_taps()
        pour_settings = self.settings_manager.get_pour_volume_settings()
        pour_ml = pour_settings['metric_pour_ml']
        pour_oz = pour_settings['imperial_pour_oz']

        for i in range(self.num_sensors):
            if i < displayed_taps_count:
                # --- FIXED: Shortened labels for Compact Mode ---
                if self.is_full_mode:
                    lbl_vol = "Gal remaining:" if display_units == "imperial" else "Liters remaining:"
                    lbl_pours = f"{pour_oz} oz pours:" if display_units == "imperial" else f"{pour_ml} ml pours:"
                else:
                    lbl_vol = "Vol:"
                    lbl_pours = "Pours:"
                
                self.volume1_label_texts[i].set(lbl_vol)
                self.volume2_label_texts[i].set(lbl_pours)
                # ------------------------------------------------
                
                effective_stability_status = "Acquiring data..."
                if self.sensor_logic and self.sensor_logic.is_paused: effective_stability_status = "Paused"
                elif self.last_known_remaining_liters[i] is None and self.sensor_is_actively_connected[i]: effective_stability_status = "Acquiring data..."
                self._do_update_sensor_stability_display(i, effective_stability_status)
                
                if self.last_known_remaining_liters[i] is not None and not (self.sensor_logic and self.sensor_logic.is_paused):
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
        
    def _open_restart_confirmation_dialog(self):
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

    def _update_single_cal_data(self, flow_rate, dispensed_liters):
        """
        Updates the UI for the single tap calibration popup with live data.
        This is called via the UI queue from SensorLogic.
        """
        if not hasattr(self, '_single_cal_popup_window') or not self._single_cal_popup_window or not self._single_cal_popup_window.winfo_exists():
            return

        self.single_cal_measured_flow_var.set(f"{flow_rate:.2f} L/min")
        
        # Update the "Measured Pour with Current Calibration" field
        # Convert liters to user's selected unit
        unit_label = self.single_cal_unit_label.get()
        if unit_label == "ml":
            display_val = dispensed_liters * 1000.0
        elif unit_label == "oz":
            display_val = dispensed_liters / OZ_TO_LITERS
        else:
            display_val = dispensed_liters
            
        self.single_cal_measured_pour_var.set(f"{display_val:.2f}")

    def run(self):
        self.root.mainloop()
