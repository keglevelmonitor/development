"""
brewbrain app
profile_editor.py
"""

import tkinter as tk
from tkinter import ttk, messagebox
from profile_data import BrewProfile, BrewStep, StepType, TimeoutBehavior

class ProfileEditor(tk.Toplevel):
    
    def __init__(self, parent, profile: BrewProfile, on_save_callback):
        super().__init__(parent)
        self.title(f"Editing Profile")
        self.geometry("900x650")
        self.transient(parent)
        
        self.profile = profile
        self.on_save = on_save_callback
        self.steps_working_copy = list(profile.steps) 
        
        self._configure_styles()
        self._create_layout()
        self._refresh_step_list()
        
        # --- ROBUST WINDOW MANAGEMENT ---
        self.protocol("WM_DELETE_WINDOW", self.close) # Handle "X" button
        self.grab_set() # Take control
        self.focus_set() # Take keyboard focus
        self.wait_visibility() # Ensure window is drawn before grabbing

    def close(self):
        """Safely releases grab and returns focus to parent before closing."""
        self.grab_release()
        if self.master:
            self.master.focus_set() # Give focus back to the Library Popup
        self.destroy()

    def _configure_styles(self):
        s = ttk.Style()
        s.configure('Editor.TFrame', background='#f0f0f0')
        s.configure('StepList.TFrame', background='white', relief='sunken')
        s.configure('Header.TLabel', font=('Arial', 12, 'bold'))
        s.configure('SubHeader.TLabel', font=('Arial', 10, 'bold'), foreground='#555555')

    def _create_layout(self):
        # MAIN CONTAINER
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill='both', expand=True)
        
        # --- TOP: PROFILE NAME ---
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill='x', pady=(0, 15))
        
        ttk.Label(top_frame, text="Profile Name:", style='Header.TLabel').pack(side='left')
        
        self.var_profile_name = tk.StringVar(value=self.profile.name)
        ent_name = ttk.Entry(top_frame, textvariable=self.var_profile_name, font=('Arial', 12))
        ent_name.pack(side='left', fill='x', expand=True, padx=10)
        
        # --- SPLIT PANE ---
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill='both', expand=True)

        # --- LEFT: LIST ---
        left_pane = ttk.Frame(content_frame, width=300)
        left_pane.pack(side='left', fill='both', padx=(0, 10), expand=False)
        
        ttk.Label(left_pane, text="Sequence", style='SubHeader.TLabel').pack(anchor='w', pady=(0, 5))
        
        list_container = ttk.Frame(left_pane)
        list_container.pack(fill='both', expand=True)
        
        self.step_listbox = tk.Listbox(list_container, font=('Arial', 11), selectmode=tk.SINGLE, activator=None, height=15)
        self.step_listbox.pack(side='left', fill='both', expand=True)
        self.step_listbox.bind('<<ListboxSelect>>', self._on_step_select)
        
        scroll = ttk.Scrollbar(list_container, orient='vertical', command=self.step_listbox.yview)
        scroll.pack(side='right', fill='y')
        self.step_listbox.config(yscrollcommand=scroll.set)
        
        btn_row = ttk.Frame(left_pane)
        btn_row.pack(fill='x', pady=5)
        ttk.Button(btn_row, text="+ Add", command=self._add_step).pack(side='left', expand=True, fill='x')
        ttk.Button(btn_row, text="- Del", command=self._delete_step).pack(side='left', expand=True, fill='x')
        ttk.Button(btn_row, text="▲", width=3, command=self._move_up).pack(side='left', padx=2)
        ttk.Button(btn_row, text="▼", width=3, command=self._move_down).pack(side='left', padx=2)

        # --- RIGHT: DETAILS ---
        self.right_pane = ttk.LabelFrame(content_frame, text="Selected Step Details", padding=15)
        self.right_pane.pack(side='right', fill='both', expand=True)
        
        self._init_form_vars()
        self._build_form_widgets()
        
        # --- BOTTOM ---
        bot_frame = ttk.Frame(self)
        bot_frame.pack(fill='x', padx=15, pady=15)
        
        # Use self.close for Cancel
        ttk.Button(bot_frame, text="Cancel", command=self.close).pack(side='right', padx=5)
        ttk.Button(bot_frame, text="Save Profile", command=self._save_and_close).pack(side='right', padx=5)

    def _init_form_vars(self):
        self.var_name = tk.StringVar()
        self.var_type = tk.StringVar()
        self.var_temp = tk.StringVar()
        self.var_duration = tk.StringVar()
        self.var_power = tk.StringVar()
        self.var_volume = tk.StringVar()
        self.var_note = tk.StringVar()
        self.var_timeout = tk.StringVar()
        
        self.var_type.trace_add('write', self._on_type_change)

    def _build_form_widgets(self):
        f = self.right_pane
        row = 0
        def add_row(label, widget, height=1):
            nonlocal row
            ttk.Label(f, text=label).grid(row=row, column=0, sticky='ne', pady=8, padx=(0, 10))
            widget.grid(row=row, column=1, sticky='ew', pady=5, ipady=(4 if height>1 else 0))
            row += 1

        add_row("Step Name:", ttk.Entry(f, textvariable=self.var_name))
        
        type_opts = [e.value for e in StepType]
        self.cb_type = ttk.Combobox(f, textvariable=self.var_type, values=type_opts, state='readonly')
        add_row("Action Type:", self.cb_type)
        
        self.ent_temp = ttk.Entry(f, textvariable=self.var_temp)
        self.lbl_temp = ttk.Label(f, text="Setpoint (°F):") 
        self.lbl_temp.grid(row=row, column=0, sticky='e', pady=8, padx=(0, 10))
        self.ent_temp.grid(row=row, column=1, sticky='ew', pady=5)
        row += 1
        
        self.ent_dur = ttk.Entry(f, textvariable=self.var_duration)
        self.lbl_dur = ttk.Label(f, text="Duration (min):")
        self.lbl_dur.grid(row=row, column=0, sticky='e', pady=8, padx=(0, 10))
        self.ent_dur.grid(row=row, column=1, sticky='ew', pady=5)
        row += 1
        
        self.ent_pwr = ttk.Entry(f, textvariable=self.var_power)
        self.lbl_pwr = ttk.Label(f, text="Power (Watts):")
        self.lbl_pwr.grid(row=row, column=0, sticky='e', pady=8, padx=(0, 10))
        self.ent_pwr.grid(row=row, column=1, sticky='ew', pady=5)
        row += 1
        
        self.ent_vol = ttk.Entry(f, textvariable=self.var_volume)
        self.lbl_vol = ttk.Label(f, text="Volume (L):")
        self.lbl_vol.grid(row=row, column=0, sticky='e', pady=8, padx=(0, 10))
        self.ent_vol.grid(row=row, column=1, sticky='ew', pady=5)
        row += 1
        
        to_opts = [e.value for e in TimeoutBehavior]
        self.cb_to = ttk.Combobox(f, textvariable=self.var_timeout, values=to_opts, state='readonly')
        add_row("At Timeout:", self.cb_to)
        
        self.txt_note = tk.Text(f, height=4, width=30, font=('Arial', 10))
        add_row("Notes:", self.txt_note, height=4)
        
        ttk.Button(f, text="Apply Changes to Selected Step", command=self._commit_form_to_step).grid(row=row, column=1, sticky='e', pady=15)

        f.columnconfigure(1, weight=1)
        self._toggle_form_state(False)

    def _refresh_step_list(self):
        self.step_listbox.delete(0, tk.END)
        for i, step in enumerate(self.steps_working_copy):
            desc = f"{i+1}. {step.name} [{step.step_type.value}]"
            self.step_listbox.insert(tk.END, desc)

    def _on_step_select(self, event):
        sel = self.step_listbox.curselection()
        if not sel: return
        
        index = sel[0]
        step = self.steps_working_copy[index]
        self.current_step_index = index 
        
        self.var_name.set(step.name)
        self.var_type.set(step.step_type.value)
        
        temp_display = step.lauter_temp_f if step.step_type == StepType.LAUTER else step.setpoint_f
        self.var_temp.set(str(temp_display) if temp_display is not None else "")
        
        self.var_duration.set(str(step.duration_min) if step.duration_min else (step.target_completion_time or ""))
        self.var_power.set(str(step.power_watts) if step.power_watts is not None else "")
        self.var_volume.set(str(step.lauter_volume) if step.lauter_volume is not None else "")
        self.var_timeout.set(step.timeout_behavior.value)
        
        self.txt_note.delete('1.0', tk.END)
        self.txt_note.insert('1.0', step.note)
        
        self._toggle_form_state(True)

    def _on_type_change(self, *args):
        t_val = self.var_type.get()
        try:
            t = StepType(t_val)
        except:
            return

        # Defaults
        self._set_state(self.ent_temp, True)
        self._set_state(self.ent_dur, True)
        self._set_state(self.ent_pwr, True)
        self._set_state(self.ent_vol, False) 
        self.lbl_dur.config(text="Duration (min):")
        self.lbl_pwr.config(text="Power (Watts):")

        if t == StepType.DELAYED_START:
            self.lbl_dur.config(text="Ready By (YYYY-MM-DD HH:MM):")
            self._set_state(self.ent_vol, False)

        elif t == StepType.BOIL:
            self._set_state(self.ent_temp, False)
            self.var_temp.set("")
            self.lbl_pwr.config(text="Duty Cycle (%):")

        elif t == StepType.LAUTER:
            self._set_state(self.ent_dur, False)
            self._set_state(self.ent_pwr, False)
            self._set_state(self.ent_vol, True)
            self.var_duration.set("0")
            self.var_power.set("")

        elif t == StepType.SG_READING:
            self._set_state(self.ent_temp, False)
            self._set_state(self.ent_dur, False)
            self._set_state(self.ent_pwr, False)
            self._set_state(self.ent_vol, False)
            self.var_temp.set("")
            self.var_duration.set("0")
            self.var_power.set("")

        elif t == StepType.HOPS_ADJUNCTS:
            self._set_state(self.ent_temp, False)
            self._set_state(self.ent_pwr, False)
            self.var_temp.set("")
            self.var_power.set("")

    def _set_state(self, widget, enabled):
        state = '!disabled' if enabled else 'disabled'
        widget.state([state])

    def _commit_form_to_step(self):
        if not hasattr(self, 'current_step_index'): return
        
        step = self.steps_working_copy[self.current_step_index]
        
        try:
            step.name = self.var_name.get()
            step.step_type = StepType(self.var_type.get())
            step.timeout_behavior = TimeoutBehavior(self.var_timeout.get())
            step.note = self.txt_note.get("1.0", tk.END).strip()
            
            t_val = self.var_temp.get()
            temp_float = float(t_val) if t_val else None
            
            if step.step_type == StepType.LAUTER:
                step.lauter_temp_f = temp_float
                step.setpoint_f = None
            else:
                step.setpoint_f = temp_float
                step.lauter_temp_f = None
            
            p_val = self.var_power.get()
            step.power_watts = int(p_val) if p_val else None
            
            v_val = self.var_volume.get()
            step.lauter_volume = float(v_val) if v_val else None
            
            d_val = self.var_duration.get()
            if step.step_type == StepType.DELAYED_START:
                 step.target_completion_time = d_val 
                 step.duration_min = 0.0
            else:
                 step.duration_min = float(d_val) if d_val else 0.0
                 step.target_completion_time = None
            
            self._refresh_step_list()
            messagebox.showinfo("Success", "Step updated.")
            
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid input: {e}")

    def _add_step(self):
        new_step = BrewStep(name="New Step")
        self.steps_working_copy.append(new_step)
        self._refresh_step_list()
        idx = len(self.steps_working_copy) - 1
        self.step_listbox.selection_clear(0, tk.END)
        self.step_listbox.selection_set(idx)
        self.step_listbox.event_generate("<<ListboxSelect>>")

    def _delete_step(self):
        sel = self.step_listbox.curselection()
        if not sel: return
        self.steps_working_copy.pop(sel[0])
        self._refresh_step_list()
        self._toggle_form_state(False)

    def _move_up(self):
        sel = self.step_listbox.curselection()
        if not sel or sel[0] == 0: return
        i = sel[0]
        self.steps_working_copy[i], self.steps_working_copy[i-1] = self.steps_working_copy[i-1], self.steps_working_copy[i]
        self._refresh_step_list()
        self.step_listbox.selection_set(i-1)

    def _move_down(self):
        sel = self.step_listbox.curselection()
        if not sel or sel[0] == len(self.steps_working_copy)-1: return
        i = sel[0]
        self.steps_working_copy[i], self.steps_working_copy[i+1] = self.steps_working_copy[i+1], self.steps_working_copy[i]
        self._refresh_step_list()
        self.step_listbox.selection_set(i+1)

    def _toggle_form_state(self, enabled):
        state = '!disabled' if enabled else 'disabled'
        for child in self.right_pane.winfo_children():
            try:
                child.state([state])
            except:
                pass 

    def _save_and_close(self):
        self.profile.name = self.var_profile_name.get()
        self.profile.steps = self.steps_working_copy
        if self.on_save:
            self.on_save(self.profile)
        # Use close() instead of destroy() to ensure grab release
        self.close()
