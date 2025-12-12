"""
src/ui_manager.py
"""
import tkinter as tk
from tkinter import ttk, messagebox
import traceback
from profile_editor import ProfileEditor
from profile_data import BrewProfile, TimeoutBehavior, SequenceStatus

class UIManager:
    
    def __init__(self, root, sequence_manager, hardware_interface):
        self.root = root
        self.sequencer = sequence_manager
        self.settings = sequence_manager.settings
        self.hw = hardware_interface 
        self.title_clicks = 0
        self.last_click_time = 0
        
        # --- WINDOW REFERENCES ---
        self.dev_window = None
        self.library_window = None
        
        # --- STATE TRACKING ---
        self.last_profile_id = None 
        self.last_active_iid = None 
        
        self.root.title("BrewBrain")
        self.root.geometry("800x600")
        self.root.resizable(False, False)
        self._configure_styles()
        
        self.current_temp_var = tk.StringVar(value="--.-°F")
        self.timer_var = tk.StringVar(value="--:--")
        self.status_text_var = tk.StringVar(value="System Idle")
        self.target_text_var = tk.StringVar(value="Target: --.-°F")
        self.next_addition_var = tk.StringVar(value="")
        self.action_btn_text = tk.StringVar(value="START")
        
        self._create_main_layout()
        self._update_loop()

    def _configure_styles(self):
        style = ttk.Style()
        style.theme_use('default') 
        style.configure('Hero.TFrame', background='#222222')
        
        # --- TEMP COLOR STYLES ---
        style.configure('HeroTemp.TLabel', font=('Arial', 80, 'bold'), background='#222222', foreground='white')
        style.configure('HeroTempRed.TLabel', font=('Arial', 80, 'bold'), background='#222222', foreground='#ff4444')
        style.configure('HeroTempBlue.TLabel', font=('Arial', 80, 'bold'), background='#222222', foreground='#3498db')
        style.configure('HeroTempGreen.TLabel', font=('Arial', 80, 'bold'), background='#222222', foreground='#00ff00')

        style.configure('HeroTimer.TLabel', font=('Arial', 80, 'bold'), background='#222222', foreground='#00ff00')
        style.configure('HeroStatus.TLabel', font=('Arial', 18), background='#222222', foreground='#cccccc')
        style.configure('HeroTarget.TLabel', font=('Arial', 14), background='#222222', foreground='#888888')
        style.configure('HeroAddition.TLabel', font=('Arial', 14, 'bold'), background='#222222', foreground='#f1c40f')
        style.configure('Strip.TFrame', background='#444444')
        style.configure('Controls.TFrame', background='#222222')
        
        style.configure('Action.TButton', font=('Arial', 16, 'bold'), foreground='blue')
        style.configure('Stop.TButton', font=('Arial', 16, 'bold'), foreground='red')
        style.configure('Advance.TButton', font=('Arial', 16, 'bold'), foreground='blue')

    def _create_main_layout(self):
        self.hero_frame = ttk.Frame(self.root, style='Hero.TFrame', height=240)
        self.hero_frame.pack(side='top', fill='x', expand=False)
        self.hero_frame.pack_propagate(False) 
        self._create_hero_widgets()
        self.hero_frame.bind("<Button-1>", self._on_header_click)

        self.strip_frame = ttk.Frame(self.root, style='Strip.TFrame', height=210)
        self.strip_frame.pack(side='top', fill='x', expand=False)
        self.strip_frame.pack_propagate(False)
        self._create_sequence_strip_widgets()

        self.controls_frame = ttk.Frame(self.root, style='Controls.TFrame', height=150)
        self.controls_frame.pack(side='bottom', fill='both', expand=True)
        self._create_control_widgets()

    def _create_hero_widgets(self):
        top_row = ttk.Frame(self.hero_frame, style='Hero.TFrame')
        top_row.pack(fill='x', pady=(20, 0), padx=30)
        
        self.lbl_temp = ttk.Label(top_row, textvariable=self.current_temp_var, style='HeroTemp.TLabel')
        self.lbl_temp.pack(side='left')
        self.lbl_temp.bind("<Button-1>", self._on_temp_click)
        
        self.lbl_timer = ttk.Label(top_row, textvariable=self.timer_var, style='HeroTimer.TLabel')
        self.lbl_timer.pack(side='right')
        
        info_stack = ttk.Frame(self.hero_frame, style='Hero.TFrame')
        info_stack.pack(side='top', pady=(10, 0))

        self.lbl_status = ttk.Label(info_stack, textvariable=self.status_text_var, style='HeroStatus.TLabel')
        self.lbl_status.pack()
        
        self.lbl_target = ttk.Label(info_stack, textvariable=self.target_text_var, style='HeroTarget.TLabel')
        self.lbl_target.pack()

        self.lbl_addition = ttk.Label(info_stack, textvariable=self.next_addition_var, style='HeroAddition.TLabel')
        self.lbl_addition.pack(pady=(5,0))

    def _create_sequence_strip_widgets(self):
        container = ttk.Frame(self.strip_frame, style='Strip.TFrame')
        container.pack(expand=True, fill='both', padx=20, pady=10)
        
        cols = ("step_num", "name", "temp", "timer", "end_mode")
        self.step_list = ttk.Treeview(container, columns=cols, show='headings', selectmode='browse')
        
        self.step_list.heading("step_num", text="#")
        self.step_list.heading("name", text="Step Name")
        self.step_list.heading("temp", text="Target")
        self.step_list.heading("timer", text="Duration")
        self.step_list.heading("end_mode", text="Next Action") 
        
        self.step_list.column("step_num", width=40, anchor="center")
        self.step_list.column("name", width=220, anchor="w")
        self.step_list.column("temp", width=80, anchor="center")
        self.step_list.column("timer", width=80, anchor="center")
        self.step_list.column("end_mode", width=100, anchor="center") 
        
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.step_list.yview)
        self.step_list.configure(yscrollcommand=scrollbar.set)
        
        self.step_list.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        self.step_list.tag_configure('active_step', background='#2ecc71', foreground='black') 
        self.step_list.tag_configure('pending_step', background='white', foreground='black')
        self.step_list.tag_configure('done_step', background='#7f8c8d', foreground='#bdc3c7')

    def _refresh_step_list(self):
        for item in self.step_list.get_children():
            self.step_list.delete(item)
            
        profile = self.sequencer.current_profile
        self.last_active_iid = None 
        
        if not profile: return

        for i, step in enumerate(profile.steps):
            try:
                d_val = getattr(step, 'duration_min', 0)
                dur_str = f"{d_val}m" if d_val > 0 else "--"
            except: dur_str = "ERR"

            try:
                t_val = getattr(step, 'setpoint_f', None)
                temp_str = f"{float(t_val):.1f}°F" if t_val is not None else "--"
            except: temp_str = "ERR"
                
            try:
                b_str = str(getattr(step, 'timeout_behavior', "")).lower()
                if "auto" in b_str: mode_str = "Auto"
                else: mode_str = "WAIT"
            except: mode_str = "?"

            step_iid = str(i)
            self.step_list.insert(
                "", "end", iid=step_iid, 
                values=(i + 1, step.name, temp_str, dur_str, mode_str),
                tags=('pending_step',),
                open=True 
            )
            
            if hasattr(step, 'additions') and step.additions:
                sorted_additions = sorted(step.additions, key=lambda x: x.time_point_min, reverse=True)
                for j, add in enumerate(sorted_additions):
                    child_iid = f"{step_iid}_add_{j}"
                    add_name = f"  ↳ {add.name}"
                    add_time = f"@ {add.time_point_min}m"
                    self.step_list.insert(
                        step_iid, "end", iid=child_iid,
                        values=("", add_name, "", add_time, "Alert"),
                        tags=('pending_step',)
                    )

    def _create_control_widgets(self):
        btn_profiles = ttk.Button(self.controls_frame, text="PROFILES\nLIBRARY", command=self._on_profiles_click)
        btn_profiles.place(relx=0.05, rely=0.2, relwidth=0.2, relheight=0.6)
        
        self.btn_action = ttk.Button(self.controls_frame, textvariable=self.action_btn_text, style='Action.TButton', command=self._on_action_click)
        self.btn_action.place(relx=0.28, rely=0.15, relwidth=0.44, relheight=0.7)
        
        btn_abort = ttk.Button(self.controls_frame, text="ABORT\nSTOP", style='Stop.TButton', command=self._on_abort_click)
        btn_abort.place(relx=0.75, rely=0.2, relwidth=0.2, relheight=0.6)

    def _on_profiles_click(self):
        if self.library_window and tk.Toplevel.winfo_exists(self.library_window):
            self.library_window.lift()
            return
        self.library_window = ProfileLibraryPopup(self.root, self.settings, self.sequencer)

    def _on_action_click(self):
        status = self.sequencer.status
        if status == SequenceStatus.IDLE:
            if not self.sequencer.current_profile:
                messagebox.showinfo("No Profile", "Please load a profile.")
                return
            self.sequencer.start_sequence()
        elif status == SequenceStatus.RUNNING:
            self.sequencer.pause_sequence()
        elif status == SequenceStatus.PAUSED:
            self.sequencer.resume_sequence()
        elif status == SequenceStatus.WAITING_FOR_USER:
            if self.sequencer.current_alert_text == "Step Complete":
                self.sequencer.advance_step()
            else:
                self.sequencer.resume_sequence()

    def _on_abort_click(self):
        if messagebox.askyesno("Abort Brew?", "Are you sure you want to STOP everything?"):
            self.sequencer.stop()

    def _on_header_click(self, event):
        import time
        now = time.time()
        if now - self.last_click_time > 2.0: self.title_clicks = 0
        self.title_clicks += 1
        self.last_click_time = now
        if self.title_clicks >= 5:
            self.title_clicks = 0
            if not self.hw.is_dev_mode(): self._show_safety_dialog()
            else: self.toggle_dev_tools(True)

    def _show_safety_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("SAFETY INTERLOCK")
        dialog.geometry("400x300")
        dialog.configure(bg="#c0392b")
        dialog.transient(self.root) 
        dialog.wait_visibility()
        dialog.grab_set()
        tk.Label(dialog, text="⚠ WARNING ⚠", font=("Arial", 24, "bold"), bg="#c0392b", fg="white").pack(pady=20)
        tk.Label(dialog, text="ENTERING DEVELOPER MODE", bg="#c0392b", fg="white", font=("Arial", 12)).pack(pady=10)
        self.safety_slider = tk.Scale(dialog, from_=0, to=100, orient="horizontal", length=300, showvalue=0)
        self.safety_slider.pack(pady=10)
        self.safety_slider.bind("<ButtonRelease-1>", lambda e: self._check_slider(dialog))

    def _check_slider(self, dialog_window):
        val = self.safety_slider.get()
        if val >= 100:
            self.hw.set_dev_mode(True)
            style = ttk.Style()
            style.configure('Hero.TFrame', background='#e67e22')
            self.hero_frame.configure(style='Hero.TFrame')
            self.toggle_dev_tools(True)
            dialog_window.destroy()
        else: self.safety_slider.set(0)

    def toggle_dev_tools(self, is_active):
        if not is_active:
            if self.dev_window and tk.Toplevel.winfo_exists(self.dev_window): self.dev_window.destroy()
            self.dev_window = None
            return
        if self.dev_window and tk.Toplevel.winfo_exists(self.dev_window):
            self.dev_window.lift()
            return
        self.dev_window = tk.Toplevel(self.root)
        self.dev_window.title("Dev Tools")
        self.dev_window.geometry("300x220")
        self.dev_window.configure(bg="#333333")
        def _on_close():
            self.dev_window.destroy()
            self.dev_window = None
        self.dev_window.protocol("WM_DELETE_WINDOW", _on_close)
        tk.Label(self.dev_window, text="Temperature Simulator", fg="white", bg="#333333", font=("Arial", 12, "bold")).pack(pady=10)
        def update_sim_temp(val): self.hw.set_virtual_temp(val)
        slider = tk.Scale(self.dev_window, from_=50, to=220, orient="horizontal", bg="#333333", fg="white", highlightthickness=0, command=update_sim_temp)
        current_temp = self.hw.read_temperature()
        slider.set(current_temp)
        slider.pack(fill="x", padx=20)
        btn_skip = tk.Button(self.dev_window, text="⏭ Force Next Step", bg="#e67e22", fg="white", font=("Arial", 10, "bold"), command=self._dev_force_next)
        btn_skip.pack(pady=15, fill="x", padx=20)

    def _dev_force_next(self): self.sequencer.advance_step()

    def _on_temp_click(self, event):
        if self.hw.is_dev_mode(): self.toggle_dev_tools(True)

    def _update_loop(self):
        try:
            if hasattr(self.sequencer, 'update'): self.sequencer.update()
            self.update_ui_from_state()
        except Exception as e:
            print(f"[UI ERROR] Loop crashed: {e}")
            traceback.print_exc()
        self.root.after(250, self._update_loop)

    def update_ui_from_state(self):
        t = self.sequencer.current_temp
        self.current_temp_var.set(f"{t:.1f}°F")
        
        st = self.sequencer.status
        tgt = self.sequencer.get_target_temp()
        
        new_style = 'HeroTemp.TLabel'
        if st in [SequenceStatus.RUNNING, SequenceStatus.WAITING_FOR_USER] and tgt is not None and tgt > 0:
            diff = t - tgt
            if diff < -1.0: new_style = 'HeroTempBlue.TLabel'
            elif diff > 1.0: new_style = 'HeroTempRed.TLabel'
            else: new_style = 'HeroTempGreen.TLabel'
        self.lbl_temp.configure(style=new_style)

        self.timer_var.set(self.sequencer.get_display_timer())
        self.status_text_var.set(self.sequencer.get_status_message())
        self.next_addition_var.set(self.sequencer.get_upcoming_additions())

        if tgt: self.target_text_var.set(f"Target: {tgt:.1f}°F")
        else: self.target_text_var.set("")

        current_idx = self.sequencer.current_step_index
        profile = self.sequencer.current_profile
        
        current_pid = profile.id if profile else None
        if current_pid != self.last_profile_id:
             self._refresh_step_list()
             self.last_profile_id = current_pid

        if profile and current_idx is not None and 0 <= current_idx < len(profile.steps):
            
            step = profile.steps[current_idx]
            step_iid = str(current_idx)
            
            active_cursor_iid = step_iid
            
            is_waiting = (self.sequencer.status == SequenceStatus.WAITING_FOR_USER)
            alert_text = self.sequencer.current_alert_text

            if hasattr(step, 'additions') and step.additions:
                children = self.step_list.get_children(step_iid)
                sorted_adds = sorted(step.additions, key=lambda x: x.time_point_min, reverse=True)
                for j, child_iid in enumerate(children):
                    if j < len(sorted_adds):
                        add_obj = sorted_adds[j]
                        if is_waiting and alert_text and (add_obj.name in alert_text):
                            active_cursor_iid = child_iid
                            break

            cursor_reached = False
            
            # --- RENDER LOOP WITH CHILD STATE LOGIC ---
            for parent_iid in self.step_list.get_children():
                # --- PROCESS PARENT ---
                if parent_iid == active_cursor_iid:
                    # Parent is active
                    self.step_list.item(parent_iid, tags=('active_step',))
                    self.step_list.selection_set(parent_iid)
                    cursor_reached = True
                    
                    # --- PROCESS CHILDREN INSIDE ACTIVE PARENT ---
                    # Here we check if individual alerts are Done/Active/Pending
                    if hasattr(step, 'additions') and step.additions:
                        children = self.step_list.get_children(parent_iid)
                        sorted_adds = sorted(step.additions, key=lambda x: x.time_point_min, reverse=True)
                        
                        for j, child_iid in enumerate(children):
                            if j < len(sorted_adds):
                                add_obj = sorted_adds[j]
                                
                                if child_iid == active_cursor_iid:
                                    # This specific alert is blocking right now
                                    self.step_list.item(child_iid, tags=('active_step',))
                                    self.step_list.selection_set(child_iid)
                                elif add_obj.triggered:
                                    # Already happened -> Gray
                                    self.step_list.item(child_iid, tags=('done_step',))
                                else:
                                    # Future -> White
                                    self.step_list.item(child_iid, tags=('pending_step',))
                    
                elif not cursor_reached:
                    # Parent is Past -> Gray
                    self.step_list.item(parent_iid, tags=('done_step',))
                    # All children Past -> Gray
                    for child in self.step_list.get_children(parent_iid):
                        self.step_list.item(child, tags=('done_step',))
                else:
                    # Parent is Future -> White
                    self.step_list.item(parent_iid, tags=('pending_step',))
                    # All children Future -> White
                    for child in self.step_list.get_children(parent_iid):
                        self.step_list.item(child, tags=('pending_step',))

            # Scroll only on change
            if active_cursor_iid != self.last_active_iid:
                self.step_list.see(active_cursor_iid)
                self.last_active_iid = active_cursor_iid

        st = self.sequencer.status
        self.btn_action.state(['!disabled']) 
        self.btn_action.configure(style='Action.TButton') 

        if st == SequenceStatus.IDLE:
            self.action_btn_text.set("START BREW")
        elif st == SequenceStatus.RUNNING:
            self.action_btn_text.set("PAUSE")
        elif st == SequenceStatus.PAUSED:
            self.action_btn_text.set("RESUME")
        elif st == SequenceStatus.WAITING_FOR_USER:
            alert_txt = self.sequencer.current_alert_text
            if alert_txt and alert_txt != "Step Complete":
                self.action_btn_text.set(f"ACKNOWLEDGE: {alert_txt}")
            else:
                self.action_btn_text.set("STEP DONE - NEXT ⏭")
            self.btn_action.configure(style='Advance.TButton')
        elif st == SequenceStatus.COMPLETED:
            self.action_btn_text.set("COMPLETE")
            self.btn_action.state(['disabled'])

