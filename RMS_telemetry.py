#!/usr/bin/env python3

"""
Basic telemetry web server that reports what's in the logs
"""

import os
import re
import copy
import glob
import json
import time
import threading
import subprocess
import argparse

from collections import deque

from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from socketserver import BaseRequestHandler

from typing import Dict, Any, Optional

# Example log entries
"""
2025/08/09 13:19:51-INFO-EventMonitor-line:2144 - Next EventMonitor run : 13:49:51 UTC; 30.0 minutes from now
2025/08/09 13:49:52-INFO-EventMonitor-line:2144 - Next EventMonitor run : 14:19:52 UTC; 30.0 minutes from now
2025/08/09 13:49:52-INFO-EventMonitor-line:2148 - Next Capture start    : 02:26:43 UTC
"""

# Example observation summary
"""
Observation Summary
===================

camera_fov_h                    : 88.58 
camera_fov_v                    : 46.955651 
camera_information              : 50H20L 
camera_lens                     : 4mm 
camera_pointing_alt             : 50.15 degrees 
camera_pointing_az              : 334.15 degrees 
capture_duration_from_fits      : 33971.297 
captured_directories            : 7 
clock_error_seconds             : 0.4 
clock_synchronized              : yes 
"""

# RegEx for parsing a line in the log
_logRE = re.compile(r'(?P<date>\d{4}/\d{2}/\d{2}) (?P<time>\d{2}:\d{2}:\d{2})-(?P<level>[A-Z]*?)-(?P<module>.*?)-line:(?P<line>\d+) - (?P<message>.*)')

# RegEx for parsing interesting lines in the "Observation Summary"
_obsRE = re.compile(r'^(?P<parameter>[a-z_]*)\s*: ?(?P<value>.*)')

_captureStarted = False

def parse_log_line(line: str, data: Optional[Dict[str,Any]]=None) -> Dict[str, Any]:
    """
    Given a line from the RMS log file, parse it and return a dictionary
    containing relavant information in that line.
    """
    
    global _captureStarted
    
    if not data:
        data = {'capture': {},
                'detections': {},
                'camera': {}
               }
    for key in ('capture', 'detections', 'camera'):
        if key not in data:
            data[key] = {}
            if key == 'detections':
                data[key]['n_star'] = 0
                
    mtch = _logRE.search(line)
    if mtch:
        dt = f"{mtch.group('date')}T{mtch.group('time')}Z"
        mod = mtch.group('module')
        lnum = int(mtch.group('line'), 10)
        message = mtch.group('message')
        
        data['updated'] = dt
        if mod == 'StartCapture':
            if message.startswith('Starting capture'):
                _captureStarted = True
                
                _, _, _, duration, _ = message.split(None)
                duration = float(duration)
                data['capture']['running'] = True
                data['capture']['duration_hr'] = duration
                data['capture']['started'] = dt
                data['capture']['block_max_age_s'] = 0.0
                data['capture']['n_frames_dropped'] = 0
                data['detections']['n_meteor'] = 0
                data['detections']['last_meteor'] = '1970/01/01T00:00:00Z'
                data['detections']['n_meteor_final'] = 0
            elif message.startswith('Ending capture...'):
                data['capture']['running'] = False
            elif message.startswith('Next start time:'):
                if _captureStarted:
                    data['end_of_day'] = True
                    _captureStarted = False
                    
        elif mod == 'BufferedCapture':
            if message.startswith("Block's max frame age:"):
                _, bage, ndropped = message.split(':', 2)
                bage, _ = bage.split(None, 1)
                bage = float(bage)
                ndropped = int(ndropped)
                data['capture']['block_max_age_s'] = bage
                data['capture']['n_frames_dropped'] = ndropped
                
        elif mod == 'DetectStarsAndMeteors':
            if message.startswith('Detected stars:'):
                _, nstar = message.split(':', 1)
                nstar = int(nstar, 10)
                data['detections']['n_star'] = nstar
            elif message.find('detected meteors:') != -1:
                _, nmeteor = message.rsplit(':', 1)
                nmeteor = int(nmeteor, 10)
                try:
                    data['detections']['n_meteor'] += nmeteor
                except KeyError:
                    data['detections']['n_meteor'] = nmeteor
                data['detections']['last_meteor'] = dt
                
        elif mod == 'MLFilter':
            if message.startswith('FTPdetectinfo filtered,'):
                nmeteor_final, _ = message.split('/', 1)
                _, nmeteor_final = nmeteor_final.rsplit(None, 1)
                nmeteor_final = int(nmeteor_final, 10)
                data['detections']['n_meteor_final'] = nmeteor_final
    else:
        mtch = _obsRE.search(line)
        if mtch:
            param, value = mtch.group('parameter'), mtch.group('value')
            value = value.rstrip()
            if value == 'True':
                value = True
            elif value == 'False':
                value = False
            else:
                try:
                    value = int(value, 10)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        pass
            if param.startswith('camera_'):
                _, param = param.split('_', 1)
                data['camera'][param] = value
            if param.startswith('photometry_good'):
                data['camera']['photometry_good'] = value
                
    return data


