# keglevel app
#
# process_flow.py
import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
import uuid
import math
import sys
import subprocess 

# --- NEW: Import platform flag from sensor_logic ---
from sensor_logic import IS_RASPBERRY_PI_MODE
# ---------------------------------------------------

# We define this mock to ensure the code runs successfully when executed directly, 
# as SettingsManager is complex. The real SettingsManager object is injected when run via main.
# FIX: Removing mock as requested, relying on successful import.
from settings_manager import SettingsManager

class InventoryManager:
    # To run standalone, we need base_dir passed to find config files reliably.
    def __init__(self, settings_manager, base_dir):
        self.settings_manager = settings_manager
        
        # --- CRITICAL PATH FIX: Get the file paths directly from the SettingsManager ---
        # --- REFACTOR: Use get_data_dir() to find the data folder ---
        data_dir = self.settings_manager.get_data_dir()

        self.settings_file_path = os.path.join(data_dir, "settings.json") # This line is technically redundant but harmless
        self.beverages_file_path = os.path.join(data_dir, "beverages_library.json")
        self.workflow_file_path = os.path.join(data_dir, "process_flow.json")
        # --- END REFACTOR ---
        
        # Load the library directly from the passed SettingsManager instance
        # --- MODIFIED: Call the new method to load from the passed settings manager ---
        # Storing the list as self.beverage_library (list) for use by ProcessFlowApp
        self.beverage_library, self.beverage_map = self._load_beverage_library_from_settings()
        
        self.columns = self._get_default_workflow_data()['columns']
        self._load_workflow_data()
        
    def refresh_beverages(self):
        """
        Lightweight refresh: Reloads only the beverage library from memory.
        Does NOT reload workflow data from disk.
        """
        self.beverage_library, self.beverage_map = self._load_beverage_library_from_settings()    
        
    def _load_beverage_library_from_settings(self):
        """Loads the beverage library from the SettingsManager instance."""
        # Use the settings manager passed during initialization, which holds the current data.
        library = self.settings_manager.get_beverage_library() 
        
        beverage_list = library.get('beverages', [])
        beverage_map = {b['id']: b for b in beverage_list if 'id' in b}
        return beverage_list, beverage_map
        
    def _get_default_workflow_data(self):
        return {
            "columns": {
                # These keys represent the saved data structure and are loaded from workflow.json
                "lagering_or_finishing": [],
                "fermenting": [],
                "on_deck": [],
                "on_rotation": []
            }
        }

    def _load_workflow_data(self):
        """Loads workflow data from JSON, or creates/validates defaults."""
        defaults = self._get_default_workflow_data()
        data_loaded_from_file = False
        
        # --- MODIFIED: Reference process_flow.json ---
        if os.path.exists(self.workflow_file_path):
            try:
                with open(self.workflow_file_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data.get('columns'), dict):
                        # Filter to include only the new valid keys
                        valid_columns = {k: v for k, v in data['columns'].items() if k in defaults['columns']}
                        self.columns = valid_columns
                        data_loaded_from_file = True
                        print("WorkflowManager: Workflow data loaded successfully.")
            except Exception as e:
                print(f"WorkflowManager: Error loading/decoding process_flow JSON: {e}. Reverting to in-memory defaults.")
        # -----------------------------------------------
        
        for key in defaults['columns']:
            if key not in self.columns or not isinstance(self.columns[key], list):
                self.columns[key] = defaults['columns'][key]
        
        self._prune_and_validate_data()
        
        if not data_loaded_from_file:
            self._save_workflow_data()
            print("WorkflowManager: Workflow data initialized with defaults.")
        
    def _prune_and_validate_data(self):
        """Removes IDs that no longer exist in the beverage library."""
        valid_ids = set(self.beverage_map.keys())

        for col_name, id_list in self.columns.items():
            self.columns[col_name] = [
                b_id for b_id in id_list if b_id in valid_ids
            ]

    def reset_to_library_defaults(self):
        # NOTE: This method is kept for backwards compatibility with old save files but is no longer used by the UI.
        """Forces the workflow data to reset to empty lists."""
        self.columns = self._get_default_workflow_data()['columns']
        self._save_workflow_data()
        print("WorkflowManager: Data forcefully reset and saved to empty lists.")

    def _save_workflow_data(self):
        """Saves the current workflow state to JSON."""
        try:
            data_to_save = {"columns": self.columns}
            with open(self.workflow_file_path, 'w') as f:
                json.dump(data_to_save, f, indent=4)
            print("WorkflowManager: Workflow data saved.")
        except Exception as e:
            print(f"WorkflowManager Error: Could not save data: {e}")
            
    def get_beverage_data(self, beverage_id):
        """Returns beverage metadata for a given ID."""
        # MODIFIED: Default values are set to ensure they are empty/None for the UI logic to use "--"
        return self.beverage_map.get(beverage_id, {"name": "UNKNOWN", "bjcp": "", "abv": "", "ibu": None})
        
    def move_item(self, col_name, item_id, direction):
        """Moves an item up/down within a column."""
        if col_name not in self.columns: return
        try:
            current_list = self.columns[col_name]
            old_index = current_list.index(item_id)
            new_index = old_index + direction
            
            if 0 <= new_index < len(current_list):
                current_list.insert(new_index, current_list.pop(old_index))
                self._save_workflow_data()
                return True
        except ValueError:
            print(f"WorkflowManager Error: Item {item_id} not found in {col_name}.")
        return False

    def add_item_to_column(self, item_id, target_col):
        """Adds an item to an inventory column (duplicates allowed)."""
        if target_col not in self.columns: return False
        
        self.columns[target_col].insert(0, item_id) # Add to the top
        self._save_workflow_data()
        return True

    def remove_item_from_column(self, item_id, col_name):
        """Removes an item from a column (only one instance if duplicates exist)."""
        if col_name not in self.columns: return False

        try:
            current_list = self.columns[col_name]
            current_list.remove(item_id)
            self._save_workflow_data()
            return True
        except ValueError:
            print(f"WorkflowManager Error: Item {item_id} not found in {col_name} for removal.")
            return False

