"""
fermvault app
api_manager.py
"""

import os
import sys
import importlib.util
import time

class APIManager:
    
    def __init__(self, settings_manager):
        self.settings_manager = settings_manager
        self.available_services = {"OFF": None}
        self.active_service_instance = None
        
    def discover_services(self, directory):
        """Scans the directory for files matching *.api.py and loads them dynamically."""
        print(f"APIManager: Discovering API services in {directory}...")
        
        for filename in os.listdir(directory):
            if filename.endswith(".api.py"):
                module_name = filename[:-7] # e.g., 'brewersfriend'
                file_path = os.path.join(directory, filename)
                
                try:
                    spec = importlib.util.spec_from_file_location(f"api_modules.{module_name}", file_path)
                    if spec:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[spec.name] = module
                        spec.loader.exec_module(module)
                        
                        # Assuming the class inside is named [ModuleName]API (e.g., BrewersFriendAPI)
                        class_name = module_name.capitalize().replace('_', '') + "API"
                        service_class = getattr(module, class_name)
                        
                        # Store the class reference, not an instance
                        self.available_services[module_name] = service_class
                        print(f"APIManager: Discovered and loaded service: {module_name}")

                except Exception as e:
                    print(f"[ERROR] APIManager: Failed to load service {filename}: {e}")

        # Initialize the active service instance based on saved setting
        self.set_active_service(self.settings_manager.get("active_api_service", "OFF"))

    def set_active_service(self, service_name):
        """Instantiates the selected API service class."""
        if service_name not in self.available_services:
            print(f"[ERROR] APIManager: Service {service_name} not found. Setting to OFF.")
            service_name = "OFF"
            
        if service_name == "OFF":
            self.active_service_instance = None
            self.settings_manager.set("active_api_service", "OFF")
            return
            
        # Instantiate the service class, passing the settings manager
        try:
            ServiceClass = self.available_services[service_name]
            self.active_service_instance = ServiceClass(self.settings_manager)
            self.settings_manager.set("active_api_service", service_name)
            print(f"APIManager: Active service set to {service_name}.")
        except Exception as e:
            print(f"[ERROR] APIManager: Failed to instantiate service {service_name}: {e}")
            self.active_service_instance = None
            self.settings_manager.set("active_api_service", "OFF")

    def get_api_data(self, data_type, session_id=None):
        """Delegates the data request to the active service instance."""
        if self.active_service_instance:
            try:
                # Assuming all service instances have a 'get_data' method
                return self.active_service_instance.get_data(data_type, session_id)
            except Exception as e:
                print(f"[ERROR] APIManager: Active service call failed: {e}")
        
        # Fallback if no active service
        return None