def get_disk_info(log_dir: str, data: Optional[Dict[str,Any]]=None) -> Dict[str,Any]:
    """
    Poll the disk usage associated with the log directory and return the results
    as a dictionary.
    """
    
    if data is None:
        data = {'disk': {}}
    if 'disk' not in data:
        data['disk'] = {}
        
    try:
        dt = datetime.utcnow().isoformat()
        dt, _ = dt.rsplit('.')
        dt += 'Z'
        info = subprocess.check_output(['df','-B1000', log_dir],
                                       text=True)
        for line in info.split('\n'):
            if line.startswith('Filesystem'):
                continue
            if len(line) < 3:
                continue
                
            _, total, used, free, _, _ = line.split(None, 5)
            total = int(total, 10) / 1000**2 # kB -> GB
            used = int(used, 10) / 1000**2 # kB -> GB
            free = int(free, 10) / 1000**2 # kB -> GB
            data['disk']['total_gb'] = total
            data['disk']['used_gb'] = used
            data['disk']['free_gb'] = free
            data['disk']['updated'] = dt
    except subprocess.CalledProcessError as e:
        print(f"WARNING: Failed to determine the disk usage: {str(e)}")
        
    return data


def get_latest_archive_dir(log_dir: str) -> Optional[str]:
    data_dir = os.path.join(log_dir, '..', 'ArchivedFiles')
    data_dir = os.path.abspath(data_dir)
    
    entries = glob.glob(os.path.join(data_dir, '*'))
    
    latest_entry = None
    latest_mtime = 0
    for entry in entries:
        if not os.path.isdir(entry):
            continue
            
        mtime = os.path.getmtime(entry)
        if mtime > latest_mtime:
            latest_entry = entry
            latest_mtime = mtime
            
    return latest_entry


def get_latest_radiants(log_dir: str) -> Optional[str]:
    data_dir = get_latest_archive_dir(log_dir)
    
    latest_radiants = None
    if data_dir:
        latest_radiants = os.path.basename(data_dir)
        latest_radiants += '_radiants.png'
        latest_radiants = os.path.join(data_dir, latest_radiants)
        if not os.path.exists(latest_radiants):
            latest_radiants = None
            
    return latest_radiants


def get_latest_capture_dir(log_dir: str) -> Optional[str]:
    data_dir = os.path.join(log_dir, '..', 'CapturedFiles')
    data_dir = os.path.abspath(data_dir)
    
    entries = glob.glob(os.path.join(data_dir, '*'))
    
    latest_entry = None
    latest_mtime = 0
    for entry in entries:
        if not os.path.isdir(entry):
            continue
            
        mtime = os.path.getmtime(entry)
        if mtime > latest_mtime:
            latest_entry = entry
            latest_mtime = mtime
            
    return latest_entry


def get_latest_image(log_dir: str) -> Optional[str]:
    data_dir = get_latest_capture_dir(log_dir)
    
    latest_image = None
    if data_dir:
        files = glob.glob(os.path.join(data_dir, '*.jpg'))
        files.sort()
        if files:
            latest_image = files[-1]
            
    return latest_image


