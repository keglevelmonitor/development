"""
fermvault app
messages.py
"""

# Messages intended for immediate user attention (Single-line UI area).
USER_MESSAGES = {
    "INIT_COMPLETE": "System initialized. Select mode and start monitoring.",
    "MONITORING_STARTED": "Monitoring STARTED",
    "MONITORING_STOPPED": "Monitoring STOPPED",
    "PENDING_CHANGES": "Settings changes pending - click Apply Settings (TBD)",
    "API_FETCH_ERROR": "API Data Error: Check Key/ID or switch to OFF mode.",
    "SENSOR_ERROR": "Temperature sensor error detected - check connections.",
}

# Messages logged for system reference (Multi-line log area).
SYSTEM_MESSAGES = {
    "INIT_START": "Starting Fermentation Vault initialization...",
    "INIT_COMPLETE": "System initialization complete. Monitoring thread active.",
    "API_SERVICE_SET": "Active API service set to: {service}",
    "CONTROL_MODE_SET": "Control Mode set to: {mode}",
    "COMPRESSOR_DWELL": "Cooling restricted by Dwell Time for {remaining} seconds.",
    "COMPRESSOR_FAILSAFE": "Cooling restricted by Fail-Safe until {time}.",
    "STATUS_REQUEST_SENT": "Status Request received and reply sent to {sender}.",
    "SETTINGS_SAVED": "Settings saved successfully for {category}.",
}

def get_user_message(key, **kwargs):
    """Retrieve and format a user message."""
    message = USER_MESSAGES.get(key, f"Unknown User Message Key: {key}")
    try:
        return message.format(**kwargs)
    except KeyError:
        return message + " [Format Error]"

def get_system_message(key, **kwargs):
    """Retrieve and format a system message."""
    message = SYSTEM_MESSAGES.get(key, f"Unknown System Message Key: {key}")
    try:
        return message.format(**kwargs)
    except KeyError:
        return message + " [Format Error]"
