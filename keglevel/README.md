## 💻 KegLevel Monitor Project

The **KegLevel** Monitor allows homebrewers to monitor and track the level of beer in their kegs. Up to 10 kegs are supported. Robust email notifications allow flexible remote monitoring.

Currently tested only on the Raspberry Pi 3B running Trixie and Bookworm. Should work with RPi4 and RPi5 running the same OS's but not yet tested.

Please **donate $$** if you use the app. See "Support the app" under the Settings & Info menu.

There is also a **🔗 [Fermentation Vault Project](https://github.com/keglevelmonitor/fermvault)** project in the repository. The FermVault app monitors the temperature of a fermenting product (beer, wine, mead, etc.) inside a refrigerator or freezer. The app turns the refrigerator/freezer on or off, and optionally a heater on or off, to maintain a consistent fermentation temperature. The temperature of the fermenting product can be used as the control-to point. PID regulation ensures accurate temperature control with very little or no overshoot or undershoot of the setpoint temperature. Robust email notifications allow flexible remote monitoring and remote email control of the FermVault system. 



## To Install the KegLevel App

Open **Terminal** and run this command. Type carefully and use proper upper/lowercase because it matters:

```bash
bash <(curl -sL bit.ly/keglevel)
```

That's it! You will now find "KegLevel Monitor" in your application menu under **Other**. You can use the "Check for Updates" action inside the app to install future updates.

## 🔗 Detailed installation instructions

Refer to the detailed installation instructions for specific hardware requirements and a complete wiring & hookup instructions:

👉 (placeholder for installation instructions)

## ⚙️ Summary hardware requirements

Required
* Raspberry Pi 3B (should work on RPi 4 but not yet tested)
* Debian Trixie OS (not tested on any other OS)
* GREDIA hall effect flow meter(s)
* 10k pull-up resistors
* Twisted-pair wiring from RPi to flow sensors (such as Cat6 cabling)
* (optional) DS18B20 temperature sensor & 4.7k pull-up resistor for temperature monitoring

Optional wiring components for ease of wiring, eliminates soldering:
* RPi terminal block HAT (very helpful for ease of wiring)
* JST XH connector wiring harnesses (very helpful for ease of wiring)
* RJ-45 screw terminal adapter (panel mount)
* RJ-45 screw terminal adapter (discrete)
* Solderless butt connectors
* Project box for mounting RPi with terminal HAT & RJ-45 adapter(s)

## ⚡ Quick Wiring Diagram

Here is a quick wiring diagram showing the logical connections of the system's compenents:
![Wiring Diagram for KegLevel Monitor](src/assets/wiring.gif)


## ⚙️ For reference
Installed file structure:

```
~/keglevel/
├── .gitignore
├── setup.sh
├── install.sh
├── keglevel.desktop
├── LICENSE
├── README.md
├── requirements.txt
├── update.sh
│
├── src/
│   ├── main.py
│   ├── notification_service.py
│   ├── popup_manager_mixin.py
│   ├── process_flow.py
│   ├── sensor_logic.py
│   ├── settings_manager.py
│   ├── temperature_manager.py
│   ├── ui_manager.py
│   ├── ui_manager_base.py
│   │
│   └── assets/
│        ├── changelog.txt
│        ├── help.md
│        ├── beer-keg.png
│        ├── support.gif
│        ├── wiring.gif
│        ├── bjcp_2015_library.json
│        └── bjcp_2021_library.json
│
├── venv/
│   ├── (installed dependencies)
│   ├── rpi-lgpio
│            
~/keglevel-data/
    ├── beverages_library.json
    ├── keg_library.json
    ├── process_flow.json
    ├── settings.json
    └── temperature_log.json
    
System-level dependencies installed via sudo apt outside of venv:
sudo apt-get install -y python3-tk python3-dev swig python3-venv liblgpio-dev

```


