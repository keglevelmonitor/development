"""
brewbrain app
profile_editor.py
"""

import tkinter as tk
from tkinter import ttk, messagebox
import copy
from profile_data import BrewProfile, BrewStep, StepType, TimeoutBehavior, BrewAddition

class AdditionsDialog(tk.Toplevel):
    """
    Sub-dialog to manage additions/alerts for a single step.
    """
    def __init__(self, parent, step_name, additions_list):
        super().__init__(parent)
        self.title(f"Alerts for: {step_name}")
        self.geometry("400x300")
        self.transient(parent)
        
        self.additions = additions_list # Reference to mutable list
        
        self._layout()
        self._refresh()
        
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.grab_set()
        self.focus_set()
        self.wait_visibility()

    def close(self):
        self.grab_release()
        self.destroy()

    def _layout(self):
        # List
        list_frame = ttk.Frame(self, padding=10)
        list_frame.pack(fill='both', expand=True)
        
        self.lb_additions = tk.Listbox(list_frame, height=8)
        self.lb_additions.pack(side='left', fill='both', expand=True)
        
        sb = ttk.Scrollbar(list_frame, orient='vertical', command=self.lb_additions.yview)
        sb.pack(side='right', fill='y')
        self.lb_additions.config(yscrollcommand=sb.set)
        
        # Inputs
        input_frame = ttk.Frame(self, padding=10)
        input_frame.pack(fill='x')
        
        ttk.Label(input_frame, text="Name:").grid(row=0, column=0, sticky='w')
        self.var_name = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.var_name).grid(row=0, column=1, sticky='ew', padx=5)
        
        ttk.Label(input_frame, text="Min Remaining:").grid(row=1, column=0, sticky='w')
        self.var_time = tk.StringVar()
        ttk.Entry(input_frame, textvariable=self.var_time, width=5).grid(row=1, column=1, sticky='w', padx=5)
        
        input_frame.columnconfigure(1, weight=1)
        
        # Buttons
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill='x')
        
        ttk.Button(btn_frame, text="Add", command=self._add).pack(side='left')
        ttk.Button(btn_frame, text="Remove Selected", command=self._remove).pack(side='right')

    def _refresh(self):
        self.lb_additions.delete(0, tk.END)
        # Sort by time descending
        self.additions.sort(key=lambda x: x.time_point_min, reverse=True)
        
        for add in self.additions:
            self.lb_additions.insert(tk.END, f"{add.time_point_min}m: {add.name}")

    def _add(self):
        name = self.var_name.get().strip()
        t_str = self.var_time.get().strip()
        
        if not name or not t_str: return
        
        try:
            t_val = int(t_str)
            new_add = BrewAddition(name=name, time_point_min=t_val)
            self.additions.append(new_add)
            self._refresh()
            self.var_name.set("")
            self.var_time.set("")
        except ValueError:
            messagebox.showerror("Error", "Time must be an integer.", parent=self)

    def _remove(self):
        sel = self.lb_additions.curselection()
        if not sel: return
        self.additions.pop(sel[0])
        self._refresh()


