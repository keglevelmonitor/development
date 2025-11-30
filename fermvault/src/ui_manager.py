"""
fermvault app
ui_manager.py
"""

import tkinter as tk
from ui_manager_base import MainUIBase
from popup_manager import PopupManager 
from fg_calculator import FGCalculator

# UIManager inherits from BOTH the base layout and the popup logic
class UIManager(MainUIBase, PopupManager):
    
    # NOTE: The __init__ signature must match the one in main.py
    def __init__(self, root, settings_manager_instance, temp_controller_instance, api_manager_instance, notification_manager_instance, app_version_string, fg_calculator_instance): # <-- UPDATED SIGNATURE
        
        # Add the instance reference
        self.fg_calculator_instance = fg_calculator_instance # <-- STORED INSTANCE
        
        # 1. Initialize MainUIBase (Layout and root variables)
        # MainUIBase handles the general window setup and widget creation.
        MainUIBase.__init__(self, root, settings_manager_instance, temp_controller_instance, api_manager_instance, notification_manager_instance, app_version_string)
        
        # 2. Initialize PopupManager (Popup logic and StringVars)
        # PopupManager sets up all the variables and methods related to opening/saving popups.
        PopupManager.__init__(self, self)

        # 3. Final Setup: Link Menu Commands
        # The MenuButton created in MainUIBase now uses the methods exposed via PopupManager.
        
        # 4. Set final control mode defaults (if not set in settings)
        self.control_mode_var.set(self.settings_manager.get("control_mode", "Beer Hold"))

        print("[UIManager] Composition complete and UI initialized.")
