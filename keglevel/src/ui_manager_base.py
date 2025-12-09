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
import re
from datetime import datetime # Added for dynamic versioning

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

# --- NEW: Dynamic Application Revision Logic ---
def _generate_dynamic_revision():
    """
    Scans the src directory for the most recently modified .py file.
    Returns a timestamp string like: "20231027.1430"
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    latest_mtime = 0
    
    # 1. Find latest timestamp from any .py file in src
    try:
        for root, dirs, files in os.walk(base_dir):
            for file in files:
                if file.endswith(".py"):
                    full_path = os.path.join(root, file)
                    try:
                        mtime = os.path.getmtime(full_path)
                        if mtime > latest_mtime:
                            latest_mtime = mtime
                    except OSError:
                        pass
    except Exception as e:
        print(f"Version Check Error: {e}")

    if latest_mtime > 0:
        # Return ONLY the timestamp. 
        # The 'About' popup adds the "(Commit: xyz)" part automatically.
        return datetime.fromtimestamp(latest_mtime).strftime("%Y%m%d.%H%M")
    else:
        return "Dev.Build"

APP_REVISION = _generate_dynamic_revision()
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
        self.num_keg_definitions = 6 
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        
        self.app_version_string = app_version_string

        # --- UPDATED MODE INITIALIZATION ---
        # Default fallback is 'basic'
        self.ui_mode = self.settings_manager.get_system_settings().get('ui_mode', 'basic') 
        self.is_full_mode = (self.ui_mode == 'detailed')
        # -----------------------------------
        
        self.is_rebuilding_ui = False
        self.ui_update_queue = queue.Queue()
        
        self._last_applied_geometry = None
        self._current_cols = 0 

        self.root.title("KegLevel Monitor")
        
        self._setup_main_window_properties()
            
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing_ui) 
        
        # --- Num Lock Logic ---
        self.original_numlock_state = None
        if IS_RASPBERRY_PI_MODE:
            self.root.bind("<FocusIn>", self._enforce_numlock, add="+")
            self.root.bind_class("Toplevel", "<FocusIn>", self._enforce_numlock, add="+")
            if self.settings_manager.get_force_numlock():
                try:
                    result = subprocess.run(['numlockx', 'status'], capture_output=True, text=True)
                    if "on" in result.stdout: self.original_numlock_state = "on"
                    elif "off" in result.stdout: self.original_numlock_state = "off"
                    subprocess.run(['numlockx', 'on'])
                except Exception: pass

        # --- Primary UI Variables ---
        self.sensor_name_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        
        self.flow_rate_label_widgets = [] 
        self.flow_rate_value_labels = []  
        self.last_pour_label_widgets = [] 
        self.last_pour_value_labels = [] 
        
        self.flow_rate_label_texts = [tk.StringVar(value="Flow rate:") for _ in range(self.num_sensors)] 
        self.flow_rate_value_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        
        # --- Last Pour Variables ---
        self.last_pour_label_texts = [tk.StringVar(value="Last Pour:") for _ in range(self.num_sensors)]
        self.last_pour_value_texts = [tk.StringVar() for _ in range(self.num_sensors)]
        
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

        # --- Metadata Variables ---
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
        self.last_known_remaining_liters = [None] * self.num_sensors
        
        self.last_known_pour_volumes = [0.0] * self.num_sensors
        
        self.workflow_app = None 
        
        self.sensor_column_frames = [None] * self.num_sensors
        
        # Dictionary to store references to metadata frames for dynamic toggling
        # Structure: { tap_index: { 'lite': frame_widget, 'full': frame_widget } }
        self.metadata_frame_refs = {} 
        
        self.settings_menubutton = None 
        self.temperature_label = None
        self.notification_status_label = None

        self._create_widgets()
        self._load_initial_ui_settings()
        self._poll_ui_update_queue()

    def _setup_main_window_properties(self):
        """Configures the main window to be resizable and safe for different screens."""
        
        # 1. Set Minimum Size
        # 800x480 is the standard 7" RPi Touchscreen resolution
        self.root.minsize(800, 480)
        
        # 2. Restore Saved Geometry OR Default
        saved_geometry = self.settings_manager.get_window_geometry()
        
        if saved_geometry:
            try:
                self.root.geometry(saved_geometry)
            except Exception:
                self.root.geometry("800x600")
        else:
            # Default safe start size
            self.root.geometry("800x600")
            
        # 3. Disable Resizing Initially
        # This is part of the fix to force the WM to acknowledge the change later
        self.root.resizable(False, False)
        
        # 4. CRITICAL FIX: The "Two-Step Jiggle"
        # We move the window 1px, WAIT 100ms, then move it back.
        # This delay ensures the Window Manager processes both events distincty.
        def jiggle_window(event):
            if event.widget != self.root: return
            self.root.unbind("<Map>")
            
            # Enable resizing now that window is visible
            self.root.resizable(True, True)
            
            def _step_1_move():
                try:
                    # Use winfo_x/y for accurate content coordinates (avoids drift)
                    x = self.root.winfo_x()
                    y = self.root.winfo_y()
                    w = self.root.winfo_width()
                    h = self.root.winfo_height()
                    
                    # Store original position for Step 2
                    self._jiggle_restore_x = x
                    self._jiggle_restore_y = y
                    self._jiggle_restore_w = w
                    self._jiggle_restore_h = h
                    
                    # Move 1px right
                    self.root.geometry(f"{w}x{h}+{x+1}+{y}")
                    
                    # Schedule Step 2 (Restore) after 100ms
                    self.root.after(100, _step_2_restore)
                except Exception as e:
                    print(f"UI Warning: Jiggle Step 1 failed: {e}")

            def _step_2_restore():
                try:
                    # Restore original position
                    x = self._jiggle_restore_x
                    y = self._jiggle_restore_y
                    w = self._jiggle_restore_w
                    h = self._jiggle_restore_h
                    self.root.geometry(f"{w}x{h}+{x}+{y}")
                except Exception as e:
                    print(f"UI Warning: Jiggle Step 2 failed: {e}")

            # Run Step 1 500ms after map
            self.root.after(500, _step_1_move)
            
        self.root.bind("<Map>", jiggle_window)

    def _enforce_numlock(self, event=None):
        if not IS_RASPBERRY_PI_MODE: return
        if not self.settings_manager.get_force_numlock(): return
        if event and isinstance(event.widget, (tk.Tk, tk.Toplevel)):
             try: subprocess.Popen(['numlockx', 'on'])
             except Exception: pass

    def _srm_to_hex(self, srm):
        if srm is None: return None
        srm = max(0, min(40, int(srm)))
        srm_colors = {
            0: "#FFFFFF", 1: "#FFE699", 2: "#FFD878", 3: "#FFCA5A", 4: "#FFBF42", 5: "#FBB123",
            6: "#F8A600", 7: "#F39C00", 8: "#EA8F00", 9: "#E58500", 10: "#DE7C00", 11: "#D77200",
            12: "#CF6900", 13: "#CB6200", 14: "#C35900", 15: "#BB5100", 16: "#B54C00", 17: "#B04500",
            18: "#A63E00", 19: "#A13700", 20: "#9B3200", 21: "#962D00", 22: "#8F2900", 23: "#882300",
            24: "#821E00", 25: "#7B1A00", 26: "#771900", 27: "#701400", 28: "#6A0E00", 29: "#660D00",
            30: "#5E0B00", 31: "#5A0A02", 32: "#600903", 33: "#520907", 34: "#4C0505", 35: "#470606",
            36: "#440607", 37: "#3F0708", 38: "#3B0607", 39: "#3A070B", 40: "#36080A"
        }
        return srm_colors.get(srm, "#E5A128")

    def _define_progressbar_styles(self):
        if not self.progressbar_styles_defined:
            s = ttk.Style(self.root)
            try: s.theme_use('default')
            except tk.TclError: pass
            common_opts = {'troughcolor': '#E0E0E0', 'borderwidth': 1, 'relief': 'sunken'}
            s.configure("green.Horizontal.TProgressbar", background='green', **common_opts)
            s.configure("neutral.Horizontal.TProgressbar", background='#C0C0C0', **common_opts)
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
        
        self.settings_menubutton = ttk.Menubutton(action_buttons_frame, text="Settings", width=12)
        default_font = tkfont.nametofont("TkMenuFont")
        self.menu_heading_font = tkfont.Font(family=default_font['family'], size=default_font['size'], weight="bold")
        self.settings_menu = tk.Menu(self.settings_menubutton, tearoff=0, disabledforeground="black")
        self.settings_menubutton["menu"] = self.settings_menu
        self.settings_menubutton.pack(side="right", padx=(0, 0), pady=0) 

        # Temperature Display
        temp_label_container = ttk.Frame(self.header_frame, width=120, height=26)
        temp_label_container.pack_propagate(False)
        temp_label_container.pack(side="right", padx=(0, 10), pady=0)
        self.temperature_label = ttk.Label(temp_label_container, textvariable=self.temperature_text, relief="sunken", padding=(5, 2), anchor=tk.W)
        self.temperature_label.pack(fill='both', expand=True)
        
        # --- 2. MAIN CONTENT CONTAINER (VERTICAL SCROLLABLE CANVAS) ---
        # Changed to Vertical scrollbar to support wrapping rows
        self.tap_container_frame = ttk.Frame(self.root)
        self.tap_container_frame.pack(side="top", fill="both", expand=True, padx=10, pady=(20, 0))
        
        # Vertical Scrollbar (Right Side)
        self.v_scrollbar = ttk.Scrollbar(self.tap_container_frame, orient="vertical")
        self.v_scrollbar.pack(side="right", fill="y")
        
        # Canvas
        self.tap_canvas = tk.Canvas(self.tap_container_frame, yscrollcommand=self.v_scrollbar.set, highlightthickness=0)
        self.tap_canvas.pack(side="left", fill="both", expand=True)
        
        self.v_scrollbar.config(command=self.tap_canvas.yview)
        
        # Internal Frame for Taps (Grid Layout)
        self.main_columns_frame = ttk.Frame(self.tap_canvas)
        
        # Create Window in Canvas
        self.canvas_window_id = self.tap_canvas.create_window((0, 0), window=self.main_columns_frame, anchor="nw")
        
        # --- DYNAMIC RESIZING EVENTS ---
        def on_frame_configure(event):
            """Reset the scroll region to encompass the inner frame"""
            self.tap_canvas.configure(scrollregion=self.tap_canvas.bbox("all"))

        def on_canvas_configure(event):
            """
            When the canvas width changes (user resize), resize the inner frame 
            to match and trigger a reflow of the grid.
            """
            if self.tap_canvas.winfo_width() != self.main_columns_frame.winfo_reqwidth():
                self.tap_canvas.itemconfig(self.canvas_window_id, width=event.width)
                
            # Trigger Reflow Logic based on new width
            self._reflow_layout(event.width)

        self.main_columns_frame.bind("<Configure>", on_frame_configure)
        self.tap_canvas.bind("<Configure>", on_canvas_configure)

        # --- TAP COLUMN CREATION LOOP ---
        WRAPLENGTH_TAP_COLUMN = 250 
        
        for i in range(self.num_sensors):
            column_frame = ttk.Frame(self.main_columns_frame, padding=(3,3), relief="groove")
            self.sensor_column_frames[i] = column_frame
            
            # Note: Grid placement now happens in _reflow_layout, not here.
            
            # 1. Header: "Tap X" + Dropdown
            header_subframe = ttk.Frame(column_frame)
            header_subframe.pack(fill="x", pady=(0, 2))
            
            ttk.Label(header_subframe, text=f"Tap {i + 1}:", style='Tap.Bold.TLabel').pack(side="left", padx=(0, 5))
            
            keg_dropdown = ttk.Combobox(header_subframe, textvariable=self.sensor_keg_selection_vars[i], state="readonly")
            keg_dropdown.pack(side="left", fill="x", expand=True)
            keg_dropdown.bind("<<ComboboxSelected>>", lambda event, idx=i: self._handle_keg_selection_change(idx))
            keg_dropdown.bind("<Button-1>", self._on_combobox_click)
            self.sensor_keg_dropdowns[i] = keg_dropdown

            # --- DYNAMIC METADATA SECTIONS ---
            self.metadata_frame_refs[i] = {}

            # A. Lite Mode Metadata (Single Line)
            lite_meta_frame = ttk.Frame(column_frame)
            
            ttk.Label(lite_meta_frame, text="ABV:", style='Metadata.Bold.TLabel').pack(side="left", padx=(0, 2))
            ttk.Label(lite_meta_frame, textvariable=self.beverage_metadata_texts[i]['abv']).pack(side="left", anchor="w")
            
            ttk.Label(lite_meta_frame, textvariable=self.beverage_metadata_texts[i]['ibu']).pack(side="right", anchor="e")
            ttk.Label(lite_meta_frame, text="IBU:", style='Metadata.Bold.TLabel').pack(side="right", padx=(5, 2))
            
            self.metadata_frame_refs[i]['lite'] = lite_meta_frame

            # B. Full Mode Metadata (Gray Box)
            # --- MODIFICATION: Reduced Fixed Height to 220 ---
            METADATA_HEIGHT = 220
            # pack_propagate(False) ensures this frame stays exactly 220px tall
            full_meta_container = ttk.Frame(column_frame, height=METADATA_HEIGHT, style='LightGray.TFrame') 
            full_meta_container.pack_propagate(False) 
            
            full_meta_inner = ttk.Frame(full_meta_container, padding=(5, 5), style='LightGray.TFrame') 
            full_meta_inner.pack(fill="both", expand=True) 
            
            # Row 1: BJCP, ABV, IBU
            fm_row1 = ttk.Frame(full_meta_inner, style='LightGray.TFrame')
            fm_row1.pack(anchor="w", fill="x")
            
            ttk.Label(fm_row1, text="BJCP:", style='Metadata.Bold.TLabel', background='#F0F0F0').pack(side="left", padx=(0, 2))
            ttk.Label(fm_row1, textvariable=self.beverage_metadata_texts[i]['bjcp'], background='#F0F0F0').pack(side="left", padx=(0, 10), anchor='w')

            # Right aligned ABV/IBU
            fm_ibu = ttk.Frame(fm_row1, style='LightGray.TFrame'); fm_ibu.pack(side="right", anchor='e')
            ttk.Label(fm_ibu, textvariable=self.beverage_metadata_texts[i]['ibu'], anchor='e', background='#F0F0F0').pack(side="right")
            ttk.Label(fm_ibu, text="IBU:", style='Metadata.Bold.TLabel', background='#F0F0F0').pack(side="right", padx=(0, 2))
            
            fm_abv = ttk.Frame(fm_row1, style='LightGray.TFrame'); fm_abv.pack(side="right", anchor='e', padx=(10, 10)) 
            ttk.Label(fm_abv, textvariable=self.beverage_metadata_texts[i]['abv'], anchor='e', background='#F0F0F0').pack(side="right")
            ttk.Label(fm_abv, text="ABV:", style='Metadata.Bold.TLabel', background='#F0F0F0').pack(side="right", padx=(0, 2))

            # Row 2: Description
            # Added padding to keep text away from edges
            description_label = ttk.Label(full_meta_inner, textvariable=self.beverage_metadata_texts[i]['description'], 
                                          anchor='nw', font=('TkDefaultFont', 11, 'italic'), justify=tk.LEFT,
                                          wraplength=WRAPLENGTH_TAP_COLUMN, background='#F0F0F0', padding=(10, 5)) 
            description_label.pack(anchor="w", fill="both", expand=True, pady=(5, 5))
            
            # Use dynamic wrapping for description based on column width
            def resize_desc_wrap(event, lbl=description_label):
                # Adjust wrap length to account for padding
                lbl.config(wraplength=event.width - 25)
            full_meta_container.bind("<Configure>", resize_desc_wrap)

            self.metadata_frame_refs[i]['full'] = full_meta_container

            # 3. Progress Bar
            pb = ttk.Progressbar(column_frame, orient="horizontal", mode="determinate", maximum=100, style="default.Horizontal.TProgressbar")
            pb.pack(pady=(10,5), fill='x', expand=False)
            self.sensor_progressbars[i] = pb
            
            # 4. Measurements
            # A. Flow Rate
            lidar_frame = ttk.Frame(column_frame); lidar_frame.pack(anchor="w", fill="x", pady=1)
            lbl_title = ttk.Label(lidar_frame, textvariable=self.flow_rate_label_texts[i])
            lbl_title.pack(side="left", padx=(0, 2))
            self.flow_rate_label_widgets.append(lbl_title)
            lbl_val = ttk.Label(lidar_frame, textvariable=self.flow_rate_value_texts[i], anchor="w")
            lbl_val.pack(side="left", padx=(0,0)) 
            self.flow_rate_value_labels.append(lbl_val)
            
            # B. Last Pour
            pour_track_frame = ttk.Frame(column_frame); pour_track_frame.pack(anchor="w", fill="x", pady=1)
            lbl_pour_title = ttk.Label(pour_track_frame, textvariable=self.last_pour_label_texts[i])
            lbl_pour_title.pack(side="left", padx=(0, 2))
            self.last_pour_label_widgets.append(lbl_pour_title)
            lbl_pour_val = ttk.Label(pour_track_frame, textvariable=self.last_pour_value_texts[i], anchor="w")
            lbl_pour_val.pack(side="left", padx=(0,0))
            self.last_pour_value_labels.append(lbl_pour_val)
            
            # C. Volume Remaining
            vol1_frame = ttk.Frame(column_frame); vol1_frame.pack(anchor="w", fill="x", pady=1)
            ttk.Label(vol1_frame, textvariable=self.volume1_label_texts[i]).pack(side="left", padx=(0, 2))
            ttk.Label(vol1_frame, textvariable=self.volume1_value_texts[i], anchor="w").pack(side="left", padx=(0,0))
            
            # D. Pours Remaining
            vol2_frame = ttk.Frame(column_frame); vol2_frame.pack(anchor="w", fill="x", pady=1)
            ttk.Label(vol2_frame, textvariable=self.volume2_label_texts[i]).pack(side="left", padx=(0, 2))
            ttk.Label(vol2_frame, textvariable=self.volume2_value_texts[i], anchor="w").pack(side="left", padx=(0,0))
            
        # --- 4. Bottom Status Bar (PACKED) ---
        notification_label_container = ttk.Frame(self.root, height=26)
        notification_label_container.pack_propagate(False)
        notification_label_container.pack(side="bottom", fill="x", padx=10, pady=(5,5))
        self.notification_status_label = ttk.Label(notification_label_container, textvariable=self.notification_status_text, anchor="w", relief="sunken", padding=(5,2))
        self.notification_status_label.pack(fill='both', expand=True)

    # def _create_widgets(self):
        # s = self._define_progressbar_styles()
        # s.configure('Tap.Bold.TLabel', font=('TkDefaultFont', 10, 'bold'))
        # s.configure('Metadata.Bold.TLabel', font=('TkDefaultFont', 9, 'bold'))
        # s.configure('LightGray.TFrame', background='#F0F0F0')
        
        # # --- 1. HEADER (PACKED) ---
        # self.header_frame = ttk.Frame(self.root)
        # self.header_frame.pack(side="top", fill="x", padx=10, pady=(10,0), anchor="n")
        
        # action_buttons_frame = ttk.Frame(self.header_frame)
        # action_buttons_frame.pack(side="right", padx=0, pady=0)
        
        # self.settings_menubutton = ttk.Menubutton(action_buttons_frame, text="Settings", width=12)
        # default_font = tkfont.nametofont("TkMenuFont")
        # self.menu_heading_font = tkfont.Font(family=default_font['family'], size=default_font['size'], weight="bold")
        # self.settings_menu = tk.Menu(self.settings_menubutton, tearoff=0, disabledforeground="black")
        # self.settings_menubutton["menu"] = self.settings_menu
        # self.settings_menubutton.pack(side="right", padx=(0, 0), pady=0) 

        # # Temperature Display
        # temp_label_container = ttk.Frame(self.header_frame, width=120, height=26)
        # temp_label_container.pack_propagate(False)
        # temp_label_container.pack(side="right", padx=(0, 10), pady=0)
        # self.temperature_label = ttk.Label(temp_label_container, textvariable=self.temperature_text, relief="sunken", padding=(5, 2), anchor=tk.W)
        # self.temperature_label.pack(fill='both', expand=True)
        
        # # --- 2. MAIN CONTENT CONTAINER (VERTICAL SCROLLABLE CANVAS) ---
        # # Changed to Vertical scrollbar to support wrapping rows
        # self.tap_container_frame = ttk.Frame(self.root)
        # self.tap_container_frame.pack(side="top", fill="both", expand=True, padx=10, pady=(20, 0))
        
        # # Vertical Scrollbar (Right Side)
        # self.v_scrollbar = ttk.Scrollbar(self.tap_container_frame, orient="vertical")
        # self.v_scrollbar.pack(side="right", fill="y")
        
        # # Canvas
        # self.tap_canvas = tk.Canvas(self.tap_container_frame, yscrollcommand=self.v_scrollbar.set, highlightthickness=0)
        # self.tap_canvas.pack(side="left", fill="both", expand=True)
        
        # self.v_scrollbar.config(command=self.tap_canvas.yview)
        
        # # Internal Frame for Taps (Grid Layout)
        # self.main_columns_frame = ttk.Frame(self.tap_canvas)
        
        # # Create Window in Canvas
        # self.canvas_window_id = self.tap_canvas.create_window((0, 0), window=self.main_columns_frame, anchor="nw")
        
        # # --- DYNAMIC RESIZING EVENTS ---
        # def on_frame_configure(event):
            # """Reset the scroll region to encompass the inner frame"""
            # self.tap_canvas.configure(scrollregion=self.tap_canvas.bbox("all"))

        # def on_canvas_configure(event):
            # """
            # When the canvas width changes (user resize), resize the inner frame 
            # to match and trigger a reflow of the grid.
            # """
            # if self.tap_canvas.winfo_width() != self.main_columns_frame.winfo_reqwidth():
                # self.tap_canvas.itemconfig(self.canvas_window_id, width=event.width)
                
            # # Trigger Reflow Logic based on new width
            # self._reflow_layout(event.width)

        # self.main_columns_frame.bind("<Configure>", on_frame_configure)
        # self.tap_canvas.bind("<Configure>", on_canvas_configure)

        # # --- TAP COLUMN CREATION LOOP ---
        # WRAPLENGTH_TAP_COLUMN = 250 
        
        # for i in range(self.num_sensors):
            # column_frame = ttk.Frame(self.main_columns_frame, padding=(3,3), relief="groove")
            # self.sensor_column_frames[i] = column_frame
            
            # # Note: Grid placement now happens in _reflow_layout, not here.
            
            # # 1. Header: "Tap X" + Dropdown
            # header_subframe = ttk.Frame(column_frame)
            # header_subframe.pack(fill="x", pady=(0, 2))
            
            # ttk.Label(header_subframe, text=f"Tap {i + 1}:", style='Tap.Bold.TLabel').pack(side="left", padx=(0, 5))
            
            # keg_dropdown = ttk.Combobox(header_subframe, textvariable=self.sensor_keg_selection_vars[i], state="readonly")
            # keg_dropdown.pack(side="left", fill="x", expand=True)
            # keg_dropdown.bind("<<ComboboxSelected>>", lambda event, idx=i: self._handle_keg_selection_change(idx))
            # keg_dropdown.bind("<Button-1>", self._on_combobox_click)
            # self.sensor_keg_dropdowns[i] = keg_dropdown

            # # --- DYNAMIC METADATA SECTIONS ---
            # self.metadata_frame_refs[i] = {}

            # # A. Lite Mode Metadata (Single Line)
            # lite_meta_frame = ttk.Frame(column_frame)
            
            # ttk.Label(lite_meta_frame, text="ABV:", style='Metadata.Bold.TLabel').pack(side="left", padx=(0, 2))
            # ttk.Label(lite_meta_frame, textvariable=self.beverage_metadata_texts[i]['abv']).pack(side="left", anchor="w")
            
            # ttk.Label(lite_meta_frame, textvariable=self.beverage_metadata_texts[i]['ibu']).pack(side="right", anchor="e")
            # ttk.Label(lite_meta_frame, text="IBU:", style='Metadata.Bold.TLabel').pack(side="right", padx=(5, 2))
            
            # self.metadata_frame_refs[i]['lite'] = lite_meta_frame

            # # B. Full Mode Metadata (Gray Box)
            # METADATA_HEIGHT = 160 
            # full_meta_container = ttk.Frame(column_frame, height=METADATA_HEIGHT, style='LightGray.TFrame') 
            # full_meta_container.pack_propagate(False) 
            
            # full_meta_inner = ttk.Frame(full_meta_container, padding=(5, 5), style='LightGray.TFrame') 
            # full_meta_inner.pack(fill="both", expand=True) 
            
            # # Row 1: BJCP, ABV, IBU
            # fm_row1 = ttk.Frame(full_meta_inner, style='LightGray.TFrame')
            # fm_row1.pack(anchor="w", fill="x")
            
            # ttk.Label(fm_row1, text="BJCP:", style='Metadata.Bold.TLabel', background='#F0F0F0').pack(side="left", padx=(0, 2))
            # ttk.Label(fm_row1, textvariable=self.beverage_metadata_texts[i]['bjcp'], background='#F0F0F0').pack(side="left", padx=(0, 10), anchor='w')

            # # Right aligned ABV/IBU
            # fm_ibu = ttk.Frame(fm_row1, style='LightGray.TFrame'); fm_ibu.pack(side="right", anchor='e')
            # ttk.Label(fm_ibu, textvariable=self.beverage_metadata_texts[i]['ibu'], anchor='e', background='#F0F0F0').pack(side="right")
            # ttk.Label(fm_ibu, text="IBU:", style='Metadata.Bold.TLabel', background='#F0F0F0').pack(side="right", padx=(0, 2))
            
            # fm_abv = ttk.Frame(fm_row1, style='LightGray.TFrame'); fm_abv.pack(side="right", anchor='e', padx=(10, 10)) 
            # ttk.Label(fm_abv, textvariable=self.beverage_metadata_texts[i]['abv'], anchor='e', background='#F0F0F0').pack(side="right")
            # ttk.Label(fm_abv, text="ABV:", style='Metadata.Bold.TLabel', background='#F0F0F0').pack(side="right", padx=(0, 2))

            # # Row 2: Description
            # description_label = ttk.Label(full_meta_inner, textvariable=self.beverage_metadata_texts[i]['description'], 
                                          # anchor='nw', font=('TkDefaultFont', 11, 'italic'), justify=tk.LEFT,
                                          # wraplength=WRAPLENGTH_TAP_COLUMN, background='#F0F0F0') 
            # description_label.pack(anchor="w", fill="both", expand=True, pady=(5, 5))
            
            # # Use dynamic wrapping for description based on column width
            # def resize_desc_wrap(event, lbl=description_label):
                # lbl.config(wraplength=event.width - 10)
            # full_meta_container.bind("<Configure>", resize_desc_wrap)

            # self.metadata_frame_refs[i]['full'] = full_meta_container

            # # 3. Progress Bar
            # pb = ttk.Progressbar(column_frame, orient="horizontal", mode="determinate", maximum=100, style="default.Horizontal.TProgressbar")
            # pb.pack(pady=(10,5), fill='x', expand=False)
            # self.sensor_progressbars[i] = pb
            
            # # 4. Measurements
            # # A. Flow Rate
            # lidar_frame = ttk.Frame(column_frame); lidar_frame.pack(anchor="w", fill="x", pady=1)
            # lbl_title = ttk.Label(lidar_frame, textvariable=self.flow_rate_label_texts[i])
            # lbl_title.pack(side="left", padx=(0, 2))
            # self.flow_rate_label_widgets.append(lbl_title)
            # lbl_val = ttk.Label(lidar_frame, textvariable=self.flow_rate_value_texts[i], anchor="w")
            # lbl_val.pack(side="left", padx=(0,0)) 
            # self.flow_rate_value_labels.append(lbl_val)
            
            # # B. Last Pour
            # pour_track_frame = ttk.Frame(column_frame); pour_track_frame.pack(anchor="w", fill="x", pady=1)
            # lbl_pour_title = ttk.Label(pour_track_frame, textvariable=self.last_pour_label_texts[i])
            # lbl_pour_title.pack(side="left", padx=(0, 2))
            # self.last_pour_label_widgets.append(lbl_pour_title)
            # lbl_pour_val = ttk.Label(pour_track_frame, textvariable=self.last_pour_value_texts[i], anchor="w")
            # lbl_pour_val.pack(side="left", padx=(0,0))
            # self.last_pour_value_labels.append(lbl_pour_val)
            
            # # C. Volume Remaining
            # vol1_frame = ttk.Frame(column_frame); vol1_frame.pack(anchor="w", fill="x", pady=1)
            # ttk.Label(vol1_frame, textvariable=self.volume1_label_texts[i]).pack(side="left", padx=(0, 2))
            # ttk.Label(vol1_frame, textvariable=self.volume1_value_texts[i], anchor="w").pack(side="left", padx=(0,0))
            
            # # D. Pours Remaining
            # vol2_frame = ttk.Frame(column_frame); vol2_frame.pack(anchor="w", fill="x", pady=1)
            # ttk.Label(vol2_frame, textvariable=self.volume2_label_texts[i]).pack(side="left", padx=(0, 2))
            # ttk.Label(vol2_frame, textvariable=self.volume2_value_texts[i], anchor="w").pack(side="left", padx=(0,0))
            
        # # --- 4. Bottom Status Bar (PACKED) ---
        # notification_label_container = ttk.Frame(self.root, height=26)
        # notification_label_container.pack_propagate(False)
        # notification_label_container.pack(side="bottom", fill="x", padx=10, pady=(5,5))
        # self.notification_status_label = ttk.Label(notification_label_container, textvariable=self.notification_status_text, anchor="w", relief="sunken", padding=(5,2))
        # self.notification_status_label.pack(fill='both', expand=True)

    def _reflow_layout(self, width, force=False):
        """
        Calculates how many columns fit within 'width' and re-grids the tap cards.
        Enforces a Minimum Width per card and Max 5 columns per row.
        """
        if width <= 1: return
        
        # INCREASED to 290 to account for text wrapping (250px) + padding.
        # This prevents cards from being gridded into a space too small for them.
        MIN_CARD_WIDTH = 290 
        MAX_COLS_PER_ROW = 5
        
        # Calculate optimal column count
        cols = math.floor(width / MIN_CARD_WIDTH)
        cols = min(cols, MAX_COLS_PER_ROW) # Cap at 5
        cols = max(cols, 1) # Min 1
        
        # Optimization: Only re-grid if the column count changed OR if forced
        if not force and cols == self._current_cols:
            return
            
        self._current_cols = cols
        
        displayed_taps = self.settings_manager.get_displayed_taps()
        
        # Clear existing weights to prevent ghost columns
        for i in range(10):
            self.main_columns_frame.grid_columnconfigure(i, weight=0)
            
        # Set weight for active columns so they stretch equally
        for i in range(cols):
            self.main_columns_frame.grid_columnconfigure(i, weight=1)
            
        # Re-grid visible items
        for i in range(displayed_taps):
            frame = self.sensor_column_frames[i]
            if frame:
                row = i // cols
                col = i % cols
                frame.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
                
        # Force update
        self.main_columns_frame.update_idletasks()
        
    def _on_combobox_click(self, event):
        """Forces the combobox list to scroll to the top when opened."""
        try:
            combo = event.widget
            combo.after(100, lambda: self._scroll_combobox_to_top(combo))
        except Exception: pass

    def _scroll_combobox_to_top(self, combo):
        try:
            popdown = combo.tk.eval(f'ttk::combobox::PopdownWindow {combo._w}')
            listbox = f"{popdown}.f.l"
            combo.tk.call(listbox, 'see', 0)
        except Exception: pass
                        
    def _load_initial_ui_settings(self):
        loaded_sensor_labels = self.settings_manager.get_sensor_labels()
        
        initial_logic_volumes = [None] * self.num_sensors
        initial_pour_volumes = [0.0] * self.num_sensors
        
        if self.sensor_logic:
            initial_logic_volumes = self.sensor_logic.last_known_remaining_liters
            initial_pour_volumes = self.sensor_logic.last_pour_volumes

        for i in range(self.num_sensors):
            self.sensor_name_texts[i].set(loaded_sensor_labels[i])
            self.flow_rate_value_texts[i].set("Init...")
            self.volume1_value_texts[i].set("Init...")
            self.volume2_value_texts[i].set("Init...")
            self.sensor_is_actively_connected[i] = False
            self.was_stable_before_pause[i] = False
            
            if i < len(initial_pour_volumes):
                self.last_known_pour_volumes[i] = initial_pour_volumes[i]
            
            logic_vol = initial_logic_volumes[i] if i < len(initial_logic_volumes) else None
            
            if logic_vol is not None:
                self.last_known_remaining_liters[i] = logic_vol
            else:
                if self.sensor_progressbars[i]:
                     self._do_update_sensor_stability_display(i, "Acquiring data...")

        self._populate_keg_dropdowns()
        self._populate_beverage_dropdowns()
        self._refresh_beverage_metadata()
        self._refresh_ui_for_settings_or_resume()
        
    def rebuild_ui(self):
        """
        Switch modes dynamically without hard restart if possible.
        """
        new_mode = self.settings_manager.get_ui_mode()
        if new_mode != self.ui_mode:
            print(f"UIManager: Switching display mode to {new_mode} dynamically.")
            self.ui_mode = new_mode
            
            # --- UPDATED CHECK ---
            self.is_full_mode = (new_mode == 'detailed')
            # ---------------------
            
            self._apply_ui_mode_visibility()
            self._refresh_ui_for_settings_or_resume()
            return

        print("UIManager: Performing hard restart...")
        if self.notification_service: self.notification_service.stop_scheduler()
        if self.sensor_logic: self.sensor_logic.stop_monitoring()
        if self.temp_logic: self.temp_logic.stop_monitoring()
        
        try:
            python = sys.executable
            os.execl(python, python, *sys.argv)
        except Exception as e:
            print(f"UIManager: Failed to restart application: {e}")
            self._on_closing_ui()
        
    def _poll_ui_update_queue(self):
        if self.is_rebuilding_ui:
            if self.root.winfo_exists(): self.root.after(100, self._poll_ui_update_queue)
            return

        max_events_per_cycle = 50 
        events_processed = 0
        
        try:
            while events_processed < max_events_per_cycle:
                try:
                    task, args = self.ui_update_queue.get_nowait()
                except queue.Empty:
                    break 

                if task == "update_sensor_data": self._do_update_sensor_data_display(*args)
                elif task == "update_sensor_stability": self._do_update_sensor_stability_display(*args)
                elif task == "update_header_status": self._do_update_header_status(*args)
                elif task == "update_notification_status": self._do_update_notification_status_display(*args)
                elif task == "update_sensor_connection": self._do_update_sensor_connection_status(*args)
                elif task == "update_temp_display": self._do_update_temperature_display(*args)
                elif task == "update_cal_data": self._update_single_cal_data(*args)
                
                self.ui_update_queue.task_done()
                events_processed += 1
        finally:
            if self.root.winfo_exists(): 
                self.root.after(50, self._poll_ui_update_queue)
                
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

    def update_sensor_data_display(self, sensor_index, flow_rate_lpm, remaining_liters_float, status_string, last_pour_vol=None):
        self.ui_update_queue.put(("update_sensor_data", (sensor_index, flow_rate_lpm, remaining_liters_float, status_string, last_pour_vol)))

    def _do_update_sensor_data_display(self, sensor_index, flow_rate_lpm, remaining_liters_float, status_string, last_pour_vol=None):
        if not self.root.winfo_exists() or not (0 <= sensor_index < self.num_sensors): return
        
        # --- Check for Unassigned Beverage (Empty Keg) ---
        assignments = self.settings_manager.get_sensor_beverage_assignments()
        is_empty_beverage = (sensor_index < len(assignments) and assignments[sensor_index] == UNASSIGNED_BEVERAGE_ID)
        
        # Override logic: If no beverage, force volume to 0 for display
        effective_remaining = remaining_liters_float
        if is_empty_beverage:
            effective_remaining = 0.0
        # -------------------------------------------------

        if status_string in ["Hardware Fault", "Error", "Missing", "Sensor Unplugged"]:
            self.flow_rate_label_texts[sensor_index].set("Flow Rate:")
            
            try: self.flow_rate_value_labels[sensor_index].config(foreground='', font=('TkDefaultFont', 9))
            except: pass
            
            self.flow_rate_value_texts[sensor_index].set("-- (Err)")
            self.volume1_value_texts[sensor_index].set("--"); self.volume2_value_texts[sensor_index].set("--")
            self.last_pour_value_texts[sensor_index].set("--") 
            
            self.last_known_remaining_liters[sensor_index] = None
            self.sensor_is_actively_connected[sensor_index] = False
            self._do_update_sensor_stability_display(sensor_index, "Acquiring data...")
            return
        
        self.sensor_is_actively_connected[sensor_index] = True
        
        if status_string == "Pouring":
            lbl_text = "Flowing:"
            pour_lbl_text = "Pouring:"
            fg_color = "green"
            try:
                bold_font = ('TkDefaultFont', 10, 'bold')
                self.flow_rate_value_labels[sensor_index].config(font=bold_font)
                self.last_pour_value_labels[sensor_index].config(font=bold_font) 
            except: pass
        else:
            # Use full descriptive label for idle state
            lbl_text = "Flow Rate:"
            pour_lbl_text = "Last Pour:"
            fg_color = "" 
            try:
                self.flow_rate_value_labels[sensor_index].config(font='')
                self.last_pour_value_labels[sensor_index].config(font='')
            except: pass

        self.flow_rate_label_texts[sensor_index].set(lbl_text)
        self.last_pour_label_texts[sensor_index].set(pour_lbl_text)
        
        try:
            self.flow_rate_value_labels[sensor_index].config(foreground=fg_color)
            self.last_pour_value_labels[sensor_index].config(foreground=fg_color)
        except: pass
        
        flow_rate_display = f"{flow_rate_lpm:.2f}" if flow_rate_lpm is not None else "0.00"
        self.flow_rate_value_texts[sensor_index].set(flow_rate_display)
        
        if last_pour_vol is not None:
            self.last_known_pour_volumes[sensor_index] = last_pour_vol
            display_units = self.settings_manager.get_display_units()
            if display_units == "imperial":
                val = last_pour_vol / OZ_TO_LITERS 
                unit = "oz"
                val_str = f"{val:.1f}"
            else:
                val = last_pour_vol * 1000.0 
                unit = "ml"
                val_str = f"{val:.0f}" 
            self.last_pour_value_texts[sensor_index].set(f"{val_str} {unit}")
        else:
            cached = self.last_known_pour_volumes[sensor_index]
            if cached > 0:
                display_units = self.settings_manager.get_display_units()
                if display_units == "imperial":
                    val = cached / OZ_TO_LITERS
                    unit = "oz"
                    val_str = f"{val:.1f}"
                else:
                    val = cached * 1000.0
                    unit = "ml"
                    val_str = f"{val:.0f}"
                self.last_pour_value_texts[sensor_index].set(f"{val_str} {unit}")
            else:
                self.last_pour_value_texts[sensor_index].set("--")
        
        if effective_remaining is not None: self.last_known_remaining_liters[sensor_index] = effective_remaining
        
        display_units = self.settings_manager.get_display_units()
        if effective_remaining is not None:
            pour_settings = self.settings_manager.get_pour_volume_settings()
            if display_units == "imperial":
                gallons = effective_remaining * LITERS_TO_GALLONS
                pour_oz = pour_settings['imperial_pour_oz']
                liters_per_pour = pour_oz * OZ_TO_LITERS
                servings_remaining = math.floor(effective_remaining / liters_per_pour) if liters_per_pour > 0 else 0
                self.volume1_value_texts[sensor_index].set(f"{gallons:.2f}")
                self.volume2_value_texts[sensor_index].set(f"{int(servings_remaining)}")
            else:
                liters = effective_remaining
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
        elif status_text_from_logic in ["Acquiring data...", "Hardware Fault", "Error"]:
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
            current_time = time.strftime("%H:%M:%S") 
            self.notification_status_text.set(f"[{current_time}] {message}")

    def _populate_keg_dropdowns(self):
        all_keg_defs = self.settings_manager.get_keg_definitions()
        beverage_library = self.settings_manager.get_beverage_library().get('beverages', [])
        
        bev_map = {b['id']: b['name'] for b in beverage_library}
        
        filled_kegs = []
        empty_kegs = []
        
        for keg in all_keg_defs:
            bev_id = keg.get('beverage_id', UNASSIGNED_BEVERAGE_ID)
            if bev_id != UNASSIGNED_BEVERAGE_ID and bev_id in bev_map:
                filled_kegs.append(keg) 
            else:
                empty_kegs.append(keg) 
                
        filled_kegs.sort(key=lambda k: (bev_map.get(k['beverage_id'], '').lower(), k.get('title', '').lower()))
        empty_kegs.sort(key=lambda k: k.get('title', '').lower())
        
        display_options = []
        display_options.append("★ Keg Kicked - Calibrate")
        display_options.append("Offline")
        
        self._keg_display_map = {} 
        
        def process_keg_list(keg_list, force_empty_label=False):
            for keg in keg_list:
                k_id = keg['id']
                title = keg.get('title', 'Unknown')
                bev_id = keg.get('beverage_id', UNASSIGNED_BEVERAGE_ID)
                
                if force_empty_label:
                    bev_name = "Empty"
                else:
                    bev_name = bev_map.get(bev_id, "Unknown")
                
                label = f"{bev_name} ({title})"
                display_options.append(label)
                self._keg_display_map[label] = k_id
                self._keg_display_map[k_id] = label 

        process_keg_list(filled_kegs, force_empty_label=False)
        process_keg_list(empty_kegs, force_empty_label=True)

        current_assignments_ids = self.settings_manager.get_sensor_keg_assignments()
        
        for i in range(self.num_sensors):
            if self.sensor_keg_dropdowns[i]:
                self.sensor_keg_dropdowns[i]['values'] = display_options
                assigned_id = current_assignments_ids[i]
                if assigned_id == UNASSIGNED_KEG_ID:
                    self.sensor_keg_selection_vars[i].set("Offline")
                else:
                    rich_label = self._keg_display_map.get(assigned_id, "Offline") 
                    self.sensor_keg_selection_vars[i].set(rich_label)
                    
    def _populate_beverage_dropdowns(self):
        pass
        
    def _handle_beverage_selection_change(self, sensor_idx):
        selected_beverage_name = self.sensor_beverage_selection_vars[sensor_idx].get()
        if selected_beverage_name == "Offline":
            selected_id = UNASSIGNED_BEVERAGE_ID
            self.settings_manager.save_sensor_beverage_assignment(sensor_idx, selected_id)
        else:
            beverage_library = self.settings_manager.get_beverage_library()
            beverage_list = beverage_library.get('beverages', [])
            selected_beverage = next((b for b in beverage_list if b.get('name') == selected_beverage_name), None)
            
            if selected_beverage:
                selected_id = selected_beverage.get('id')
                self.settings_manager.save_sensor_beverage_assignment(sensor_idx, selected_id)
            else:
                return

        self._refresh_beverage_metadata()
        self.refresh_tap_metadata(sensor_idx)

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
        selected_label = self.sensor_keg_selection_vars[sensor_idx].get()
        
        if selected_label.startswith("★"):
            current_assignments_ids = self.settings_manager.get_sensor_keg_assignments()
            assigned_id = current_assignments_ids[sensor_idx]
            prev_label = self._keg_display_map.get(assigned_id, "Offline")
            self.sensor_keg_selection_vars[sensor_idx].set(prev_label)
            
            confirm = messagebox.askyesno(
                "Confirm Keg Kicked",
                f"Has the keg on Tap {sensor_idx+1} completely run dry?\n\nThis function is for calibrating the tap using a known full keg volume against the pulses recorded until empty.\n\nClick YES only if the keg is empty.",
                parent=self.root
            )
            if not confirm: return
            if hasattr(self, '_open_flow_calibration_popup'):
                keg = self.settings_manager.get_keg_by_id(assigned_id)
                simple_title = keg.get('title', 'Unknown') if keg else 'Offline'
                self._open_flow_calibration_popup(initial_tab_index=1, initial_tap_index=sensor_idx, initial_keg_title=simple_title)
            return
        
        if selected_label == "Offline":
            selected_keg_id = UNASSIGNED_KEG_ID
            selected_bev_id = UNASSIGNED_BEVERAGE_ID
        else:
            selected_keg_id = self._keg_display_map.get(selected_label)
            if not selected_keg_id: return 
            
            keg_def = self.settings_manager.get_keg_by_id(selected_keg_id)
            selected_bev_id = keg_def.get('beverage_id', UNASSIGNED_BEVERAGE_ID)
            
        self.settings_manager.save_sensor_keg_assignment(sensor_idx, selected_keg_id)
        self.settings_manager.save_sensor_beverage_assignment(sensor_idx, selected_bev_id)
        
        self._refresh_ui_for_settings_or_resume()
        self.refresh_tap_metadata(sensor_idx) 
        
        if self.sensor_logic: 
            self.sensor_logic.force_recalculation()
    
    # --- Dynamic Visibility Toggler ---
    def _apply_ui_mode_visibility(self):
        """Hides or Shows metadata frames based on self.ui_mode."""
        mode = self.ui_mode # 'detailed' or 'basic'
        
        for i in range(self.num_sensors):
            frames = self.metadata_frame_refs.get(i, {})
            lite_frame = frames.get('lite')
            full_frame = frames.get('full')
            
            # --- UPDATED CHECK ---
            if mode == 'detailed':
                if lite_frame: lite_frame.pack_forget()
                if full_frame: full_frame.pack(anchor="w", pady=(2, 5), fill="x", after=self.sensor_keg_dropdowns[i].master)
            else:
                if full_frame: full_frame.pack_forget()
                if lite_frame: lite_frame.pack(anchor="w", pady=(2, 0), fill="x", after=self.sensor_keg_dropdowns[i].master)

    def _update_sensor_column_visibility(self):
        """
        Updates which columns are visible based on displayed_taps setting.
        The actual grid position is handled by _reflow_layout.
        """
        displayed_taps_count = self.settings_manager.get_displayed_taps()
        
        # 1. Update visibility state (Mapped/Unmapped)
        for i in range(self.num_sensors):
            column_frame = self.sensor_column_frames[i]
            if column_frame:
                if i < displayed_taps_count:
                    # We don't grid() here; _reflow_layout handles grid placement.
                    # Just ensure we don't hide it if it's meant to be shown.
                    pass 
                else: 
                    column_frame.grid_remove()
                    
        # 2. Apply visibility rules (Lite vs Full metadata)
        self._apply_ui_mode_visibility()
        
        # 3. Trigger layout recalculation FORCEFULLY
        # Pass force=True to ensure taps are re-gridded even if the column count 
        # (width geometry) hasn't changed.
        self._reflow_layout(self.tap_canvas.winfo_width(), force=True)

    def _refresh_ui_for_settings_or_resume(self):
        self._update_sensor_column_visibility()
        self.root.update_idletasks()
        
        self._refresh_beverage_metadata()
        self._populate_beverage_dropdowns()
        
        display_units = self.settings_manager.get_display_units()
        displayed_taps_count = self.settings_manager.get_displayed_taps()
        pour_settings = self.settings_manager.get_pour_volume_settings()
        pour_ml = pour_settings['metric_pour_ml']
        pour_oz = pour_settings['imperial_pour_oz']

        for i in range(self.num_sensors):
            if i < displayed_taps_count:
                if display_units == "imperial":
                    pours_label_str = f"{pour_oz} oz pours:"
                else:
                    pours_label_str = f"{pour_ml} ml pours:"

                # --- MODIFIED: Always use full labels (Removed 'if self.is_full_mode' logic) ---
                lbl_vol = "Gal remaining:" if display_units == "imperial" else "Liters remaining:"
                lbl_pours = pours_label_str
                lbl_last_pour = "Last Pour:"
                # -------------------------------------------------------------------------------
                
                self.volume1_label_texts[i].set(lbl_vol)
                self.volume2_label_texts[i].set(lbl_pours)
                self.last_pour_label_texts[i].set(lbl_last_pour)
                
                cached_pour = self.last_known_pour_volumes[i]
                if cached_pour > 0:
                    if display_units == "imperial":
                        val = cached_pour / OZ_TO_LITERS
                        unit = "oz"
                        val_str = f"{val:.1f}"
                    else:
                        val = cached_pour * 1000.0
                        unit = "ml"
                        val_str = f"{val:.0f}" 
                    self.last_pour_value_texts[i].set(f"{val_str} {unit}")
                else:
                    self.last_pour_value_texts[i].set("--")
                
                effective_stability_status = "Acquiring data..."
                if self.sensor_logic and self.sensor_logic.is_paused: 
                    effective_stability_status = "Paused"
                elif self.last_known_remaining_liters[i] is not None:
                    effective_stability_status = "Data stable"
                
                self._do_update_sensor_stability_display(i, effective_stability_status)
                
                if self.last_known_remaining_liters[i] is not None and not (self.sensor_logic and self.sensor_logic.is_paused):
                    self._do_update_sensor_data_display(i, 0.0, self.last_known_remaining_liters[i], "Nominal", self.last_known_pour_volumes[i])
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
        # Deprecated: No longer needed for mode switch, but kept for critical setting changes
        popup = tk.Toplevel(self.root)
        popup.title("Restart Required")
        popup.geometry("350x180")
        popup.transient(self.root)
        popup.grab_set()
        
        frame = ttk.Frame(popup, padding="15"); frame.pack(expand=True, fill="both")
        
        ttk.Label(frame, text="Settings changed. Please restart the application.", 
                  wraplength=300, justify=tk.CENTER).pack(pady=(0, 20))
        
        buttons_frame = ttk.Frame(popup, padding="10"); buttons_frame.pack(fill="x", side="bottom")
        
        ttk.Button(buttons_frame, text="Quit Application", command=lambda: [popup.destroy(), self._on_closing_ui()]).pack(side="right", padx=5)
        ttk.Button(buttons_frame, text="Close", command=popup.destroy).pack(side="right")

    def _on_closing_ui(self):
        print("UIManager: Closing application...")
        
        if self.original_numlock_state == "off":
            try: subprocess.run(['numlockx', 'off'])
            except Exception: pass
        
        if self.root and hasattr(self.root, 'winfo_exists') and self.root.winfo_exists():
            try:
                current_geometry = self.root.geometry()
                self.settings_manager.save_window_geometry(current_geometry)
            except Exception as e:
                print(f"UIManager: Could not save window geometry: {e}")

        # --- NEW: Save Workflow Geometry if open ---
        # This handles the case where the user closes the Main UI while Workflow is still open
        if self.workflow_app:
             try:
                 self.workflow_app.save_geometry()
             except Exception as e:
                 print(f"UIManager: Could not save workflow geometry: {e}")
        # -------------------------------------------

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
        if not hasattr(self, '_single_cal_popup_window') or not self._single_cal_popup_window or not self._single_cal_popup_window.winfo_exists():
            return

        self.single_cal_measured_flow_var.set(f"{flow_rate:.2f} L/min")
        
        unit_label = self.single_cal_unit_label.get()
        if unit_label == "ml":
            display_val = dispensed_liters * 1000.0
        elif unit_label == "oz":
            display_val = dispensed_liters / OZ_TO_LITERS
        else:
            display_val = dispensed_liters
            
        self.single_cal_measured_pour_var.set(f"{display_val:.2f}")
        
    def refresh_tap_metadata(self, sensor_index):
        if not hasattr(self, 'sensor_column_frames') or sensor_index >= len(self.sensor_column_frames):
            return

        kegs = self.settings_manager.get_keg_definitions()
        assignments = self.settings_manager.get_sensor_keg_assignments()
        beverage_assignments = self.settings_manager.get_sensor_beverage_assignments()
        beverage_lib = self.settings_manager.get_beverage_library().get('beverages', [])
        
        keg_id = assignments[sensor_index]
        beverage_id = beverage_assignments[sensor_index]
        
        beverage = next((b for b in beverage_lib if b['id'] == beverage_id), None)
        beverage_name = beverage['name'] if beverage else "Unknown"
        
        # --- FIX: Handle NoneType for beverage ---
        srm = beverage.get('srm') if beverage else None
        # -----------------------------------------
        
        # Note: Colors are handled via styles now
        self._update_tap_progress_bar_colors()
        
    def run(self):
        self.root.mainloop()
