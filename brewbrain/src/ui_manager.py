"""
src/ui_manager.py
"""

import tkinter as tk
from tkinter import ttk, messagebox
from profile_editor import ProfileEditor
from profile_data import BrewProfile
from sequence_manager import SequenceStatus

class UIManager:
    
    def __init__(self, root, sequence_manager, hardware_interface):
        self.root = root
        self.sequencer = sequence_manager
        self.settings = sequence_manager.settings
        self.hw = hardware_interface # <--- NEW
        
        # Click Tracking for Dev Mode
        self.title_clicks = 0
        self.last_click_time = 0
        
        # Window Setup
        self.root.title("BrewBrain")
        self.root.geometry("800x600")
        self.root.resizable(False, False)
        
        # Style Configuration
        self._configure_styles()
        
        # --- UI State Variables ---
        self.current_temp_var = tk.StringVar(value="--.-°F")
        self.timer_var = tk.StringVar(value="--:--")
        self.status_text_var = tk.StringVar(value="System Idle")
        self.target_text_var = tk.StringVar(value="Target: --.-°F")
        
        # Button Vars
        self.action_btn_text = tk.StringVar(value="START")
        
        # Build the Layout
        self._create_main_layout()
        
        # Start the UI Poll Loop
        self._update_loop()

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use('default') 
        
        # HERO ZONE STYLES
        style.configure('Hero.TFrame', background='#222222')
        style.configure('HeroTemp.TLabel', font=('Arial', 80, 'bold'), background='#222222', foreground='white')
        style.configure('HeroTempRed.TLabel', font=('Arial', 80, 'bold'), background='#222222', foreground='#ff4444') # Heating
        style.configure('HeroTimer.TLabel', font=('Arial', 80, 'bold'), background='#222222', foreground='#00ff00') # Matrix Green
        style.configure('HeroStatus.TLabel', font=('Arial', 18), background='#222222', foreground='#cccccc')
        style.configure('HeroTarget.TLabel', font=('Arial', 14), background='#222222', foreground='#888888')

        # SEQUENCE STRIP STYLES
        style.configure('Strip.TFrame', background='#444444')
        
        # Cards
        style.configure('CardPrev.TFrame', background='#333333', relief='flat')
        style.configure('CardCurrent.TFrame', background='#ffffff', relief='raised', borderwidth=3)
        style.configure('CardNext.TFrame', background='#666666', relief='flat')
        
        # Card Text
        style.configure('CardTitle.TLabel', font=('Arial', 14, 'bold'))
        style.configure('CardBody.TLabel', font=('Arial', 10))
        
        # CONTROL ZONE STYLES
        style.configure('Controls.TFrame', background='#222222')
        
        # Big Buttons
        style.configure('Action.TButton', font=('Arial', 16, 'bold'))
        style.configure('Stop.TButton', font=('Arial', 16, 'bold'), foreground='red')

    def _create_main_layout(self):
        # 1. Hero Zone (Top 40% = 240px)
        self.hero_frame = ttk.Frame(self.root, style='Hero.TFrame', height=240)
        self.hero_frame.pack(side='top', fill='x', expand=False)
        self.hero_frame.pack_propagate(False) 
        self._create_hero_widgets()
        
        # BIND CLICK FOR DEV MODE
        self.hero_frame.bind("<Button-1>", self._on_header_click)

        # 2. Sequence Strip (Middle 35% = 210px)
        self.strip_frame = ttk.Frame(self.root, style='Strip.TFrame', height=210)
        self.strip_frame.pack(side='top', fill='x', expand=False)
        self.strip_frame.pack_propagate(False)
        self._create_sequence_strip_widgets()

        # 3. Controls (Bottom 25% = 150px)
        self.controls_frame = ttk.Frame(self.root, style='Controls.TFrame', height=150)
        self.controls_frame.pack(side='bottom', fill='both', expand=True)
        self._create_control_widgets()

    def _create_hero_widgets(self):
        # Top Row: Temp (Left) and Timer (Right)
        top_row = ttk.Frame(self.hero_frame, style='Hero.TFrame')
        top_row.pack(fill='x', pady=(20, 0), padx=30)
        
        self.lbl_temp = ttk.Label(top_row, textvariable=self.current_temp_var, style='HeroTemp.TLabel')
        self.lbl_temp.pack(side='left')
        
        # BIND TEMP CLICK FOR VIRTUAL SLIDER
        self.lbl_temp.bind("<Button-1>", self._on_temp_click)
        
        self.lbl_timer = ttk.Label(top_row, textvariable=self.timer_var, style='HeroTimer.TLabel')
        self.lbl_timer.pack(side='right')
        
        # Bottom Row: Status Text
        self.lbl_status = ttk.Label(self.hero_frame, textvariable=self.status_text_var, style='HeroStatus.TLabel')
        self.lbl_status.pack(side='top', pady=(10, 0))
        
        self.lbl_target = ttk.Label(self.hero_frame, textvariable=self.target_text_var, style='HeroTarget.TLabel')
        self.lbl_target.pack(side='top')

    def _create_sequence_strip_widgets(self):
        container = ttk.Frame(self.strip_frame, style='Strip.TFrame')
        container.pack(expand=True, fill='both', padx=20, pady=20)
        
        # Grid: 25% | 50% | 25%
        container.columnconfigure(0, weight=1)
        container.columnconfigure(1, weight=2) 
        container.columnconfigure(2, weight=1)
        container.rowconfigure(0, weight=1)
        
        # --- PREVIOUS STEP (Left) ---
        self.card_prev = ttk.Frame(container, style='CardPrev.TFrame')
        self.card_prev.grid(row=0, column=0, sticky='nsew', padx=5)
        
        self.lbl_prev_title = ttk.Label(self.card_prev, text="", style='CardTitle.TLabel', background='#333333', foreground='#666666')
        self.lbl_prev_title.pack(expand=True)
        
        # --- CURRENT STEP (Middle) ---
        self.card_curr = ttk.Frame(container, style='CardCurrent.TFrame')
        self.card_curr.grid(row=0, column=1, sticky='nsew', padx=5)
        
        self.lbl_curr_title = ttk.Label(self.card_curr, text="Load Profile", style='CardTitle.TLabel', background='#ffffff')
        self.lbl_curr_title.pack(pady=(20, 10))
        
        self.lbl_curr_details = ttk.Label(self.card_curr, text="Press 'Profiles' to begin", style='CardBody.TLabel', background='#ffffff')
        self.lbl_curr_details.pack()

        # --- NEXT STEP (Right) ---
        self.card_next = ttk.Frame(container, style='CardNext.TFrame')
        self.card_next.grid(row=0, column=2, sticky='nsew', padx=5)
        
        self.lbl_next_title = ttk.Label(self.card_next, text="", style='CardTitle.TLabel', background='#666666', foreground='#cccccc')
        self.lbl_next_title.pack(expand=True)

    def _create_control_widgets(self):
        # 1. Profiles Button
        btn_profiles = ttk.Button(self.controls_frame, text="PROFILES\nLIBRARY", command=self._on_profiles_click)
        btn_profiles.place(relx=0.05, rely=0.2, relwidth=0.2, relheight=0.6)
        
        # 2. Main Action Button
        self.btn_action = ttk.Button(self.controls_frame, textvariable=self.action_btn_text, style='Action.TButton', command=self._on_action_click)
        self.btn_action.place(relx=0.28, rely=0.15, relwidth=0.44, relheight=0.7)
        
        # 3. Abort Button
        btn_abort = ttk.Button(self.controls_frame, text="ABORT\nSTOP", style='Stop.TButton', command=self._on_abort_click)
        btn_abort.place(relx=0.75, rely=0.2, relwidth=0.2, relheight=0.6)

    # --- EVENT HANDLERS ---
    
    def _on_profiles_click(self):
        ProfileLibraryPopup(self.root, self.settings, self.sequencer)

    def _on_action_click(self):
        status = self.sequencer.status
        
        if status == SequenceStatus.IDLE:
            if not self.sequencer.current_profile:
                messagebox.showinfo("No Profile", "Please load a profile from the Library first.")
                return
            self.sequencer.start_sequence()
            
        elif status == SequenceStatus.RUNNING:
            self.sequencer.pause_sequence()
            
        elif status == SequenceStatus.PAUSED:
            self.sequencer.resume_sequence()
            
        elif status == SequenceStatus.WAITING_FOR_USER:
            if messagebox.askyesno("Advance Step", "Are you ready to move to the next step?"):
                self.sequencer.advance_step()

    def _on_abort_click(self):
        if messagebox.askyesno("Abort Brew?", "Are you sure you want to STOP everything?"):
            self.sequencer.stop()

    # --- DEV MODE HANDLERS ---

    def _on_header_click(self, event):
        import time
        now = time.time()
        
        # Reset if too slow
        if now - self.last_click_time > 2.0:
            self.title_clicks = 0
            
        self.title_clicks += 1
        self.last_click_time = now
        # print(f"Click {self.title_clicks}")
        
        if self.title_clicks >= 5:
            self.title_clicks = 0
            if not self.hw.is_dev_mode():
                self._show_safety_dialog()
            else:
                pass # Already in Dev Mode

    def _show_safety_dialog(self):
        """The 'Two-Key Turn' Safety Dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("SAFETY INTERLOCK")
        dialog.geometry("400x300")
        dialog.configure(bg="#c0392b")
        dialog.transient(self.root) 
        dialog.wait_visibility()
        dialog.grab_set()

        tk.Label(dialog, text="⚠ WARNING ⚠", font=("Arial", 24, "bold"), bg="#c0392b", fg="white").pack(pady=20)
        tk.Label(dialog, text="ENTERING DEVELOPER MODE\n\nSensors will be disconnected.\nEnsure heaters are safe.", 
                 bg="#c0392b", fg="white", font=("Arial", 12)).pack(pady=10)

        tk.Label(dialog, text="Slide to Unlock", bg="#c0392b", fg="white").pack(pady=(20, 0))

        # THE SLIDER
        self.safety_slider = tk.Scale(dialog, from_=0, to=100, orient="horizontal", length=300, showvalue=0)
        self.safety_slider.pack(pady=10)
        
        # Bind release event to check if it reached 100
        self.safety_slider.bind("<ButtonRelease-1>", lambda e: self._check_slider(dialog))

    def _check_slider(self, dialog_window):
        val = self.safety_slider.get()
        if val >= 100:
            # SUCCESS
            self.hw.set_dev_mode(True)
            # Visual indication
            style = ttk.Style()
            style.configure('Hero.TFrame', background='#e67e22') # Orange
            self.hero_frame.configure(style='Hero.TFrame')
            
            dialog_window.destroy()
        else:
            # SNAP BACK
            self.safety_slider.set(0)

    def _on_temp_click(self, event):
        """Open Virtual Temp slider if in Dev Mode"""
        if self.hw.is_dev_mode():
            self._show_dev_controls()

    def _show_dev_controls(self):
        ctls = tk.Toplevel(self.root)
        ctls.title("Virtual Sensor")
        ctls.geometry("300x150")
        
        tk.Label(ctls, text="Adjust Virtual Temperature").pack(pady=10)
        
        # Initial value
        current_v = self.hw.read_temperature()
        
        s = tk.Scale(ctls, from_=50, to=220, orient="horizontal", length=250)
        s.set(current_v)
        s.pack(pady=10)
        
        # Update HW immediately on drag
        s.bind("<B1-Motion>", lambda e: self.hw.set_virtual_temp(s.get()))
        s.bind("<ButtonRelease-1>", lambda e: self.hw.set_virtual_temp(s.get()))

    # --- UPDATE LOOP ---
    
    def _update_loop(self):
        self.update_ui_from_state()
        self.root.after(250, self._update_loop)

    def update_ui_from_state(self):
        # 1. Update Temperature
        t = self.sequencer.current_temp
        self.current_temp_var.set(f"{t:.1f}°F")
        
        # Change color if heating
        if self.sequencer.is_heating:
            self.lbl_temp.configure(style='HeroTempRed.TLabel')
        else:
            self.lbl_temp.configure(style='HeroTemp.TLabel')

        # 2. Update Timer
        self.timer_var.set(self.sequencer.get_display_timer())
        
        # 3. Update Status Texts
        self.status_text_var.set(self.sequencer.get_status_message())
        
        tgt = self.sequencer.get_target_temp()
        if tgt:
            self.target_text_var.set(f"Target: {tgt:.1f}°F")
        else:
            self.target_text_var.set("")

        # 4. Update Sequence Strip
        prev_txt, curr_txt, next_txt = self.sequencer.get_step_preview_texts()
        
        self.lbl_prev_title.config(text=prev_txt)
        
        if self.sequencer.current_profile:
            self.lbl_curr_title.config(text=self.sequencer.current_profile.name)
        else:
            self.lbl_curr_title.config(text="No Profile Loaded")
            
        self.lbl_curr_details.config(text=curr_txt)
        self.lbl_next_title.config(text=next_txt)

        # 5. Update Action Button Text/State
        st = self.sequencer.status
        if st == SequenceStatus.IDLE:
            self.action_btn_text.set("START BREW")
            self.btn_action.state(['!disabled'])
        elif st == SequenceStatus.RUNNING:
            self.action_btn_text.set("PAUSE")
            self.btn_action.state(['!disabled'])
        elif st == SequenceStatus.PAUSED:
            self.action_btn_text.set("RESUME")
            self.btn_action.state(['!disabled'])
        elif st == SequenceStatus.WAITING_FOR_USER:
            self.action_btn_text.set("NEXT STEP >>")
        elif st == SequenceStatus.COMPLETED:
            self.action_btn_text.set("COMPLETE")
            self.btn_action.state(['disabled'])

# --- SUB-CLASS: PROFILE LIBRARY POPUP ---

class ProfileLibraryPopup(tk.Toplevel):
    def __init__(self, parent, settings_manager, sequencer):
        super().__init__(parent)
        self.title("Profile Library")
        self.geometry("600x400")
        self.transient(parent)
        
        self.settings = settings_manager
        self.sequencer = sequencer
        
        self._layout()
        self._refresh_list()
        
        # --- ROBUST WINDOW MANAGEMENT ---
        self.protocol("WM_DELETE_WINDOW", self.close) 
        self.grab_set() 
        self.focus_set() 
        self.wait_visibility() 

    def close(self):
        """Releases grab explicitly before destroying window."""
        self.grab_release()
        if self.master:
            self.master.focus_set()
        self.destroy()

    def _layout(self):
        # Toolbar
        toolbar = ttk.Frame(self, padding=5)
        toolbar.pack(fill='x', side='bottom')
        
        ttk.Button(toolbar, text="Load & Run", command=self._load_selected).pack(side='right', padx=5)
        ttk.Button(toolbar, text="Edit", command=self._edit_selected).pack(side='right', padx=5)
        ttk.Button(toolbar, text="Delete", command=self._delete_selected).pack(side='right', padx=5)
        ttk.Button(toolbar, text="+ New Profile", command=self._create_new).pack(side='left', padx=5)
        
        # List
        self.tree = ttk.Treeview(self, columns=("steps", "date"), show="tree headings")
        self.tree.heading("#0", text="Profile Name")
        self.tree.heading("steps", text="Steps")
        self.tree.heading("date", text="Created")
        self.tree.column("steps", width=50, anchor='center')
        self.tree.column("date", width=100)
        
        self.tree.pack(fill='both', expand=True, padx=10, pady=10)

    def _refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        profiles = self.settings.get_all_profiles()
        for p in profiles:
            self.tree.insert("", "end", iid=p.id, text=p.name, values=(len(p.steps), p.created_date))

    def _get_selected_id(self):
        sel = self.tree.selection()
        if not sel: return None
        return sel[0]

    def _load_selected(self):
        pid = self._get_selected_id()
        if not pid: return
        
        profile = self.settings.get_profile_by_id(pid)
        if profile:
            self.sequencer.load_profile(profile)
            # Use close() instead of destroy() to release grab
            self.close()

    def _edit_selected(self):
        pid = self._get_selected_id()
        if not pid: return
        
        profile = self.settings.get_profile_by_id(pid)
        if profile:
            # Open Editor
            ProfileEditor(self, profile, on_save_callback=self._on_editor_save)

    def _create_new(self):
        # Create dummy profile
        new_p = BrewProfile(name="New Profile")
        # Open Editor immediately
        ProfileEditor(self, new_p, on_save_callback=self._on_editor_save)

    def _delete_selected(self):
        pid = self._get_selected_id()
        if not pid: return
        if messagebox.askyesno("Confirm", "Delete this profile?"):
            self.settings.delete_profile(pid)
            self._refresh_list()

    def _on_editor_save(self, profile):
        # Save to disk
        self.settings.save_profile(profile)
        self._refresh_list()
