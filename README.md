# anchor-remote
Raspberri Pi Flask application to remotely control a boat anchor via the WiFi connection to your smartphone


Purpose
-------
When you rent a (sail) boat and you are short on crew members, the skipper may need to both steer the boat and drop the anchor at the same time. When the boat is not equipped with an anchor remote control, this application may help you out. 

Anchor Remote Control using WiFi
--------------------------------
When you do not own the boat but still want to provide a remote control without having to install hardware, a Raspberri Pi may be a handy option. The idea is that you can hook-up the Raspberri Pi with a plug that fits into the socket for the hand held anchor control unit. Or you wire-up the Raspberri Pi to the solenoid (you would need to open a panel in the front of the boat to get to it) that controls the windlass electric motor. The solenoid is a relais designed to switch heavy electric loads. More on this later.

Raspberri Pi with relais board
------------------------------
A Raspberri Pi with WiFi and an additional relais board (Hardware on Top: HAT module) is used to provide the 'up' and 'down' commands to the solenoid, which will make the anchor go up or down. The WiFi unit of the Raspberri Pi is configured to transmit a signal (as a 'hot spot') rather than hook-up to a WiFi router. The Raspberri Pi then becomes a server that provides a WiFi network that you can connect to with your smartphone. A Flask application on the Raspberri Pi provides a web app that you access from your phone. The app allows you to operate the anchor remotely.

Flask app "Anchor Remote"
-------------------------
The Flask app uses the Raspberri *gpiozero* library to access the General Purpose Input/Output *gpio* interface of the Raspberri pi. In this way the (small) Raspberri relais board can be controlled. In turn the small Raspberri relais will control the (large) Solenoid. The app provides the user interface via the browser on your smartphone, after you have connected your phone to the Raspberri WiFi hotspot.

The Flask app supports the following:

* Maintain configuration options
* Maintain boat specific parameters (per boat)
* Set the target anchor chain length based on the anchor depth
* Start the anchor-down (or up) run which will work towards the target chain length
* Pause and resume the run
* Do small manual up or down adjustments
* View the anchor event history (per anchor site)
* Trigger a controlled shut down of the Raspberri Pi when done

Single user control
-------------------
The Flask app identifies a user only by its IP address (no username), which is the local IP address within the Raspberri WiFi network. The app allows only a single user to have control, others can only view. This will be the first user who accesses the app after startup of the Raspberri pi.

No user login
-------------
No user login is required for the Flask app. A login is aleady required to connect your smartphone to the Raspberri WiFi.


CPU temperature control
-----------------------
The Flask app includes logic to monitor the CPU temperature and trigger a fan to cool it down. When the relais board has three relais units, two are used for the anchor (up, down) and the third can be used to switch the fan. This is a miniature fan to be mounted on the Raspberri Pi housing.

Bootstrap HTML styling
----------------------
The HTML styling is provided by Bootstrap https://getbootstrap.com Because you may not have access to the Internet during operation, the Bootstrap CSS and JS files are downloaded to local files and saved to the *static* file folder. 

SQLite database
---------------
The app generates upon first use and subsequently uses a SQLite database. The configuration settings and anchor events are stored here. When you set a target length, you can define the anchor site name. The anchor events are related to the anchor sites. The database file is stored in a directory which you define in the file flaskconfig.py. Two paths are defined: one to use on the development server and one to use on the Raspberri pi. This is determined by the server name, in this case 'rpi5'. Change the flaskconfig.py to refelct your setup.

Flask app as a Python package
-----------------------------
The app is setup as Python package *anchorapp* with python code in the subdirectories *app_logic* and *models*, static files related to HTML rendering in *static* and HTML files in *templates*. The files __init__.py, __main__.py and flaskconfig.py are in the main directory *anchorapp*. Launch the application outside of the main directory by running run_anchor.py. On the Raspberri itself, run it with *sudo* because you will access the system level gpio pins.

Python version and python libraries
-----------------------------------
The Python source was developed with version 3.12 and the following Python libraries are required:

* flask
* SQLAlchemy
* Flask-SQLAlchemy
* WTForms
* flask-wtf
* gpiozero

Note: on the Raspberri Pi, the gpiozero library and flask are pre-installed. Installing gpiozero also in a Python virtual environment resulted in errors. Do not use a virtual environment on the Raspberri Pi. Instead install the SQLAlchemy libraries at operating system level with the following commands:

* ``sudo pip3 install SQLAlchemy --break-system-packages``
* ``sudo pip3 install Flask-SQLAlchemy --break-system-packages``

Hardware
--------
* A small computer capable of running Linux and driving a relais. Like a Raspberri Pi or Arduino. 
* A 64 GB microSD card for storage will be sufficient.
* A relais board with at least two relais units. If you have three units, you can also drive a fan to cool the CPU.
* A length of electrical cable (low voltage, low power) with three to five wires. Three to connect to the solenoid and an additional two to connect to the 12 / 24 power if you want to use the boat power instead of a 5 volt powerbank. 
* Optional : A housing to protect the combined computer board & relais board.
* Optional : A UBEC: DC/DC Step-Down Buck converter if you want to use the boat 12 or 24 volt power. It will convert down 5 volt that your computer board needs. Otherwise use a (phone) powerbank.
* Optional : A connector & socket if you want to be able to detach the wires that connect your computer board to the boat. Three pins if you only connect to the solenoid (common, up and down). Five pins if you also connect to the 12 or 24 volt power of the boat. Or even four pins, because the ‘common’ connection will usually be the plus 12 / 24 volt line.
* Optional : A connector that can be plugged into the socket where the wired anchor remote control is connected. Alternatively open a pannel on the inside of the boat to connect the wires directly to the solenoid and 12 / 24 volt power.
* Optional : Real Time Clock (RTC) rechargeable battery to keep the clock running while powered-off.
* Optional: PC Fan 25x25x10mm - 5V
* Optional: Some jump wires to connect the 5 volt pin to the relais to run the PC Fan.
* Optional: A small circuit breaker (switch) to insert in the connection of the UBEC to the input 5 volt pin of the computer board. If the UBEC is connected to the computer and you use the powerbank to supply power, the computer may not start. Disconnect the UBEC with the switch in that case.
* Optional: A Linux-compatible WiFi-adapter (like the Ax300 from BrosTrend) if you want to keep the built-in WiFi to hook up to a network and use this additional WiFi adapter as a transmitter (hot-spot).

Configure WiFi as a Hot-spot
----------------------------
On the Raspberri Pi (command line) issue the following command to start an interactive WiFi configuration: ``sudo nmtui``
* Select "Edit a connection"
* select your WiFi (adapter) and name it "Hotspot"
* change the SSID to for example "AnchorRemote"
* change the mode to "<Access Point>"
* set security to "<WPA & WPA2 Personal>"
* set a *password* and select <OK>.
Documentation about nmtui can be found here https://variwiki.com/index.php?title=Wifi_NetworkManager#Configuring_WiFi_Access_Point

Launch Flask app at startup
---------------------------
After you have installed the Python code on your Raspberri Pi, configure it to run the application at startup. Enter the command ``crontab -e`` and add the following line:
``@reboot sleep 20 && sudo python3 /home/<username>/run_anchor.py`` where you replace <username> with your username.

Find the process with ``htop`` or ``ps -U root -u root u | grep py``
