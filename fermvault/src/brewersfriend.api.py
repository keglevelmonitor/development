"""
fermvault app
brewersfriend.api.py
"""

import requests
import json
from datetime import datetime
import pytz

class BrewersfriendAPI:
    
    def __init__(self, settings_manager):
        self.settings_manager = settings_manager
        self.api_key = self.settings_manager.get("api_key", "")
        self.base_url = "https://api.brewersfriend.com/v1/"
        
    # --- MODIFICATION: Added safe converter ---
    def _safe_float_convert(self, value, default=None):
        """Safely converts a value to float, handling None, '', etc."""
        if value is None:
            return default
        try:
            return float(value)
        except (ValueError, TypeError):
            return default
    # --- END MODIFICATION ---
            
    def get_data(self, data_type, session_id=None):
        if not self.api_key:
            print("[ERROR] BrewersFriendAPI: API key is missing.")
            # --- MODIFICATION: Return the error instead of None ---
            return {"error": "API key is missing. Please set in API & FG Settings."}
            # --- END MODIFICATION ---
        
        if data_type == "list_sessions":
            return self._fetch_brew_sessions()
        elif data_type == "session_data" and session_id:
            return self._fetch_session_data(session_id)
        elif data_type == "fermentation_history" and session_id:
            # This is the endpoint the FG calculator will need
            return self._fetch_fermentation_readings(session_id)
        else:
            print(f"[ERROR] BrewersFriendAPI: Unknown data type {data_type} or missing ID.")
            return None

    def _fetch_brew_sessions(self):
        """Fetches a list of recent brew sessions."""
        url = self.base_url + "brewsessions"
        headers = {"X-API-Key": self.api_key}
        params = {"limit": 10}
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Returns data structure compatible with UI parsing for the Brew Session dropdown
            return data.get("brewsessions", [])
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] BrewersFriendAPI: Failed to fetch sessions: {e}")
            return None

    def _fetch_session_data(self, session_id):
        """
        Fetches detailed data for a single brew session (OG/SG/Temp).
        Tries the fast '/brewsessions' endpoint first. If no active stream
        data is found, it falls back to the slow '/fermentation' endpoint.
        """
        url = self.base_url + f"brewsessions/{session_id}"
        headers = {"X-API-Key": self.api_key}

        try:
            # --- API Call 1: Get Summary Data (Fast Path) ---
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not (data and "brewsessions" in data and len(data["brewsessions"]) > 0):
                return None
                
            session_data = data["brewsessions"][0]
            
            # --- MODIFICATION: Use safe conversion for OG ---
            current_stats = session_data.get("current_stats", {})
            og_value = self._safe_float_convert(current_stats.get("og"))
            # --- END MODIFICATION ---
            
            og_timestamp_str = session_data.get("created_at")
            recipe_title = session_data.get("recipe_title", "Unknown")

            # --- Attempt to get data from an active stream ---
            device_reading_json = session_data.get("device_reading", "{}") or "{}"
            device_reading = json.loads(device_reading_json)
            last_reading = device_reading.get("last_reading", {})
            
            # --- MODIFICATION: Use safe conversion for gravity ---
            gravity = self._safe_float_convert(last_reading.get("gravity"))
            # --- END MODIFICATION ---
            
            sg_timestamp_str = session_data.get("device_updated_at")

            # --- FIX: Safely convert temp_c to float ---
            temp_c = self._safe_float_convert(last_reading.get("temp"))
            beer_temp_f = (temp_c * 9/5) + 32 if temp_c is not None else None
            # --- END FIX ---

            # --- MODIFICATION: Check if gravity is a valid float > 0 ---
            if gravity is not None and gravity > 0:
            # --- END MODIFICATION ---
                print("[DEBUG] BrewersFriendAPI: Found active stream data. Using fast path.")
                return {
                    "sg_actual": gravity, # Already a float
                    "og_actual": og_value,  # Already a float or None
                    "beer_temp_f": beer_temp_f,
                    "recipe_title": recipe_title,
                    "sg_timestamp": sg_timestamp_str,
                    "og_timestamp": og_timestamp_str
                }
            
            # --- FALLBACK PATH: No active device. Must fetch history. ---
            print("[DEBUG] BrewersFriendAPI: No active stream. Fetching full history to find last SG.")
            
            # This calls the *other* function in this class
            readings_data = self._fetch_fermentation_readings(session_id)

            if not (readings_data and "readings" in readings_data and readings_data["readings"]):
                # No history either, just return OG data
                print("[DEBUG] BrewersFriendAPI: No readings found in history.")
                return { 
                    "sg_actual": None, 
                    "og_actual": og_value, # Already a float or None
                    "beer_temp_f": None, 
                    "recipe_title": recipe_title, 
                    "sg_timestamp": None, 
                    "og_timestamp": og_timestamp_str 
                }

            # Find the most recent reading *with* a gravity value
            latest_gravity_reading = None
            for reading in readings_data["readings"]:
                if reading.get("gravity") is not None and reading.get("created_at"):
                    if latest_gravity_reading is None or reading["created_at"] > latest_gravity_reading["created_at"]:
                        latest_gravity_reading = reading
            
            if latest_gravity_reading:
                # --- MODIFICATION: Use safe conversion ---
                sg_val = self._safe_float_convert(latest_gravity_reading.get("gravity"))
                # --- END MODIFICATION ---
                sg_time = latest_gravity_reading.get("created_at")

                # --- FIX: Safely convert temp_c_hist to float ---
                temp_c_hist = self._safe_float_convert(latest_gravity_reading.get("temp"))
                beer_temp_f_hist = (temp_c_hist * 9/5) + 32 if temp_c_hist is not None else None
                # --- END FIX ---
                
                print(f"[DEBUG] BrewersFriendAPI: Found last historical SG: {sg_val} at {sg_time}")
                
                return {
                    "sg_actual": sg_val,  # Already a float or None
                    "og_actual": og_value, # Already a float or None
                    "beer_temp_f": beer_temp_f_hist,
                    "recipe_title": recipe_title,
                    "sg_timestamp": sg_time,
                    "og_timestamp": og_timestamp_str
                }
            else:
                # No gravity readings in history, just return OG
                print("[DEBUG] BrewersFriendAPI: History found, but no gravity readings present.")
                return { 
                    "sg_actual": None, 
                    "og_actual": og_value, # Already a float or None
                    "beer_temp_f": None, 
                    "recipe_title": recipe_title, 
                    "sg_timestamp": None, 
                    "og_timestamp": og_timestamp_str 
                }

        except requests.exceptions.RequestException as e:
            print(f"[ERROR] BrewersFriendAPI: Failed to fetch session data: {e}")
            return None

    def _fetch_fermentation_readings(self, session_id):
        """Fetches all readings for a brew session, required for FG calc."""
        # --- MODIFICATION START: Use the correct endpoint ---
        url = self.base_url + f"fermentation/{session_id}"
        # --- MODIFICATION END ---
        headers = {"X-API-Key": self.api_key}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            # The data is expected to be in a dictionary, e.g., {"readings": [...]}
            return data 
            
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] BrewersFriendAPI: Failed to fetch readings for FG calc: {e}")
            return None
