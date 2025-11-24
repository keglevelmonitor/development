"""
fermvault app
fg_calculator.py
"""

import requests
import json
import os
from datetime import datetime
import time

class FGCalculator:
    
    # NOTE: output_file is now only used for debugging/local data storage, not as a core requirement.
    def __init__(self, settings_manager, api_manager, output_file="fermentation_data.json"):
        self.settings_manager = settings_manager
        self.api_manager = api_manager
        
        # --- MODIFICATION: Define the user data directory ---
        self.data_dir = os.path.join(os.path.expanduser('~'), 'fermvault-data')
        
        # --- MODIFICATION: Ensure data directory exists (Safeguard) ---
        try:
            os.makedirs(self.data_dir, exist_ok=True)
        except OSError as e:
            print(f"[ERROR] FGCalc: Could not create data directory at {self.data_dir}: {e}")
        # --- END MODIFICATIONS ---

        # --- MODIFICATION: Set the output file path to be *inside* the data_dir ---
        self.output_file = os.path.join(self.data_dir, output_file)
        # --- END MODIFICATIONS ---


    def _get_api_parameters(self):
        """Retrieves required API key, session ID, and calculation parameters."""
        api_settings = self.settings_manager.get_all_api_settings()
        
        # Note: Active API service and Session ID are read from current settings when method is called
        active_service = self.settings_manager.get("active_api_service")
        api_key = api_settings.get("api_key")
        
        # NOTE: Brew Session ID needs to be fetched from the UI's selected Brew Session
        # Assuming there is a mechanism to get the ID corresponding to the UI's selection.
        # For now, we rely on the caller to potentially provide it if needed, or we fetch a placeholder.
        brew_session_id = self.settings_manager.get("current_brew_session_id") 
        
        # --- MODIFICATION: Removed API check, it's handled by NotificationManager ---
        if active_service == "OFF":
             return None, None, None, None, None, None
        # --- END MODIFICATION ---

        return (
            active_service,
            api_key,
            brew_session_id,
            api_settings.get("tolerance", 0.0005),
            api_settings.get("window_size", 450),
            api_settings.get("max_outliers", 4)
        )
        
    def _fetch_and_save_data(self, active_service, brew_session_id):
        """Fetches historical fermentation data using the APIManager."""
        
        # APIManager is designed to delegate based on the active service name
        data = self.api_manager.get_api_data("fermentation_history", session_id=brew_session_id) 

        if data is not None and isinstance(data, dict):
            try:
                # --- MODIFICATION: Ensure data directory exists ---
                os.makedirs(self.data_dir, exist_ok=True)
                # --- END MODIFICATION ---
                
                # Save data for inspection/debugging
                with open(self.output_file, "w") as f:
                    json.dump(data, f)
                return data
            except IOError as e:
                print(f"[ERROR] FGCalc File I/O error: {e}")
                return data
        else:
            # --- MODIFICATION: Simplified error message ---
            raise Exception("API fetch failed")
            # --- END MODIFICATION ---
            
    def _analyze_fermentation(self, data, tolerance, window_size, max_outliers):
        """
        Analyzes the specific gravity data for stability using an optimized Sliding Window algorithm.
        Iterates from NEWEST to OLDEST.
        Includes thread yielding to prevent UI freeze during long history scans.
        """
        # 1. Filter valid readings
        all_readings = data.get('readings', [])
        valid_readings = [r for r in all_readings if r.get('gravity') is not None]
        sg_values = [r.get('gravity') for r in valid_readings]
        
        N = len(sg_values)
        if N < window_size:
            return {"overall_stable": False, "error": "Not enough data"}

        # 2. Initialize the FIRST window (The Newest Window)
        # Indices: [N-window_size ... N-1]
        current_start_index = N - window_size
        current_window = sg_values[current_start_index : N]
        current_outliers = 0
        
        # Calculate initial outliers for the newest window
        for j in range(len(current_window) - 1):
            if abs(current_window[j+1] - current_window[j]) > tolerance:
                current_outliers += 1

        # Check if the newest window is stable
        if current_outliers <= max_outliers:
            return self._format_result(valid_readings, current_start_index, window_size, current_window)

        # 3. Sliding Window Loop (Backwards)
        # We slide the window to the LEFT (towards the past).
        for i in range(N - window_size - 1, -1, -1):
            
            # --- FIX: Yield to UI thread every 500 iterations ---
            # This prevents the calculation from "starving" the UI and making it look frozen.
            if i % 500 == 0:
                time.sleep(0)
            # ----------------------------------------------------

            # A. HANDLE RIGHT EDGE (Leaving the window)
            val_right_1 = sg_values[i + window_size - 1]
            val_right_2 = sg_values[i + window_size]
            if abs(val_right_2 - val_right_1) > tolerance:
                current_outliers -= 1 

            # B. HANDLE LEFT EDGE (Entering the window)
            val_left_1 = sg_values[i]
            val_left_2 = sg_values[i+1]
            if abs(val_left_2 - val_left_1) > tolerance:
                current_outliers += 1 
            
            # C. Check Stability
            if current_outliers <= max_outliers:
                found_window = sg_values[i : i + window_size]
                return self._format_result(valid_readings, i, window_size, found_window)

        return {"overall_stable": False}

    def _format_result(self, valid_readings, start_index, window_size, window_values):
        """Helper to format the success response."""
        first_reading = valid_readings[start_index]
        last_reading = valid_readings[start_index + window_size - 1]
        average_sg = sum(window_values) / len(window_values)

        return {
            "overall_stable": True,
            "first_timestamp": first_reading.get('created_at'),
            "last_timestamp": last_reading.get('created_at'),
            "average_sg": average_sg,
        }
        
    def calculate_fg(self):
        """Main routine to fetch, process, and return FG calculation results."""
        
        active_service, api_key, brew_session_id, tolerance, window_size, max_outliers = self._get_api_parameters()
        
        # Store settings for the log message, even if we fail early
        settings_dict = {"tolerance": tolerance, "window_size": window_size, "max_outliers": max_outliers}
        
        if active_service == "OFF":
            # This case is now handled by NotificationManager, but we keep it as a fallback.
            return {"error": "API OFF", "stable": False, "settings": settings_dict}
            
        # --- MODIFICATION: Simplified error logic ---
        if not brew_session_id:
            return {"error": "No Session ID", "stable": False, "settings": settings_dict}
        # --- END MODIFICATION ---
        
        print(f"FG Calc: Starting analysis for {brew_session_id}. Tolerance: {tolerance}")
        
        try:
            data = self._fetch_and_save_data(active_service, brew_session_id)
            
            results = self._analyze_fermentation(data, tolerance, window_size, max_outliers)
            
            return {
                "results": results, 
                "settings": settings_dict,
                "stable": results.get("overall_stable", False)
            }
            
        except Exception as e:
            print(f"[ERROR] FG calculation failed: {e}")
            # --- MODIFICATION: Simplified error message ---
            # e.g., "API fetch failed" or a generic "calculation error"
            error_msg = str(e) if str(e) == "API fetch failed" else "calculation error"
            return {"error": error_msg, "stable": False, "settings": settings_dict}
            # --- END MODIFICATION ---
