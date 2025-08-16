#!/usr/bin/env python3

"""
Basic telemetry web server that reports what's in the logs
"""

import os
import glob
import time
import argparse
import subprocess

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
    sys_data = server.get_system_data()
    
    # Load in the system, memory, network, and disk info
    tSys = tMem = tNet = tDisk = time.time()
    sys_data['system'] = get_system_info(args.log_dir)
    sys_data['memory'] = get_memory_info(args.log_dir)
    sys_data['network'] = get_network_info(args.log_dir)
    sys_data['disk'] = get_disk_info(args.log_dir)
    
    # Load in the old logs
    t0 = time.time()
    lognames = glob.glob(os.path.join(args.log_dir, 'log_*.log'))
    lognames.sort(key=os.path.getmtime)
    
    last_logfile = ''
    last_logpos = 0
    while lognames:
        last_logfile = logcurr = lognames[0]
        lognames = lognames[1:]
        if len(lognames) > 6:
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
                last_logpos = fh.tell()
                
            server.set_data(data)
            
    # Now that we've loaded what we can, start the server
    server.set_data(data)
    server.set_system_data(sys_data)
    server.run()

    print(f"Started server on {server.ip}, port {server.port}")
    print("Press ctrl-C to exit")
    try:
        while True:
            t0 = time.time()
            
            lognames = glob.glob(os.path.join(args.log_dir, 'log_*.log'))
            if not lognames:
                time.sleep(60)
                continue
                
            lognames.sort(key=os.path.getmtime)
            logcurr = lognames[-1]
            if logcurr != last_logfile:
                last_logfile = logcurr
                last_logpos = 0
                
            try:
                ## Part 1 - Log file
                ### Load what's new in the file
                code = os.path.basename(logcurr)
                _, code, _ = code.split('_', 2)
                
                data = server.get_data()
                data['station_id'] = code
                
                with open(logcurr, 'r') as fh:
                    fh.seek(last_logpos, 0)
                    open_size = os.path.getsize(logcurr)
                    
                    for line in fh:
                        data = parse_log_line(line, data=data)
                        last_logpos = fh.tell()
                        if last_logpos >= open_size:
                            break
                            
                ### Update
                server.set_data(data)
                
                try:
                    n_lines_parse = n_lines_parse_old
                    del n_lines_parse_old
                except NameError:
                    pass
                    
                ## Part 2 - System info
                ### Poll what needs to be polled
                new_sys_data = {}
                if t0 - tSys > 120:
                    try:
                        new_sys_data['system'] = get_system_info(args.log_dir)
                        tSys = t0
                    except Exception as e:
                        print(f"WARNING: failed to parse system status info: {str(e)}")
                if t0 - tMem > 300:
                    try:
                        new_sys_data['memory'] = get_memory_info(args.log_dir)
                        tMem = t0
                    except Exception as e:
                        print(f"WARNING: failed to parse memory info: {str(e)}")
                if t0 - tNet > 120:
                    try:
                        new_sys_data['network'] = get_network_info(args.log_dir)
                        tNet = t0
                    except Exception as e:
                        print(f"WARNING: failed to parse network info: {str(e)}")
                if t0 - tDisk > 1800:
                    try:
                        new_sys_data['disk'] = get_disk_info(args.log_dir)
                        tDisk = t0
                    except Exception as e:
                        print(f"WARNING: failed to parse disk usage info: {str(e)}")
                        
                ### Update but only if something's changed
                if new_sys_data:
                    sys_data = server.get_system_data()
                    sys_data.update(new_sys_data)
                    server.set_system_data(sys_data)
                    
            except Exception as e:
                print(f"WARNING: failed to parse the most recent log: {str(e)}")
                
            t1  = time.time()
            tSleep = 60 - (t1 - t0)
            while tSleep > 1:
                time.sleep(1)
                t1  = time.time()
                tSleep = 60 - (t1 - t0)
                
    except KeyboardInterrupt:
        print("Stopping server...")
        
    server.shutdown() 
    print("Server stopped") 
