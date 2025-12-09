# keglevel app
#
# setup_wizard.py
import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont
import os
import sys
import glob

# Try to import platform flag, default to False if module missing (e.g. dev PC)
try:
    from sensor_logic import IS_RASPBERRY_PI_MODE
except ImportError:
    IS_RASPBERRY_PI_MODE = False

# Constants
WIZARD_WIDTH = 720
WIZARD_HEIGHT = 480

class SetupWizard:
    def __init__(self, settings_manager):
        self.settings_manager = settings_manager
        self.root = tk.Tk()
        self.root.title("KegLevel Monitor - Initial Setup")
        
        # Center the wizard
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = int((screen_width / 2) - (WIZARD_WIDTH / 2))
        y = int((screen_height / 2) - (WIZARD_HEIGHT / 2))
        self.root.geometry(f"{WIZARD_WIDTH}x{WIZARD_HEIGHT}+{x}+{y}")
        self.root.resizable(False, False)
        
        self.current_step = 0
        self.wizard_data = {
            "ui_mode": "detailed", # Default to Detailed
            "taps": 3,             # Default to 3
            "units": "metric",
            "temp_sensor": "unassigned",
            "numlock": True        # Default to True (Enabled)
        }
        
        self.content_frame = ttk.Frame(self.root, padding="20")
        self.content_frame.pack(fill="both", expand=True)
        
        self.steps = [
            self._step_eula,
            self._step_donation,
            self._step_mode_selection,
            self._step_system_config,
            self._step_finish
        ]
        
        self._define_styles()
        
        # Start
        self._show_current_step()

    def run(self):
        self.root.mainloop()
        # Return True if setup finished successfully, False if closed/cancelled
        return self.settings_manager.get_setup_complete()

    def _define_styles(self):
        """Defines styling for the live preview cards."""
        s = ttk.Style()
        try: s.theme_use('default')
        except: pass
        
        common_opts = {'troughcolor': '#E0E0E0', 'borderwidth': 1, 'relief': 'sunken'}
        s.configure("green.Horizontal.TProgressbar", background='green', **common_opts)
        s.configure('Tap.Bold.TLabel', font=('TkDefaultFont', 10, 'bold'))
        s.configure('Metadata.Bold.TLabel', font=('TkDefaultFont', 9, 'bold'))
        s.configure('LightGray.TFrame', background='#F0F0F0')
        s.configure('Card.TFrame', relief='groove', borderwidth=1)
        
        # Selected/Unselected styles for Mode cards
        s.configure('Selected.Card.TFrame', relief='solid', borderwidth=2, background='#e6f3ff')
        s.configure('Unselected.Card.TFrame', relief='groove', borderwidth=1, background='#f0f0f0')

    def _clear_frame(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def _show_current_step(self):
        self._clear_frame()
        if 0 <= self.current_step < len(self.steps):
            self.steps[self.current_step]()
        else:
            self.root.destroy()

    def _next_step(self):
        self.current_step += 1
        self._show_current_step()

    def _prev_step(self):
        if self.current_step > 0:
            self.current_step -= 1
            self._show_current_step()

    # --- STEP 1: EULA ---
    def _step_eula(self):
        ttk.Label(self.content_frame, text="End User License Agreement", font=('TkDefaultFont', 16, 'bold')).pack(pady=(0, 10))
        
        text_area = tk.Text(self.content_frame, wrap="word", height=12, relief="sunken", borderwidth=1)
        text_area.pack(fill="both", expand=True, pady=(0, 10))
        
        eula_text = (
            "1. Scope of Agreement\n"
            "This Agreement applies to the \"Keg Level Monitor\" software. By using this software, you agree to these terms.\n\n"
            "2. Acceptance of Responsibility\n"
            "You, the user, accept all responsibility for any consequence or outcome arising from the use of this app.\n\n"
            "3. No Guarantee or Warranty\n"
            "This app is provided \"as is\" without warranty of any kind. You use this app entirely at your own risk."
        )
        text_area.insert("1.0", eula_text)
        text_area.config(state="disabled")
        
        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(fill="x", side="bottom")
        
        def on_disagree():
            if messagebox.askyesno("Exit Setup?", "You must accept the EULA to use this software.\nExit application?", parent=self.root):
                sys.exit(0)
                
        def on_agree():
            # Save agreement immediately
            sys_set = self.settings_manager.get_system_settings()
            sys_set['eula_agreed'] = True
            sys_set['show_eula_on_launch'] = False
            self.settings_manager.settings['system_settings'] = sys_set
            self.settings_manager._save_all_settings()
            self._next_step()

        ttk.Button(btn_frame, text="I Do Not Agree", command=on_disagree).pack(side="left")
        ttk.Button(btn_frame, text="I Agree", command=on_agree).pack(side="right")

    # --- STEP 2: DONATION ---
    def _step_donation(self):
        ttk.Label(self.content_frame, text="Support the Project", font=('TkDefaultFont', 16, 'bold')).pack(pady=(0, 10))
        
        msg = (
            "This app took hundreds of hours to develop, test, and optimize. "
            "Please consider supporting this app with a donation so continuous "
            "improvements can be made. Thank you!"
        )
        ttk.Label(self.content_frame, text=msg, wraplength=600, justify="center").pack(pady=(0, 20))
        
        # Try to load image
        try:
            base_dir = self.settings_manager.get_base_dir()
            img_path = os.path.join(base_dir, "assets", "support.gif")
            if os.path.exists(img_path):
                img = tk.PhotoImage(file=img_path)
                lbl = ttk.Label(self.content_frame, image=img)
                lbl.image = img # Keep ref
                lbl.pack()
            else:
                ttk.Label(self.content_frame, text="[QR Code Placeholder]", relief="sunken", padding=20).pack()
        except Exception:
            pass

        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(fill="x", side="bottom", pady=10)
        ttk.Button(btn_frame, text="Next >>", command=self._next_step).pack(side="right")

    # --- STEP 3: MODE SELECTION (Live Cards) ---
    def _step_mode_selection(self):
        ttk.Label(self.content_frame, text="Choose Display Detail", font=('TkDefaultFont', 16, 'bold')).pack(pady=(0, 5))
        ttk.Label(self.content_frame, text="Click on the layout you prefer. You can change this later in Settings.", font=('TkDefaultFont', 10)).pack(pady=(0, 15))
        
        container = ttk.Frame(self.content_frame)
        container.pack(expand=True, fill="both")
        
        # Variables to track selection
        self.selected_mode_var = tk.StringVar(value=self.wizard_data['ui_mode'])
        
        # --- Helper to draw a fake card ---
        def draw_card(parent, mode, title):
            # Dynamic Height: Tall for Detailed, Short for Basic
            card_height = 320 if mode == 'detailed' else 200
            
            # Outer Frame (Clickable)
            style_name = 'Selected.Card.TFrame' if self.selected_mode_var.get() == mode else 'Unselected.Card.TFrame'
            card = ttk.Frame(parent, padding=5, style=style_name, width=320, height=card_height)
            card.pack_propagate(False) # Force fixed size
            card.pack(fill="both", expand=True) 
            
            # Header
            ttk.Label(card, text=title, font=('TkDefaultFont', 12, 'bold')).pack(pady=(0, 5))
            
            # Mock Card Content
            inner = ttk.Frame(card)
            inner.pack(fill="x", pady=2)
            ttk.Label(inner, text="Tap 1: House Pale Ale", font=('TkDefaultFont', 9, 'bold')).pack(anchor="w")
            
            if mode == 'detailed':
                # Full Metadata Box
                meta = ttk.Frame(card, style='LightGray.TFrame', padding=5)
                meta.pack(fill="x", pady=2)
                
                r1 = ttk.Frame(meta, style='LightGray.TFrame'); r1.pack(fill="x")
                
                # Use tk.Label for bg color support
                tk.Label(r1, text="BJCP: 18B", font=('TkDefaultFont', 8, 'bold'), bg='#F0F0F0').pack(side="left")
                
                # Right Side: IBU and ABV
                right_stats = tk.Frame(r1, bg='#F0F0F0')
                right_stats.pack(side="right")
                tk.Label(right_stats, text="IBU: 35", font=('TkDefaultFont', 8, 'bold'), bg='#F0F0F0').pack(side="right", padx=(5,0))
                # Make ABV Bold
                tk.Label(right_stats, text="ABV: 5.5%", font=('TkDefaultFont', 8, 'bold'), bg='#F0F0F0').pack(side="right")
                
                # Longer Description Text
                desc_text = "A refreshing American Pale Ale with citrus notes and a clean, dry finish. This all-grain brew was made from locally grown and malted barley, hops from the Pacific Northwest, and yeast cultivated in the US. The House Pale Ale is our brewerie's go-to beer for any occasion."
                tk.Label(meta, text=desc_text, 
                          font=('TkDefaultFont', 8, 'italic'), bg='#F0F0F0', wraplength=280, justify="left", anchor="w").pack(fill="x", pady=2)
            else:
                # Lite Metadata Line
                meta = ttk.Frame(card)
                meta.pack(fill="x", pady=2)
                ttk.Label(meta, text="ABV:", font=('TkDefaultFont', 8, 'bold')).pack(side="left")
                ttk.Label(meta, text="5.5%", font=('TkDefaultFont', 8)).pack(side="left")
                
                # Swap Order (Pack Right: Value First, Then Label)
                ttk.Label(meta, text="35", font=('TkDefaultFont', 8)).pack(side="right")
                ttk.Label(meta, text="IBU:", font=('TkDefaultFont', 8, 'bold')).pack(side="right", padx=(0, 2))
            
            # Progress Bar
            ttk.Progressbar(card, value=60, style="green.Horizontal.TProgressbar").pack(fill="x", pady=5)
            
            # Stats Rows
            r_flow = ttk.Frame(card); r_flow.pack(fill="x")
            ttk.Label(r_flow, text="Flow Rate:").pack(side="left")
            ttk.Label(r_flow, text="0.00").pack(side="left")
            
            r_pour = ttk.Frame(card); r_pour.pack(fill="x")
            ttk.Label(r_pour, text="Last Pour:").pack(side="left")
            ttk.Label(r_pour, text="450 ml").pack(side="left")
            
            r_vol = ttk.Frame(card); r_vol.pack(fill="x")
            ttk.Label(r_vol, text="Liters rem:").pack(side="left")
            ttk.Label(r_vol, text="12.5").pack(side="left")
            
            r_count = ttk.Frame(card); r_count.pack(fill="x")
            ttk.Label(r_count, text="Pours rem:").pack(side="left")
            ttk.Label(r_count, text="35").pack(side="left")

            return card

        # --- Frames for Left (Detailed) and Right (Basic) ---
        left_frame = ttk.Frame(container); left_frame.pack(side="left", expand=True, padx=10, anchor="n")
        right_frame = ttk.Frame(container); right_frame.pack(side="right", expand=True, padx=10, anchor="n")
        
        def select_mode(mode):
            self.selected_mode_var.set(mode)
            self.wizard_data['ui_mode'] = mode
            self._show_current_step()

        # Render Cards
        detailed_card = draw_card(left_frame, 'detailed', "Detailed View")
        basic_card = draw_card(right_frame, 'basic', "Basic View")
        
        # Bind Clicks
        def bind_click(widget, mode):
            widget.bind("<Button-1>", lambda e: select_mode(mode))
            for child in widget.winfo_children():
                bind_click(child, mode)
                
        bind_click(detailed_card, 'detailed')
        bind_click(basic_card, 'basic')

        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(fill="x", side="bottom", pady=10)
        ttk.Button(btn_frame, text="Next >>", command=self._next_step).pack(side="right")

    # --- STEP 4: SYSTEM SETTINGS (Taps, Units, Temp, NumLock) ---
    def _step_system_config(self):
        ttk.Label(self.content_frame, text="System Settings", font=('TkDefaultFont', 16, 'bold')).pack(pady=(0, 5))
        ttk.Label(self.content_frame, text="Select the system settings you prefer. You can change this later in Settings.", font=('TkDefaultFont', 10)).pack(pady=(0, 20))
        
        form_frame = ttk.Frame(self.content_frame)
        form_frame.pack()
        
        # 1. Taps
        ttk.Label(form_frame, text="Number of Taps:", font=('TkDefaultFont', 12)).grid(row=0, column=0, pady=10, sticky="e", padx=10)
        
        default_taps = str(self.wizard_data.get('taps', 3))
        self.taps_var = tk.StringVar(value=default_taps)
        
        taps_spin = ttk.Spinbox(form_frame, from_=1, to=10, textvariable=self.taps_var, width=5, font=('TkDefaultFont', 12))
        taps_spin.grid(row=0, column=1, pady=10, sticky="w")
        taps_spin.set(default_taps)
        
        # 2. Units
        ttk.Label(form_frame, text="Display Units:", font=('TkDefaultFont', 12)).grid(row=1, column=0, pady=10, sticky="ne", padx=10)
        
        units_frame = ttk.Frame(form_frame)
        units_frame.grid(row=1, column=1, pady=10, sticky="w")
        
        self.units_var = tk.StringVar(value=self.wizard_data['units'])
        
        ttk.Radiobutton(units_frame, text="Metric (Liters / Kg / °C)", variable=self.units_var, value="metric").pack(anchor="w", pady=5)
        ttk.Radiobutton(units_frame, text="Imperial (Gallons / Lb / °F)", variable=self.units_var, value="imperial").pack(anchor="w", pady=5)
        
        # 3. Temperature Sensor
        ttk.Label(form_frame, text="Temperature Sensor:", font=('TkDefaultFont', 12)).grid(row=2, column=0, pady=10, sticky="e", padx=10)
        
        sensors = []
        try:
            base_dir = '/sys/bus/w1/devices/'
            device_folders = glob.glob(base_dir + '28-*')
            sensors = [os.path.basename(f) for f in device_folders]
        except: pass
        
        self.sensor_var = tk.StringVar()
        
        if not sensors:
            ttk.Label(form_frame, text="<None Detected>", foreground="red", font=('TkDefaultFont', 11)).grid(row=2, column=1, pady=10, sticky="w")
            self.wizard_data['temp_sensor'] = "unassigned"
            self.sensor_var.set("unassigned") 
        elif len(sensors) == 1:
            single_id = sensors[0]
            ttk.Label(form_frame, text=f"<{single_id}>", foreground="green", font=('TkDefaultFont', 11, 'bold')).grid(row=2, column=1, pady=10, sticky="w")
            self.wizard_data['temp_sensor'] = single_id
            self.sensor_var.set(single_id)
        else:
            sensor_dropdown = ttk.Combobox(form_frame, textvariable=self.sensor_var, values=sensors, state="readonly", width=20)
            sensor_dropdown.grid(row=2, column=1, pady=10, sticky="w")
            if not self.wizard_data['temp_sensor'] or self.wizard_data['temp_sensor'] == "unassigned":
                 self.sensor_var.set(sensors[0])
            else:
                 self.sensor_var.set(self.wizard_data['temp_sensor'])

        current_row = 3

        # 4. Force Num Lock
        if IS_RASPBERRY_PI_MODE:
            self.numlock_var = tk.BooleanVar(value=self.wizard_data.get('numlock', True))
            nl_chk = ttk.Checkbutton(form_frame, text="Force Num Lock ON while app is running", variable=self.numlock_var)
            nl_chk.grid(row=current_row, column=0, columnspan=2, pady=(15, 5), sticky="w", padx=10)
            current_row += 1

        # 5. Enable Pour Log (NEW)
        self.enable_log_var = tk.BooleanVar(value=True)
        log_chk = ttk.Checkbutton(form_frame, text="Enable Pour Log", variable=self.enable_log_var)
        log_chk.grid(row=current_row, column=0, columnspan=2, pady=5, sticky="w", padx=10)

        # Buttons
        btn_frame = ttk.Frame(self.content_frame)
        btn_frame.pack(fill="x", side="bottom", pady=10)
        
        def on_next():
            try:
                val = taps_spin.get().strip()
                if not val: val = self.taps_var.get().strip()
                taps_val = 3 if not val else max(1, min(10, int(val)))
            except ValueError:
                taps_val = 3 
                
            self.wizard_data['taps'] = taps_val
            self.wizard_data['units'] = self.units_var.get()
            
            if len(sensors) > 1: self.wizard_data['temp_sensor'] = self.sensor_var.get()
            if IS_RASPBERRY_PI_MODE: self.wizard_data['numlock'] = self.numlock_var.get()
            
            # Save log setting to wizard data
            self.wizard_data['enable_pour_log'] = self.enable_log_var.get()
            
            self._next_step()
            
        ttk.Button(btn_frame, text="<< Back", command=self._prev_step).pack(side="left")
        ttk.Button(btn_frame, text="Finish Setup", command=on_next).pack(side="right")

    # --- STEP 5: FINISH (Hidden processing step) ---
    def _step_finish(self):
        # Save all data
        print("Wizard: Saving configuration...")
        
        # 1. UI Mode
        self.settings_manager.save_ui_mode(self.wizard_data['ui_mode'])
        
        # 2. Units
        self.settings_manager.save_display_units(self.wizard_data['units'])
        
        # 3. Taps
        self.settings_manager.save_displayed_taps(self.wizard_data['taps'])
        
        # 4. Temp Sensor
        self.settings_manager.set_ds18b20_ambient_sensor(self.wizard_data['temp_sensor'])
        
        # 5. Num Lock
        if IS_RASPBERRY_PI_MODE:
            self.settings_manager.save_force_numlock(self.wizard_data['numlock'])
            
        # 6. Enable Pour Log (NEW)
        self.settings_manager.save_enable_pour_log(self.wizard_data.get('enable_pour_log', True))
        
        # 7. Set Flag
        self.settings_manager.set_setup_complete(True)
        
        messagebox.showinfo("Setup Complete", "Configuration saved! Launching application...", parent=self.root)
        self.root.destroy()
