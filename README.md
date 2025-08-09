RMS_telemetry
#############
Basic telemetry web service for the RPi Meteor Station (RMS) that polls the logs
every 60 s to provide a snapshot of what is going on.

Usage
-----
```
python3 RMS_telemetry.py --log-dir=your_RMS_data_log_directory_here
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
