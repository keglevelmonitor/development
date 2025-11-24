================================================================================
KEGLEVEL HELP FILE SYNTAX GUIDE
================================================================================
1. DEFINING SECTIONS
   - Start a section with a tag like: [SECTION: name]
   - The section continues until the next [SECTION: tag] or the end of the file.

2. FORMATTING RULES
   - Headings: ## My Heading ## (Large, Bold, Underlined)
   - Bold: **important** (Bold text)
   - Bullets: * Item (Indented bullet)
   - Links: [Text](URL) (Opens Browser) or [Text](section:name) (Internal Jump)
================================================================================

[SECTION: main]
## Welcome to KegLevel Monitor ##

KegLevel Monitor is a precision inventory tracking system for your kegerator, utilizing flow meters and temperature sensors to give you real-time data on your pours.

**Quick Links:**
* [Keg Configuration](section:keg_settings)
* [Beverage Library](section:beverage_library)
* [Notifications](section:notifications)
* [Calibration](section:calibration)
* [System Settings](section:system_settings)

**Support:**
For additional support or to report bugs, please contact the developer via email:

keglevelmonitor@gmail.com

[SECTION: keg_settings]
## Keg Settings ##

This screen allows you to define the physical characteristics of your kegs to calculate volume accurately.

**Definitions:**
* **Tare Weight:** The weight of the keg shell when completely empty.
* **Starting Total Weight:** The weight of the full keg (shell + liquid).
* **Maximum Full Volume:** The theoretical capacity (e.g., 18.93L for a Corny keg). Used for graphical displays.
* **Calculated Starting Volume:** Derived automatically from the weights above. This is your true "100%" reference for tracking.

**How to use:**
1. Click **Add New Keg** to create a profile.
2. Enter the weights in your preferred unit (kg or lb).
3. Click **Save**.
4. Assign this profile to a specific Tap in the main window dropdowns.

[SECTION: beverage_library]
## Beverage Library ##

The Library stores details about the beers, ciders, or seltzers you have on tap.

**Features:**
* **Importing:** You can import standard BJCP style guidelines using the dropdown at the bottom of the main library list.
* **Editing:** Click "Edit" on any item to customize ABV, IBU, or descriptions.
* **Assignment:** Once a beverage is created here, you can assign it to a Tap on the main screen using the dropdowns above the progress bars.

[SECTION: notifications]
## Notification Settings ##

KegLevel can alert you via email when kegs get low or temperature goes out of range.

**Outbound Alerts (Push):**
Set up a recipient email to receive daily or hourly status reports containing flow data and temperature logs.

**Conditional Alerts:**
* **Volume:** Trigger an instant email when a keg drops below a specific volume (e.g., 4 Liters).
* **Temperature:** Trigger an alert if the kegerator gets too warm (e.g., > 45F) or too cold (e.g., < 30F).

**Inbound Control:**
Enable "Status Request" to allow the system to check for emails with the subject "STATUS". It will reply immediately with current system stats.

[SECTION: calibration]
## Flow Sensor Calibration ##

To ensure accurate tracking, each flow meter must be calibrated to your specific system pressure and line length.

**The "Single Pour" Method:**
1. Click **Calibrate** next to a specific tap.
2. Pour a known volume (e.g., exactly 1 Liter or 32oz) into a measuring jug.
3. Enter that known volume into the "Volume Poured" box.
4. Click **Stop**. The system will calculate the new "Pulses Per Liter" (K-Factor) automatically.
5. (Optional) You can choose to deduct this calibration pour from your inventory or ignore it.

**Expert Mode:**
If you already know your K-Factor, click "Manual Cal Factor - Expert Only" on the main calibration screen to type it in directly.

[SECTION: system_settings]
## System Settings ##

Global configuration for the application.

* **Display Mode:** Toggle between "Full" (1080p) and "Compact" (800x600) layouts.
* **Units:** Switch between Metric (Liters/Kg/C) and Imperial (Gallons/Lb/F).
* **Pour Volume:** Define the size of a standard pour (e.g., 12oz or 500ml) for the "Pours Remaining" display.
* **Autostart:** Configure the Raspberry Pi to launch KegLevel automatically on boot.

[SECTION: workflow]
## KegLevel Workflow ##

A digital whiteboard for your brewing pipeline.

Track what is **On Deck**, **Fermenting**, or **Lagering** so you know exactly what is ready to replace a kicked keg. You can drag and drop items between columns or use the arrow buttons.

[SECTION: temp_log]
## Temperature Log ##

View historical temperature data including:
* Daily High/Low/Average
* Weekly trends
* Monthly statistics

Use **Reset Log** to clear this history if you move the sensor or change environments.

[SECTION: wiring]
## Wiring Diagram ##

Please refer to the image provided in the "Wiring Diagram" menu option for standard GPIO connections.

*(Note: Ensure your 10k pull-down resistors are correctly installed between the signal pin and ground to prevent phantom pours.)*