# --- UI Application Class ---
# --- MODIFIED: Renamed to ProcessFlowApp ---
class ProcessFlowApp:
    # UPDATED COLUMN ORDER for left-to-right display: On Rotation -> On Deck -> Fermenting -> Lagering
    INVENTORY_COLUMNS = ["on_rotation", "on_deck", "fermenting", "lagering_or_finishing"]
    
    # MODIFIED: __init__ now accepts a Tkinter root object (a Toplevel from UIManager).
    def __init__(self, root_window, settings_manager, base_dir, parent_root=None):
        self.parent_root = parent_root
        self.settings_manager = settings_manager
        self.base_dir = base_dir 
        
        self.view_mode = self.settings_manager.get_workflow_view_mode() 
        
        self.manager = InventoryManager(settings_manager, self.base_dir) 
        
        self.all_beverages = self.manager.beverage_library
        self.beverage_names = sorted([b.get('name', 'Untitled') for b in self.all_beverages if b.get('id')])
        self.beverage_names.insert(0, "-- Add Beverage --")
        self.name_to_id_map = {b['name']: b['id'] for b in self.all_beverages if 'id' in b and 'name' in b}
        
        self.column_combobox_vars = {col: tk.StringVar(value="-- Add Beverage --") for col in self.INVENTORY_COLUMNS}
        
        self.popup = root_window
        self.popup.title("KegLevel Workflow")
        
        # --- NEW: Restore Saved Geometry ---
        saved_geo = self.settings_manager.get_workflow_window_geometry()
        if saved_geo:
            try:
                self.popup.geometry(saved_geo)
            except Exception:
                pass # Ignore invalid geometry
        # -----------------------------------

        # --- NEW: Bind Close Event to Save Geometry ---
        self.popup.protocol("WM_DELETE_WINDOW", self._on_close)
        # ----------------------------------------------
        
        self._apply_window_jiggle_fix()
        
        self.column_names = self.INVENTORY_COLUMNS
        self.display_titles = {
            "lagering_or_finishing": "Lagering or Finishing (kegged)", 
            "fermenting": "Fermenting", 
            "on_deck": "On Deck", 
            "on_rotation": "On Rotation"
        }
        
        self._setup_styles() 
        self._create_widgets()

    # --- NEW: Helper to save geometry independently ---
    def save_geometry(self):
        """Saves the current window geometry to settings if the window is active."""
        if not self.popup: return
        try:
            if self.popup.winfo_exists():
                current_geo = self.popup.geometry()
                self.settings_manager.save_workflow_window_geometry(current_geo)
        except Exception as e:
            print(f"WorkflowApp Warning: Could not save geometry: {e}")

    # MODIFIED: _on_close uses the helper
    def _on_close(self):
        """Saves the current window geometry and closes the window."""
        self.save_geometry()
        # Proceed with closing
        self.popup.destroy()

    def _apply_window_jiggle_fix(self):
        """
        Applies the 'jiggle' fix to force the window manager to recognize resizing handles.
        Moves the window 1px and back after mapping.
        """
        # 1. Disable resizing initially to ensure state change triggers update
        self.popup.resizable(False, False)
        
        def jiggle_window(event):
            if event.widget != self.popup: return
            self.popup.unbind("<Map>")
            
            # Enable resizing now that window is visible
            self.popup.resizable(True, True)
            
            def _step_1_move():
                try:
                    # Use winfo_x/y for accurate content coordinates
                    x = self.popup.winfo_x()
                    y = self.popup.winfo_y()
                    w = self.popup.winfo_width()
                    h = self.popup.winfo_height()
                    
                    # Store original for restore
                    self._jiggle_restore_x = x
                    self._jiggle_restore_y = y
                    
                    # Move 1px right
                    self.popup.geometry(f"{w}x{h}+{x+1}+{y}")
                    
                    # Schedule Step 2
                    self.popup.after(100, _step_2_restore)
                except Exception as e:
                    print(f"Workflow Warning: Jiggle Step 1 failed: {e}")

            def _step_2_restore():
                try:
                    # Restore original position
                    x = self._jiggle_restore_x
                    y = self._jiggle_restore_y
                    w = self.popup.winfo_width()
                    h = self.popup.winfo_height()
                    self.popup.geometry(f"{w}x{h}+{x}+{y}")
                except Exception as e:
                    print(f"Workflow Warning: Jiggle Step 2 failed: {e}")

            # Run Step 1 500ms after map to allow WM to settle
            self.popup.after(500, _step_1_move)
            
        self.popup.bind("<Map>", jiggle_window)

    # --- NEW: Helper to toggle view mode ---
    def _set_view_mode(self, mode):
        if mode not in ['dashboard', 'paged']: return
        if mode == self.view_mode: return
        
        print(f"WorkflowApp: Switching view to {mode}")
        self.view_mode = mode
        self.settings_manager.save_workflow_view_mode(mode)
        
        self._create_widgets()
        self._refresh_columns() # Refresh All

    def run(self):
        """Finalizes setup when hosted by UIManager."""
        self.popup.focus_set()
        self._refresh_columns() # Refresh All

    def _setup_styles(self):
        s = ttk.Style(self.popup)
        # 1. Dark Gray background for button frame/column gutters
        s.configure("Button.TFrame", background="#D9D9D9") 
        s.configure("Condensed.TButton", padding=(0, 0), width=2)
        
    def _create_widgets(self):
        # 1. Clear existing widgets (for refresh/toggle)
        for widget in self.popup.winfo_children():
            widget.destroy()

        # --- Top Control Bar ---
        control_frame = ttk.Frame(self.popup, padding=(10, 5, 10, 5))
        control_frame.pack(fill="x", side="top")
        
        # View Mode Toggle Menu (Left Side)
        current_view_label = "Dashboard (4-Col)" if self.view_mode == 'dashboard' else "Paged (Tabs)"
        view_btn = ttk.Menubutton(control_frame, text=f"View: {current_view_label}")
        view_menu = tk.Menu(view_btn, tearoff=0)
        view_btn["menu"] = view_menu
        
        view_menu.add_command(label="Dashboard View (4-Col)", command=lambda: self._set_view_mode("dashboard"))
        view_menu.add_command(label="Paged View (Tabs)", command=lambda: self._set_view_mode("paged"))
        
        view_btn.pack(side="left")
        
        # Space Filler
        ttk.Frame(control_frame).pack(side="left", expand=True, fill="x")
        
        # --- Main Column Frame ---
        main_frame = ttk.Frame(self.popup, padding="10")
        main_frame.pack(expand=True, fill="both")
        
        # --- CONDITIONAL LAYOUT LOGIC ---
        if self.view_mode == 'dashboard':
            # Full Mode: 4 columns in a single grid row
            for col_idx in range(len(self.column_names)): 
                main_frame.grid_columnconfigure(col_idx, weight=1, uniform="col_group")
            main_frame.grid_rowconfigure(0, weight=1)
            
            columns_to_process = self.column_names
            # Helper logic for the loop below
            is_dashboard = True 

        else: # 'paged' mode
            notebook = ttk.Notebook(main_frame)
            notebook.pack(expand=True, fill="both")
            
            # Tab 1: On Rotation / On Deck
            tab1_frame = ttk.Frame(notebook, padding=0)
            tab1_frame.pack(expand=True, fill="both")
            notebook.add(tab1_frame, text="On Rotation & On Deck")
            tab1_frame.grid_columnconfigure(0, weight=1, uniform="tab_col_group"); tab1_frame.grid_columnconfigure(1, weight=1, uniform="tab_col_group")
            tab1_frame.grid_rowconfigure(0, weight=1)
            
            # Tab 2: Fermenting / Lagering
            tab2_frame = ttk.Frame(notebook, padding=0)
            tab2_frame.pack(expand=True, fill="both")
            notebook.add(tab2_frame, text="Fermenting & Lagering/Finishing")
            tab2_frame.grid_columnconfigure(0, weight=1, uniform="tab_col_group"); tab2_frame.grid_columnconfigure(1, weight=1, uniform="tab_col_group")
            tab2_frame.grid_rowconfigure(0, weight=1)

            # Define the mapping for the layout loop: (column_name: (container_frame, grid_column))
            columns_to_process = {
                self.column_names[0]: (tab1_frame, 0), # on_rotation
                self.column_names[1]: (tab1_frame, 1), # on_deck
                self.column_names[2]: (tab2_frame, 0), # fermenting
                self.column_names[3]: (tab2_frame, 1)  # lagering_or_finishing
            }
            is_dashboard = False

        self.column_frames = {}; self.column_canvases = {}; self.inner_frames = {}
        self.column_comboboxes = {}
        
        # Iterate over columns (using the logic defined above)
        iterator = enumerate(columns_to_process) if is_dashboard else enumerate(columns_to_process.keys())
        
        for col_idx, col_name in iterator:
            col_title = self.display_titles[col_name]
            
            # Determine container and grid position based on mode
            if is_dashboard:
                container = main_frame
                grid_col_index = col_idx
            else:
                container, grid_col_index = columns_to_process[col_name]
            
            # --- Column Frame ---
            col_frame = ttk.Frame(container, relief="flat", padding=2)
            col_frame.grid(row=0, column=grid_col_index, sticky="nsew", padx=5, pady=0)
            
            # 1. Header and Combobox Container
            header_container = ttk.Frame(col_frame)
            header_container.pack(fill="x", pady=(0, 5))
            
            # --- ROW 1: Title and Add Button ---
            title_add_frame = ttk.Frame(header_container)
            title_add_frame.pack(fill="x", pady=(0, 2))
            title_add_frame.grid_columnconfigure(0, weight=1)
            
            ttk.Label(title_add_frame, text=col_title, font=('TkDefaultFont', 10, 'bold'), relief="raised", padding=5).grid(row=0, column=0, sticky='ew')
            
            ttk.Button(title_add_frame, text="Add ▼", width=5,
                       command=lambda cn=col_name: self._handle_add_button(cn)).grid(row=0, column=1, sticky='e')

            # --- ROW 2: Combobox ---
            combobox = ttk.Combobox(header_container, 
                                    textvariable=self.column_combobox_vars[col_name],
                                    values=self.beverage_names,
                                    state="readonly",
                                    width=20)
            combobox.pack(fill="x", pady=(2, 5))
            self.column_comboboxes[col_name] = combobox

            # 2. Scrollable Content Setup
            canvas = tk.Canvas(col_frame, borderwidth=0, background="#D9D9D9")
            v_scrollbar = ttk.Scrollbar(col_frame, orient="vertical", command=canvas.yview)
            inner_frame = ttk.Frame(canvas, padding=5)
            
            canvas.configure(yscrollcommand=v_scrollbar.set)
            v_scrollbar.pack(side="right", fill="y")
            canvas.pack(side="left", fill="both", expand=True)
            
            canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor="nw")
            
            inner_frame.bind("<Configure>", lambda e, c=canvas: c.config(scrollregion=c.bbox("all")))
            canvas.bind('<Configure>', lambda e, c=canvas, w=canvas_window: c.itemconfig(w, width=e.width))
            
            self.column_frames[col_name] = col_frame
            self.column_canvases[col_name] = canvas
            self.inner_frames[col_name] = inner_frame
            
            inner_frame.grid_columnconfigure(0, weight=1)
            inner_frame.grid_columnconfigure(1, weight=0)
            
    # --- REMOVED: All Beverage Library Editor Popup Logic ---
    # The dedicated functions for the library editor (_open_beverage_library_popup,
    # _open_beverage_edit_form, _save_beverage, _delete_beverage_and_refresh, _close_library_popup)
    # have been removed as requested.
    # --------------------------------------------------------

    def _open_beverage_library_process(self):
        """Launches the Beverage Library editor as a separate process via main.py."""
        # --- CRITICAL FIX: Use the resolved base_dir for the main script path ---
        main_script_path = os.path.join(self.settings_manager.get_base_dir(), "main.py")
        # --- END FIX ---
        try:
            # Launch main.py with a flag indicating it should open the Beverage Library immediately.
            subprocess.Popen([sys.executable, main_script_path, "--open-beverage-library"])
            print("WorkflowApp: Launched Beverage Library editor via subprocess.")
        except Exception as e:
            print(f"WorkflowApp Error: Could not launch Beverage Library via subprocess: {e}")
            messagebox.showerror("Error", f"Could not launch Beverage Library: {e}", parent=self.popup)

    def _handle_add_button(self, col_name):
        """Handles clicking the 'Add V' button next to the column title."""
        selected_name = self.column_combobox_vars[col_name].get() 
        
        if selected_name in self.name_to_id_map:
            item_id = self.name_to_id_map[selected_name]
            if self.manager.add_item_to_column(item_id, col_name):
                # Optimize: Refresh ONLY the target column
                self._refresh_columns([col_name])
                
                # --- NEW: Reset the dropdown after successful add ---
                self.column_combobox_vars[col_name].set("-- Add Beverage --")
                if col_name in self.column_comboboxes:
                    self.column_comboboxes[col_name].selection_clear()
                # ----------------------------------------------------
        else:
            # Show a simple error since the validation is done client-side
            messagebox.showwarning("Selection Required", "Please select a beverage from the dropdown list.", parent=self.popup)


    def _handle_reset_data(self):
        # This method is now unused but kept in case external code calls it.
        if messagebox.askyesno("Confirm Reset", 
                               "This will permanently clear all Lagering, Fermenting, On Deck, and On Rotation lists, and repopulate the Source List from the Beverage Library. Continue?",
                               parent=self.popup):
            try:
                self.manager.reset_to_library_defaults()
                self._refresh_all_columns()
                messagebox.showinfo("Reset Complete", "Workflow data reset successfully.", parent=self.popup)
            except Exception as e:
                messagebox.showerror("Error", f"An error occurred during reset: {e}", parent=self.popup)

    def _refresh_columns(self, columns_to_update=None):
        """
        Refreshes the UI for specific columns. 
        If columns_to_update is None, refreshes ALL columns (default behavior).
        """
        # 1. Lightweight refresh of beverage data from memory
        self.manager.refresh_beverages()
        
        # 2. Update cached beverage lists (Fast)
        self.all_beverages = self.manager.beverage_library
        self.beverage_names = sorted([b.get('name', 'Untitled') for b in self.all_beverages if b.get('id')])
        self.beverage_names.insert(0, "-- Add Beverage --")
        self.name_to_id_map = {b['name']: b['id'] for b in self.all_beverages if 'id' in b and 'name' in b}

        # 3. Determine which columns to target
        targets = columns_to_update if columns_to_update else self.column_names

        # 4. Redraw ONLY the target columns
        for col_name in targets:
            # Update Dropdown values
            if col_name in self.column_comboboxes:
                 self.column_comboboxes[col_name]['values'] = self.beverage_names
                 current_value = self.column_comboboxes[col_name].get()
                 if current_value not in self.name_to_id_map:
                    self.column_combobox_vars[col_name].set("-- Add Beverage --")

            # Rebuild Beverage Cards
            if col_name in self.inner_frames:
                inner_frame = self.inner_frames[col_name]
                
                # Clear old widgets in this column
                for widget in inner_frame.winfo_children():
                    widget.destroy()
                    
                # Recreate widgets for this column
                item_list = self.manager.columns[col_name]
                for index, item_id in enumerate(item_list):
                    beverage_data = self.manager.get_beverage_data(item_id)
                    self._create_beverage_item_widget(inner_frame, col_name, item_id, beverage_data, index)
                    
                inner_frame.update_idletasks()

    def _create_beverage_item_widget(self, parent_frame, col_name, item_id, data, index):
        # Item frame background is set to the lighter gray: #EAEAEA
        item_frame = tk.Frame(parent_frame, background="#EAEAEA", padx=5, pady=5)
        item_frame.grid(row=index, column=0, sticky="ew", padx=(0, 5), pady=2)
        
        button_frame = ttk.Frame(parent_frame, padding=2, style="Button.TFrame")
        button_frame.grid(row=index, column=1, sticky="ns", padx=(0, 2), pady=2)
        
        # Configure the grid WITHIN the item_frame for two columns (Name/BJCP area and ABV/IBU area)
        item_frame.grid_columnconfigure(0, weight=1)  # Left column (Name/BJCP label)
        item_frame.grid_columnconfigure(1, weight=0)  # Right column (ABV/IBU)

        # Row 0: Beverage Name (Now spans two columns for full width)
        # --- FONT SIZE INCREASED TO 10 ---
        ttk.Label(item_frame, text=data['name'], 
                  font=('TkDefaultFont', 10), 
                  anchor='w', 
                  background="#EAEAEA", 
                  wraplength=200).grid(row=0, column=0, columnspan=2, sticky='ew')
        
        # --- ABV/IBU Section (Moved to Row 1, Column 1) ---
        abv_ibu_frame = tk.Frame(item_frame, background="#EAEAEA")
        # Positioned in row 1, column 1 (right side)
        abv_ibu_frame.grid(row=1, column=1, sticky='e', padx=(5, 0)) 

        # ABV: (Bold Label)
        ttk.Label(abv_ibu_frame, text="ABV:", 
                  font=('TkDefaultFont', 9, 'bold'), 
                  background="#EAEAEA").pack(side='left', padx=(0, 2))
        
        # FIX: The format for ABV display is now handled by ui_manager_base (which pulls from settings_manager).
        # We need to ensure we use '--' if the source data is missing.
        abv_value = data.get('abv', '').strip()
        # The ABV value itself should not contain the %, as this is added by the logic in ui_manager_base.
        # However, to be compliant with the logic where `--` is shown if blank:
        abv_display_text = f"{abv_value}%" if abv_value else "--"
        
        # ABV Value (Normal Text)
        ttk.Label(abv_ibu_frame, text=abv_display_text, 
                  font=('TkDefaultFont', 9), 
                  background="#EAEAEA").pack(side='left', padx=(0, 5))

        # IBU: (Bold Label)
        ttk.Label(abv_ibu_frame, text="IBU:", 
                  font=('TkDefaultFont', 9, 'bold'), 
                  background="#EAEAEA").pack(side='left', padx=(0, 2))
        
        # IBU Value (Normal Text)
        ibu_value = data.get('ibu')
        ibu_display = str(ibu_value) if ibu_value is not None and str(ibu_value).strip() else "--"
        ttk.Label(abv_ibu_frame, text=ibu_display, 
                  font=('TkDefaultFont', 9), 
                  background="#EAEAEA").pack(side='left', padx=(0, 0))
        # --- END MODIFIED ABV/IBU ---
        
        # Row 1: BJCP/Style (Moved to Row 1, Column 0)
        bjcp_style = data.get('bjcp', '').strip()
        bjcp_data_text = bjcp_style if bjcp_style else "--"
        
        # Internal frame to hold BJCP: (bold) and data (normal)
        bjcp_frame = tk.Frame(item_frame, background="#EAEAEA")
        # Positioned in row 1, column 0 (left side)
        bjcp_frame.grid(row=1, column=0, sticky='w') # Removed columnspan=2
        bjcp_frame.grid_columnconfigure(1, weight=1)

        # BJCP: (Bold)
        ttk.Label(bjcp_frame, text="BJCP:", 
                  font=('TkDefaultFont', 9, 'bold'), 
                  background="#EAEAEA").grid(row=0, column=0, sticky='w', padx=(0, 2))
        
        # Data (Normal)
        ttk.Label(bjcp_frame, text=bjcp_data_text, 
                  font=('TkDefaultFont', 9), 
                  background="#EAEAEA", 
                  wraplength=200).grid(row=0, column=1, sticky='w')
        
        # --- Condensing Control Buttons (2x2 Grid Layout) ---
        button_inner_frame = ttk.Frame(button_frame)
        button_inner_frame.pack(expand=True, fill='y') 
        
        # Row 0: Up (Left) | Advance (Right)
        ttk.Button(button_inner_frame, text="▲", style="Condensed.TButton", 
                   command=lambda c=col_name, i_id=item_id: self._handle_move(c, i_id, -1)).grid(row=0, column=0, padx=1, pady=1, sticky="ew")
        
        # Only show Advance if NOT in the last column
        if col_name != "lagering_or_finishing":
             ttk.Button(button_inner_frame, text="▶", style="Condensed.TButton", 
                   command=lambda c=col_name, i_id=item_id: self._handle_advance(c, i_id)).grid(row=0, column=1, padx=1, pady=1, sticky="ew")

        # Row 1: Down (Left) | Remove (Right)
        ttk.Button(button_inner_frame, text="▼", style="Condensed.TButton", 
                   command=lambda c=col_name, i_id=item_id: self._handle_move(c, i_id, 1)).grid(row=1, column=0, padx=1, pady=1, sticky="ew")

        ttk.Button(button_inner_frame, text="x", style="Condensed.TButton", 
                   command=lambda c=col_name, i_id=item_id: self._handle_remove(i_id, c)).grid(row=1, column=1, padx=1, pady=1, sticky="ew")

    def _handle_add(self, item_id, target_col):
        pass
            
    def _handle_remove(self, item_id, col_name):
        if self.manager.remove_item_from_column(item_id, col_name):
            # Optimize: Refresh ONLY the target column
            self._refresh_columns([col_name])

    def _handle_move(self, col_name, item_id, direction):
        if self.manager.move_item(col_name, item_id, direction):
            # Optimize: Refresh ONLY the target column
            self._refresh_columns([col_name])

    def _handle_advance(self, col_name, item_id):
        """
        Moves or copies an item to the next stage in the workflow.
        """
        if col_name == "on_rotation":
            # COPY to "on_deck" -> Only "on_deck" changes visually
            if self.manager.add_item_to_column(item_id, "on_deck"):
                self._refresh_columns(["on_deck"])
                
        elif col_name == "on_deck":
            # MOVE to "fermenting" -> Both columns change
            if self.manager.add_item_to_column(item_id, "fermenting"):
                self.manager.remove_item_from_column(item_id, "on_deck")
                self._refresh_columns(["on_deck", "fermenting"])
                
        elif col_name == "fermenting":
            # MOVE to "lagering" -> Both columns change
            if self.manager.add_item_to_column(item_id, "lagering_or_finishing"):
                self.manager.remove_item_from_column(item_id, "fermenting")
                self._refresh_columns(["fermenting", "lagering_or_finishing"])
