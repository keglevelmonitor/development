FermVault Help File Formatting Cheat Sheet
==========================================
This file contains the help text for the application.
Sections are defined by [SECTION: name].

Formatting Syntax:
------------------
Headers:      ## Header Text ##           (Must start and end with ##)
Bullets:      * List Item                 (Must start with * and a space)
Bold:         **Bold Text** (Wrap text in double asterisks)
Links (Web):  [Link Text](http://...)     (Opens in default browser)
Links (App):  [Link Text](section:name)   (Navigates to another help section)

Note: Standard text is automatically wrapped.
==========================================

[SECTION: main]
## FermVault Help ##
Select a topic below:
* [Temperature Setpoints & Modes](section:setpoints)
* [PID Tuning](section:pid)
* [Notifications & Alerts](section:notifications)
* [API & Final Gravity](section:api)
* [Brew Sessions](section:brew_sessions)
* [System Settings](section:system)
* [Wiring Diagram](section:wiring)

##Fermentation Vault##
The FermVault is a control system that uses temperature sensors and PID control to monitor and manage fermentation temperature. 
* Optionally, if a digital hydrometer and a service such as brewersfriend.com are used, the fermentation data can be loaded to the app via an API service to help you follow the fermentation process.
* Optionally, notifications of the vault's current conditions can be emailed on a user-selectable schedule. 
* Optionally, commands can be emailed to the vault to remotely change the control mode or the temperature setpoints. 
* Compressor protection is provided through user-adjustable settings for compressor dwell time (on/off cycle time), maximum compressor run-time (fail-safe), and fail-safe shutdown or rest time. 

##Operational Specs##
**The Vault**
A refrigerator or a freezer (preferred) is the foundation of the vault. The vault holds the fermentation vessel and provides an enclosed, insulated environment for the system to control the temperature. The refrigerator or freezer function is used for cooling. A small pad-type heater placed in the vault, beneath the fermentation vessel, is used for heating. 

Two relays, one for heating and one for cooling, are turned on or off by the control system to energize the appropriate source and achieve the target setpoint using PID (Proportional / Integral / Derivative) control. 

A third relay controls an optional circulation fan that can be placed inside the vault to allow more even cooling and heating of the vault.

**Sensors**
Two DS18B20 temperature sensors monitor temperature. The ambient sensor is installed inside the air space in the vault and measures the actual air temperature. The beer sensor is immersed in the beer and measures the actual beer temperature. 

**Operational controls**
Two user-adjustable setpoints, one for ambient and one for beer, specify the target temperature. The control mode determines how the setpoints and actual measurements are used to reach and maintain the target temperature.  

## Settings Menus ##
Popups called from the Settings menu allow you to adjust system parameters and view important information about the app. 

[<< Back to Help Index](section:main)

[SECTION: setpoints]
## Operational Controls & Modes ##
Two user-adjustable setpoints, one for ambient and one for beer, specify the target temperature. The control mode determines how the setpoints and actual measurements are used to reach and maintain the target temperature.  

**Ambient Control Mode**
The function of this mode is to quickly bring the actual ambient temperature to the ambient setpoint and closely hold that temperature. The ambient setpoint is the target. The control system turns the heating/cooling relays on and off to achieve and maintain the target without regard to the beer setpoint. The default deadband or "window" for control is +/- 1 degree F from the setpoint. The deadband is user-adjustable.

**Beer Control Mode**
The function of this mode is to quickly bring the actual beer temperature to the beer setpoint and closely hold that temperature. The beer setpoint is the target. The control system turns the heating/cooling relays on and off to achieve and maintain the target with the assistance of the ambient actual temperature and the PID algorithm.

Ambient maximum and minimum thresholds are automatically calculated using the PID algorithm, and are adjusted to provide a narrow deadband. When the beer setpoint and actual are far apart, the deadband is far higher or lower than the beer temperature. Thus the ambient temperature is far higher or lower than the beer temperature, allowing more rapid heating or cooling of the beer. As the difference between the beer setpoint and actual narrows, the deadband moves closer to the beer setpoint. The PID algorithm allows the system to heat or cool to the beer target quickly, and hold the temperature, without large overshoot or undershoot. The PID parameters are user-adjustable.

**Ramp Control Mode**
The function of this mode is to slowly increase the beer setpoint and thus the actual beer temperature to achieve a specified hold target in a specified period of time. This method is often used for lager fermentation, and the finished target is often used for a diacetyl rest. 

The beer setpoint is the starting target, the ramp-up setpoint is the end target, and the ramp duration is used to calculate how much and how often the beer setpoint is incremented. The PID algorithm allows the system to continuously ramp-up the beer temperature to the target in a smooth and controlled fashion.

**Crash Control Mode**
The function of this mode is to quickly decrease the actual beer temperature to achieve the target. The crash setpoint is the target. The control system turns the heating/cooling relays on and off to achieve and maintain the target with the assistance of the ambient temperature measurement and the PID algorithm. Just like the beer control mode, the PID algorithm allows the vault to get very cold, well below freezing if necessary, in order to bring the beer to target as quickly as possible. The PID algorithm brings the deadband closer to the actual beer temperature as it approaches the target, limiting undershoot and thereby virtually eliminating the risk of freezing the beer. 

[<< Back to Help Index](section:main)

[SECTION: pid]
##WARNING - EXPERT SETTINGS##

These settings are for expert users only. They directly control the temperature control algorithms.

Improper settings may produce unexpected results, poor temperature control, or potentially dangerous (overheating/overcooling) conditions.

**Do not change these settings unless you fully understand their function.**

Use the "Reset to Defaults" button to restore the original, stable tuning.

##Control Methods Explained##

Your controller uses two different methods to control temperature, depending on the "Control Mode" selected.

* **Thermostatic Control:** This is a simple ON/OFF switch. It is used in "Ambient Hold" mode and during the main "Ramp-Up" phase. It creates a "deadband" (window) around your target and turns the heater or cooler on when the temperature leaves that window.

* **PID Control:** This is a "smart" controller used in "Beer Hold," "Fast Crash," and the start/end of "Ramp-Up" mode. It uses a "PID Envelope" to predictively control the ambient temperature to gently guide your beer temperature to its setpoint.

##PID Settings (Tab 1)##

**PID (Kp, Ki, Kd) Parameters**

These three values are the core of the PID controller. They determine how aggressively it reacts to changes in beer temperature.

**Proportional (Kp):** The "Present" term. This is the main power of the controller. A higher Kp reacts more strongly to the current error between your setpoint and the actual temperature.

	**Too high:** Leads to wild temperature swings and overshooting.

	**Too low:** The controller will be very slow to reach the setpoint.

**Integral (Ki):** The "Past" term. This term "remembers" past errors. It is responsible for eliminating "droop" (a small, persistent error where the temperature never quite reaches the setpoint).

	* **Too high:** Can cause overshooting and instability.

	* **Too low:** Will be slow to correct for small, lingering errors.

**Derivative (Kd):** The "Future" term. This term "predicts" the future by looking at how fast the temperature is changing. It acts as a damper, applying the brakes as you get close to the setpoint to prevent overshooting.

	* **Too high:** Will "choke" the controller, making it very slow.

	* **Too low:** Will allow the temperature to overshoot the setpoint.

**PID Logging (Checkbox)**

* This enables (if checked) or disables (if unchecked) the pid_tuning_log.csv file.

* When enabled, the controller will log its internal state (Setpoint, Beer Temp, PID Output, etc.) to this file every 5 seconds. This data is essential for analyzing how the controller is behaving and for fine-tuning the Kp, Ki, and Kd values.

##Tuning Parameters (Tab 2)##

**Global PID Tuning**

* **PID Idle Zone (All Modes):** This is a deadband (in F) for the **Integral (Ki)** term ONLY. If the beer temp is inside this zone (e.g., +/- 0.5 F), the Integral is reset to zero.

* **Purpose:** This is critical for preventing "Integral Windup." It stops the controller from building up a huge Ki value when it's already at the setpoint, which would cause a massive overshoot the next time it needs to run.

**Ambient Mode Tuning**

* **Ambient Mode Deadband:** This is the +/- value (in F) used for **Thermostatic** control in "Ambient Hold" mode.

* **Example:** If your target is 37.0 F and this is 1.0 F, the controller will cool when the temp hits 38.0 F and heat when it hits 36.0 F.

**PID Mode Tuning (Beer/Ramp/Crash)**

This controls the "PID Envelope," which is the +/- window (in F) applied to the **PID output.**

* **Standard PID Envelope (Beer/Ramp):** This is the window used for gentle holds ("Beer Hold" and the start/end of "Ramp-Up"). A smaller value provides a tighter, more gentle ambient control.

* **Example:** The PID decides the ambient temp should be 50 F. If this value is 1.0 F, the controller will cool the ambient to 49.0 F and heat it to 51.0 F.

* **Crash Mode Envelope Width:** This is a **separate, larger** window used ONLY by "Fast Crash" mode.

* **Purpose:** A larger window (e.g., 2.0 F) makes the crash more aggressive, as it allows the cooler to run harder and create a wider, colder ambient envelope.

**Ramp-Up Mode Staging**

This mode is a 3-stage process. These parameters control the "gates" between those stages.

* **Stage 1: Pre-Ramp (PID Hold):** The system holds the beer at the "Beer Temp" setpoint.

	* **Ramp: Pre-Ramp Tolerance:** This is the +/- value (in F) that the beer temp must be inside before the ramp will begin. It ensures your beer is stable before the ramp starts.

* **Stage 2: Main Ramp (Thermostatic):** The system follows the moving ramp target thermostatically.

	* **Ramp:** Thermostatic Deadband: This is the +/- value (in F) for the thermostatic controller during the main ramp. A smaller value (e.g., 0.1 F) will keep the beer temp very close to the moving target.

* **Stage 3: PID Landing:** The system switches back to a gentle PID hold to "soft land" at the final "Ramp Temp" setpoint.

	* **Ramp: PID Landing Zone:** This is the trigger (in F) for this stage. When the moving target is this close to the final "Ramp Temp" (e.g., 0.5 F away), the system will switch from Thermostatic to PID control.

[<< Back to Help Index](section:main)

[SECTION: notifications]
## Notifications ##
Configure how the app alerts you.

**Push Notifications**
Periodic status updates sent to your email. You can adjust the email notification interval (Frequency) and set the recipient email address.

**Conditional Notifications**
Triggered when specific conditions are met, such as:
* Ambient or beer temperature exceeds defined limits.
* Final Gravity (FG) becomes stable.
* A sensor is disconnected or fails.

**Email Controls (Status & Commands)**
This feature allows you to send emails **TO** the Pi to request a status update or change settings remotely. When enabled, the RPi scans the configured email account for new messages. If a new message is found, it is processed by the app and marked as Read in the email account. If STATUS or COMMAND is in the subject line, the app parses the information in the email and acts: 
* If STATUS is in the subject line, a report of the current conditions is emailed to the recipient email address. 
* If COMMAND is in the subject line, the app parses the body of the email and processes valid commands (such a changing control mode or setpoints). 
* Note that STATUS and COMMAND are not case-sensitive.

**Email Configuration**
Notifications require a valid SMTP configuration (for outgoing) and IMAP configuration (for incoming) in the "RPi Email Configuration" tab.

It is recommended that you use a dedicated email account set up exclusively for use by this app. If you use your personal email for this feature, then every minute your email account's inbox will be scanned. New messages will be marked as read. The app will try to find any email with Status or Command. You don't want the app running through your personal emails and marking them read and looking for valid commands for the app. Use an email account dedicated for use by this app only.

[<< Back to Help Index](section:main)

[SECTION: api]
## API Services ##
API Services are optional. When OFF, all API functions are disabled. 

The default API service is brewersfriend.com. If you subscribe to brewersfriend.com and use a digital hydrometer like the Tilt, iSpindel, or RAPT Pill, you can enable the brewersfriend.com API service. Doing so will allow you to:
* Select the Brew Session from a list of the ten most recent brew sessions at brewersfriend.com.
* Collect and show OG (Original Gravity) and SG (current Specific Gravity) readings in the FermVault app. 
* Calculate FG (Final Gravity) based on parameters set in the API Settings popup. 

## Final Gravity (FG) Settings ##
* **FG Check Frequency**: How often to check for stable gravity.
* **SG Range Tolerance**: The maximum gravity change allowed to be considered "stable".
* **SG Records Window**: The number of data points to analyze for stability.
* **Max SG Outliers**: How many anomalous readings to ignore.

## Custom API Services Implementation ##
You can create a custom API service to interact with the app.

This section describes the interface "contract" that a custom Python class must follow to be dynamically loaded and used as an API Service by the Fermentation Vault application.

**1. File and Class Naming Convention**
The APIManager discovers plugins by scanning the application directory for files matching a specific pattern.
* **File Name:** Must end with `.api.py` (e.g., `my_service.api.py`).
* **Class Name:** The file must contain a class whose name is the "camel case" version of the module name, plus "API".
    * `brewersfriend.api.py` must contain class `BrewersfriendAPI`.
    * `my_service.api.py` must contain class `MyServiceAPI`.

**2. Class Initialization (Constructor)**
The plugin class must implement an `__init__` method that accepts a single argument: `settings_manager`.
* **Definition:** `def __init__(self, settings_manager):`
* **Purpose:** The application will pass its live SettingsManager instance to the plugin upon initialization.
* **Implementation:** The plugin is required to use this `settings_manager` object to retrieve its own API key and any other necessary settings.

**3. Main Data Method (Interface)**
The plugin class must implement a public method named `get_data`.
* **Definition:** `def get_data(self, data_type, session_id=None):`
* **Parameters:**
    * `data_type (str)`: A string token that tells the plugin what data the application is requesting.
    * `session_id (str or None)`: The unique ID of the brew session, if one is required.
* **Return:** The method must return data in the specific format required by the `data_type` or `None` if the API call fails.

**4. Required data_type Endpoints**

**A. data_type="list_sessions"**
* **Called By:** UIManager (to populate the "Brew Session" dropdown).
* **Expected Output:** A List of Dictionaries. Each dictionary must contain:
    * `id (str or int)`: The unique identifier for this session.
    * `recipe_title (str)`: The human-readable name.
* **Example Return:**
```json
[
  { "id": "530259", "recipe_title": "Baltic Porter" },
  { "id": "530123", "recipe_title": "Hazy IPA" }
]


**B. data_type="session_data"**
* **Called By:** NotificationManager (to populate the main UI's OG/SG fields) [cite: notification_manager.py].
* **session_id:** Will be a valid session ID (str) provided by the UI.
* **Expected Output:** A single Dictionary. This dictionary must contain the following keys. If a value is not available, the plugin should return None for that key.
* **og_actual (float or None):** The Original Gravity.
* **sg_actual (float or None):** The most recent Specific Gravity.
* **og_timestamp (str or None):** An ISO 8601 formatted timestamp string (e.g., "2025-11-10T15:22:44+00:00") for the og_actual reading.
* **sg_timestamp (str or None):** An ISO 8601 formatted timestamp string for the sg_actual reading.

**Example Return:**

JSON

{
"og_actual": 1.070,
"sg_actual": 1.015,
"og_timestamp": "2025-11-01T13:18:16+00:00",
"sg_timestamp": "2025-11-10T15:22:44+00:00",
"recipe_title": "Baltic Porter W34/70"
}

**C. data_type="fermentation_history"**
* **Called By:** FGCalculator (to perform stability analysis) [cite: fg_calculator.py].
* **session_id:** Will be a valid session ID (str) provided by the UI.
* **Expected Output:** A single Dictionary. This dictionary must contain a key named "readings".
* **"readings" (List):** A List of Dictionaries. Each dictionary represents a single historical gravity reading and must contain:
* **gravity (float):** The gravity reading.
* **created_at (str):** An ISO 8601 formatted timestamp string. The list must be in chronological order (oldest to newest, or newest to oldest) for the FGCalculator's windowing function to work correctly.

**Example Return:**

JSON

{
"readings": [
{ "gravity": 1.016, "created_at": "2025-11-09T12:00:00+00:00" },
{ "gravity": 1.015, "created_at": "2025-11-09T18:00:00+00:00" },
{ "gravity": 1.015, "created_at": "2025-11-10T00:00:00+00:00" },
{ "gravity": 1.015, "created_at": "2025-11-10T06:00:00+00:00" }
]
}

**5. Data Formats & Error Handling**
* **Timestamps:** All timestamps must be returned as strings in ISO 8601 format. The NotificationManager's parser is built to handle this [cite: notification_manager.py].
* **Gravity/Temperatures:** All gravity or temperature values must be returned as float (or int) types, or None. The application contains safety checks (e.g., _safe_float_convert) to handle None, but it will crash if it receives a string for a numeric value (e.g., "1.050" instead of 1.050) [cite: brewersfriend.api.py, notification_manager.py].
* **API Errors:** If the plugin experiences an HTTP error, a KeyError, or any other failure, the get_data method should catch the exception and return None. The APIManager will handle this None return gracefully and log the error [cite: api_manager.py].

[<< Back to Help Index](section:main)