class ProfileLibraryPopup(tk.Toplevel):
    def __init__(self, parent, settings_manager, sequencer):
        super().__init__(parent)
        self.title("Profile Library")
        self.geometry("600x400")
        self.transient(parent)
        self.settings = settings_manager
        self.sequencer = sequencer
        
        self.editor_window = None
        
        self._layout()
        self._refresh_list()
        self.protocol("WM_DELETE_WINDOW", self.close) 
        self.grab_set() 
        self.focus_set() 
        self.wait_visibility() 

    def close(self):
        try:
            self.grab_release()
        except:
            pass
        finally:
            if self.master: self.master.focus_set()
            self.destroy()

    def _layout(self):
        toolbar = ttk.Frame(self, padding=5)
        toolbar.pack(fill='x', side='bottom')
        
        ttk.Button(toolbar, text="Load Profile", command=self._load_selected).pack(side='right', padx=5)
        ttk.Button(toolbar, text="Edit", command=self._edit_selected).pack(side='right', padx=5)
        ttk.Button(toolbar, text="Delete", command=self._delete_selected).pack(side='right', padx=5)
        ttk.Button(toolbar, text="+ New Profile", command=self._create_new).pack(side='left', padx=5)
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
            self.close()

    def _edit_selected(self):
        if self.editor_window:
            try:
                if self.editor_window.winfo_exists():
                    self.editor_window.lift()
                    return
                else:
                    self.editor_window = None
            except:
                self.editor_window = None

        pid = self._get_selected_id()
        if not pid: return
        profile = self.settings.get_profile_by_id(pid)
        if profile:
            self.editor_window = ProfileEditor(self, profile, on_save_callback=self._on_editor_save)

    def _create_new(self):
        if self.editor_window:
            try:
                if self.editor_window.winfo_exists():
                    self.editor_window.lift()
                    return
                else:
                    self.editor_window = None
            except:
                self.editor_window = None
            
        new_p = BrewProfile(name="New Profile")
        self.editor_window = ProfileEditor(self, new_p, on_save_callback=self._on_editor_save)

    def _delete_selected(self):
        pid = self._get_selected_id()
        if not pid: return
        if messagebox.askyesno("Confirm", "Delete this profile?"):
            self.settings.delete_profile(pid)
            self._refresh_list()

    def _on_editor_save(self, profile):
        self.settings.save_profile(profile)
        self._refresh_list()