class ProfileEditor(tk.Toplevel):
    
    def __init__(self, parent, profile: BrewProfile, on_save_callback):
        super().__init__(parent)
        self.title(f"Editing Profile")
        self.geometry("900x700")
        self.transient(parent)
        
        self.profile = profile
        self.on_save = on_save_callback
        
        # Deep copy steps so we can Cancel without side effects
        self.steps_working_copy = copy.deepcopy(profile.steps) 
        self.current_step_index = None 
        
        self._configure_styles()
        self._create_layout()
        self._refresh_step_list()
        
        # Select first item if exists
        if self.steps_working_copy:
            self.step_listbox.selection_set(0)
            self._on_step_select(None)
        
        # --- ROBUST WINDOW MANAGEMENT ---
        self.protocol("WM_DELETE_WINDOW", self.close) 
        self.grab_set() 
        self.focus_set() 
        self.wait_visibility() 

    def close(self):
        """Safely releases grab and checks for unsaved changes."""
        # 1. Save current step edit if possible
        if self.current_step_index is not None:
             self._save_current_edit()

        # 2. Check for Dirty State (Compare to original)
        if self.steps_working_copy != self.profile.steps:
            if not messagebox.askyesno("Unsaved Changes", 
                                       "You have made changes. Discard them?", 
                                       parent=self):
                return # User cancelled the close

        self.grab_release()
        if self.master:
            self.master.focus_set() 
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
        
        # Cancel / Save
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
        
        # --- NEW: ADDITIONS BUTTON ---
        self.btn_additions = ttk.Button(f, text="Manage Alerts / Additions...", command=self._open_additions)
        self.btn_additions.grid(row=row, column=1, sticky='ew', pady=10)
        row += 1
        
        self.txt_note = tk.Text(f, height=4, width=30, font=('Arial', 10))
        add_row("Notes:", self.txt_note, height=4)
        
        # NO APPLY BUTTON - AUTO SAVE LOGIC USED

        f.columnconfigure(1, weight=1)
        self._toggle_form_state(False)

    def _refresh_step_list(self):
        self.step_listbox.delete(0, tk.END)
        for i, step in enumerate(self.steps_working_copy):
            desc = f"{i+1}. {step.name} [{step.step_type.value}]"
            self.step_listbox.insert(tk.END, desc)

    def _save_current_edit(self):
        """Saves form data to the currently selected step object. Returns True if valid."""
        if self.current_step_index is None: return True
        if not (0 <= self.current_step_index < len(self.steps_working_copy)): return True
        
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
                 
            return True
            
        except ValueError as e:
            messagebox.showerror("Validation Error", f"Invalid input: {e}", parent=self)
            return False

    def _on_step_select(self, event):
        # 1. Save Previous Step
        if not self._save_current_edit():
            # If validation failed, REVERT selection to old index
            if self.current_step_index is not None:
                self.step_listbox.selection_clear(0, tk.END)
                self.step_listbox.selection_set(self.current_step_index)
            return

        # 2. Load New Step
        sel = self.step_listbox.curselection()
        if not sel: return
        
        index = sel[0]
        step = self.steps_working_copy[index]
        self.current_step_index = index 
        
        # Populate Form
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

    def _open_additions(self):
        # Ensure current step data is saved to memory first
        self._save_current_edit()
        
        if self.current_step_index is None: return
        step = self.steps_working_copy[self.current_step_index]
        AdditionsDialog(self, step.name, step.additions)

    def _on_type_change(self, *args):
        t_val = self.var_type.get()
        try:
            t = StepType(t_val)
        except:
            return

        self._set_state(self.ent_temp, True)
        self._set_state(self.ent_dur, True)
        self._set_state(self.ent_pwr, True)
        self._set_state(self.ent_vol, False) 
        self.lbl_dur.config(text="Duration (min):")
        self.lbl_pwr.config(text="Power (Watts):")
        self._set_state(self.btn_additions, True)

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

    def _add_step(self):
        self._save_current_edit()
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
        self.current_step_index = None 
        self._refresh_step_list()
        self._toggle_form_state(False)
        
        # Select previous if available
        if self.steps_working_copy:
            new_idx = max(0, sel[0]-1)
            self.step_listbox.selection_set(new_idx)
            self.step_listbox.event_generate("<<ListboxSelect>>")

    def _move_up(self):
        self._save_current_edit()
        sel = self.step_listbox.curselection()
        if not sel or sel[0] == 0: return
        i = sel[0]
        self.steps_working_copy[i], self.steps_working_copy[i-1] = self.steps_working_copy[i-1], self.steps_working_copy[i]
        self._refresh_step_list()
        self.step_listbox.selection_set(i-1)
        self.step_listbox.event_generate("<<ListboxSelect>>")

    def _move_down(self):
        self._save_current_edit()
        sel = self.step_listbox.curselection()
        if not sel or sel[0] == len(self.steps_working_copy)-1: return
        i = sel[0]
        self.steps_working_copy[i], self.steps_working_copy[i+1] = self.steps_working_copy[i+1], self.steps_working_copy[i]
        self._refresh_step_list()
        self.step_listbox.selection_set(i+1)
        self.step_listbox.event_generate("<<ListboxSelect>>")

    def _toggle_form_state(self, enabled):
        state = '!disabled' if enabled else 'disabled'
        for child in self.right_pane.winfo_children():
            try: child.state([state])
            except: pass 

    def _save_and_close(self):
        if not self._save_current_edit(): return
        
        self.profile.name = self.var_profile_name.get()
        self.profile.steps = self.steps_working_copy
        if self.on_save:
            self.on_save(self.profile)
        
        self.grab_release()
        if self.master: self.master.focus_set()
        self.destroy()
