#!/usr/bin/env python3

"""
Basic telemetry web server that reports what's in the logs
"""

import os
import glob
import time
import argparse

from RMS_telemetry.server import TelemetryServer
from RMS_telemetry.log import parse_log_line
from RMS_telemetry.utils import *
from RMS_telemetry.system import *

from typing import Dict, Any, Optional


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='run a simple telemetry server to monitor the logs on a RMS', 
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
    parser.add_argument('--ip', type=str, default='0.0.0.0',
                        help='IP address to bind to')
    parser.add_argument('--port', type=int, default=5000,
                        help='port to bind to')
    parser.add_argument('-d', '--log-dir', type=str, default='/home/rms/RMS_data/logs/',
                        help='log directory to watch')
    args = parser.parse_args()
    
    # Make sure we have a directory
    if not os.path.exists(args.log_dir):
        raise RuntimeError(f"Log directory '{args.log_dir}' does not exist")
    args.log_dir = os.path.abspath(args.log_dir)
    if not os.path.isdir(args.log_dir):
        raise RuntimeError(f"Log directory '{args.log_dir}' is not a directory")
        
    # Setup the server
    server = TelemetryServer(args.ip, args.port, args.log_dir)
    data = server.get_data()
    
    # Load in the disk info
    tDisk = 0.0
    try:
        new_data = get_disk_info(args.log_dir)
        tDisk = time.time()
        data['disk'] = new_data
        
    except Exception as e:
        print(f"WARNING: failed to parse the most disk usage info: {str(e)}")
        
    # Load in the old logs
    t0 = time.time()
    lognames = glob.glob(os.path.join(args.log_dir, 'log_*.log'))
    logages = [t0 - os.path.getmtime(logname) for logname in lognames]
    while lognames:
        oldest = logages.index(max(logages))
        logcurr = lognames[oldest]
        if len(lognames) > 7:
            print(f"Skipping log '{os.path.basename(logcurr)}'...")
        else:
            print(f"Parsing log '{os.path.basename(logcurr)}'...")
            
            code = os.path.basename(logcurr)
            _, code, _ = code.split('_', 2)
            data['station_id'] = code
            
            with open(logcurr, 'r') as fh:
                for line in fh:
                    try:
                        data = parse_log_line(line, data=data)
                    except Exception as e:
                        print(f"WARNING: failed to parse log '{os.path.basename(logcurr)}': {str(e)}")
                        
            server.set_data(data)
            
        del lognames[oldest]
        del logages[oldest]
        
    # Now that we've loaded what we can, start the server
    server.set_data(data)
    server.run()

    print(f"Started server on {server.ip}, port {server.port}")
    print("Press ctrl-C to exit")
    try:
        while True:
            t0 = time.time()
            
            lognames = glob.glob(os.path.join(args.log_dir, '_*.log'))
            if not lognames:
                time.sleep(60)
                continue
                
            logages = [t0 - os.path.getmtime(logname) for logname in lognames]
            logcurr = lognames[logages.index(min(logages))]
            
            try:
                code = os.path.basename(logcurr)
                _, code, _ = code.split('_', 2)
                
                latest = subprocess.check_output(['tail', '-n100', logcurr],
                                                 text=True)
                                                 
                data = server.get_data()
                data['station_id'] = code
                
                for line in latest.split('\n'):
                    data = parse_log_line(line, data=data)
                    
                if t0 - tDisk > 1800:
                    try:
                        new_data = get_disk_info(args.log_dir)
                        data['disk'] = new_data
                    except Exception as e:
                        print(f"WARNING: failed to parse the most disk usage info: {str(e)}")
                        
                server.set_data(data)
                             
            except subprocess.CalledProcessError as e:
                print(f"WARNING: failed to poll the most recent log: {str(e)}")
            except Exception as e:
                print(f"WARNING: failed to parse the most recent log: {str(e)}")
                
            t1  = time.time()
            tSleep = 120 - (t1 - t0)
            while tSleep > 1:
                time.sleep(1)
                t1  = time.time()
                tSleep = 120 - (t1 - t0)
                
    except KeyboardInterrupt:
        print("Stopping server..")
        
    server.shutdown() 
    print("Server stopped.") 
