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