class TelemetryServer(ThreadingHTTPServer):
    def __init__(self, ip: str, port: int, log_dir: str):
        super().__init__((ip, port), TelemetryHandler)
        self._ip = ip
        self._port = port
        self._log_dir = log_dir
        self._data = {}
        self._previous_data = deque([], 7)
        
    @property
    def ip(self):
        return self._ip
        
    @property
    def port(self):
        return self._port
        
    @property
    def log_dir(self):
        return self._log_dir
        
    def set_data(self, data_obj: Dict[str,Any]):
        if 'end_of_day' in data_obj:
            if data_obj['end_of_day']:
                self._previous_data.append(copy.deepcopy(self._data))
                del data_obj['end_of_day']
                
                if not data_obj['capture']['running']:
                    data_obj['capture']['duration_hr'] = 0.0
                    data_obj['capture']['started']: '1970/01/01T00:00:00Z'
                    data_obj['detections']['n_meteor'] = 0
                    data_obj['detections']['last_meteor'] = '1970/01/01T00:00:00Z'
                    data_obj['detections']['n_meteor_final'] = 0
        self._data = data_obj
        
    def get_data(self) -> Dict[str,Any]:
        return self._data
        
    def get_previous_data(self, date: Optional[str]=None) -> Optional[Dict[str,Any]]:
        if self._previous_data:
            if date is None:
                return self._previous_data[-1]
            else:
                for entry in self._previous_data:
                    if entry['capture']['started'].replace('/', '').startswith(date):
                        return entry
        return None
        
    def run(self):
        server_thread = threading.Thread(target=self.serve_forever)
        server_thread.daemon_threads = True
        server_thread.start()


class  TelemetryHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        m = re.search(r'GET (/.*?(\?.*)?) HTTP.+', self.requestline)
        if m:
            self.handle_request(m.group(1))
        else:
            self.send_response(500)
            self.wfile.write('Internal Error - parsing requestline')
            
    def handle_request(self, req: str):
        params = {}
        if req.find('?') != -1:
            req, params = req.split('?', 1)
            params = params.split('&')
            params = {entry.split('=')[0]: entry.split('=')[1] for entry in params}
            for key in params:
                value = params[key]
                if value.lower() == 'true':
                    value = True
                elif value.lower() == 'false':
                    value = False
                else:
                    try:
                        value = int(value, 10)
                    except ValueError:
                        try:
                            value = float(value)
                        except ValueError:
                            pass
                params[key] = value
                
        if req == '/':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            self.wfile.write(bytes(json.dumps(self.server.get_data()), "utf-8"))
            self.wfile.flush()
            
        elif req == '/previous':
            date = None
            if 'date' in params:
                date = params['date']
                
            data = self.server.get_previous_data(date=date)
            if data:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()

                self.wfile.write(bytes(json.dumps(data), "utf-8"))
            else:
                self.send_response(404)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()

                self.wfile.write(bytes('Not found', 'utf-8'))
            self.wfile.flush()
            
        elif req == '/latest/radiants':
            data = get_latest_radiants(self.server.log_dir)
            if data:
                self.send_response(200)
                self.send_header('Content-type', 'image/png')
                self.end_headers()
                
                with open(data, 'rb') as fh:
                    self.wfile.write(fh.read())
                    
            else:
                self.send_response(404)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()

                self.wfile.write(bytes('Not found', 'utf-8'))
            self.wfile.flush()
            
        elif req == '/latest/image':
            data = get_latest_image(self.server.log_dir)
            if data:
                self.send_response(200)
                self.send_header('Content-type', 'image/jpeg')
                self.end_headers()
                
                with open(data, 'rb') as fh:
                    self.wfile.write(fh.read())
                    
            else:
                self.send_response(404)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()

                self.wfile.write(bytes('Not found', 'utf-8'))
            self.wfile.flush()
            
        else:
            self.send_response(404)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()

            self.wfile.write(bytes('Not found', 'utf-8'))
            self.wfile.flush()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='run a simple telemetry server to monitor the logs on a RMS', 
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
    parser.add_argument('--ip', type=str, default='127.0.0.1',
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
        for key in new_data.keys():
            value = new_data[key]
            if isinstance(value, dict):
                try:
                    data[key].update(value)
                except KeyError:
                    data[key] = value
            else:
                data[key] = value
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
                        data = get_disk_info(args.log_dir, data=data)
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
