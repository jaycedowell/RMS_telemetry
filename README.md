RMS_telemetry
=============
Basic telemetry web service for the RPi Meteor Station (RMS) that polls the logs
every 60 s to provide a snapshot of what is going on.

Usage
-----
For a default single camera RPi setup, clone to repository into `/home/rms`,
change into the `RMS_telemetry` directory, and run:
```
./RMS_telemetry.sh
```
This will start the default server listening on all network interfaces to port
5000.

For more control over where the server looks for log files or what IP address to
bind to you can directly call the Python script:
```
python3 RMS_telemetry.py --ip=192.168.1.32 --port 6032 --log-dir=your_RMS_data_log_directory_here
```

Endpoints
---------
 * /index.html - Landing page
 * /system - System status (disk and memory usage, CPU load, temperature)
 * /latest - Most recent log info
 * /latest/image - Most recent captured image
 * /previous - Summary of the previous completed capture
 * /previous/radiants - Radiants plot from the previous completed capture
 * /previous/image - Stacked image of detected meteors from the previous completed capture
 * /previous/dates - List of dates stored in the telemetry server's history

Autostart
---------
To automatically enable the server at boot, add the following to the end of 
`/etc/xdg/lxsession/LXDE-pi/autostart`:
```
# Run the telemetry server
sleep 10
@lxterminal -e "/home/rms/RMS_telemetry/RMS_telemetry.sh"
```
Be sure to update the path to `RMS_telemetry.sh` to match where the software
lives.
