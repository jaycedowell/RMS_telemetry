import os
import re
import copy
import json
import threading
from collections import deque

from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from socketserver import BaseRequestHandler
from urllib.parse import unquote_plus

from .images import get_radiants, get_image, get_image_data
from .utils import timestamp_to_iso, get_archive_dir
from .system import *

from typing import Optional, Dict, Any, List, Callable


__all__ = ['TelemetryServer', 'TelemetryHandler']


# Dummy time when we don't have a real time to report
_DUMMY_TIME = timestamp_to_iso(0)


class TelemetryServer(ThreadingHTTPServer):
    """
    HTTP server for telemetry data that handles not only the requests but also
    maintaing the history of the camera setup being monitored.  The size of the
    history (in days) is controlled by the `max_history` keyword.
    """
    
    def __init__(self, ip: str, port: int, log_dir: str, max_history: int=7,
                       handler:Optional["TelemetryHandler"]=None):
        if handler is None:
            handler = TelemetryHandler
        super().__init__((ip, port), handler)
        self._ip = ip
        self._port = port
        self._log_dir = log_dir
        self._max_history = max_history
        self._data = {}
        self._previous_data = deque([], self._max_history)
        
    @property
    def ip(self):
        """
        IP address the server is bound to.
        """
        
        return self._ip
        
    @property
    def port(self):
        """
        Port the server is bound to.
        """
        
        return self._port
        
    @property
    def log_dir(self):
        """
        Log directory the server is monitoring.
        """
        
        return self._log_dir
        
    def set_data(self, data_obj: Dict[str,Any]):
        """
        Update the state with the most recent data.
        """
        
        if 'end_of_day' in data_obj:
            if data_obj['end_of_day']:
                self._previous_data.append(copy.deepcopy(self._data))
                del data_obj['end_of_day']
                
                if not data_obj['capture']['running']:
                    data_obj['capture']['duration_hr'] = 0.0
                    data_obj['capture']['started'] = _DUMMY_TIME
                    data_obj['capture']['latest_block'] = _DUMMY_TIME
                    data_obj['capture']['block_max_age_s'] = 0.0
                    data_obj['capture']['n_frames_dropped'] = 0
                    data_obj['capture']['latest_all_white'] = _DUMMY_TIME
                    data_obj['detections']['n_meteor'] = 0
                    data_obj['detections']['last_meteor'] = _DUMMY_TIME
                    data_obj['detections']['n_meteor_final'] = 0
                    
                for llevel in ('error', 'critical'):
                    if llevel in data_obj:
                        del data_obj[llevel]
                        
        self._data = data_obj
        
    def get_data(self) -> Dict[str,Any]:
        """
        Return the most recent state.
        """
        
        return self._data
        
    def get_previous_dates(self) -> List[str]:
        """
        Return a list of YYYYMMDD dates in the history.
        """
        
        dates = []
        for entry in self._previous_data:
            date, _ = entry['capture']['started'].split('T', 1)
            dates.append(date.replace('-', ''))
            
        return dates
        
    def get_previous_data(self, date: Optional[str]=None) -> Optional[Dict[str,Any]]:
        """
        Return an entry from the history.  If `date` is not provided then the
        most recent entry is returned.  Otherwise, `data` is used to find the
        YYYYMMDD entry.  If there is no history or the specified date cannot be
        found None is returned.
        """
        
        if self._previous_data:
            if date is None:
                return self._previous_data[-1]
            else:
                for entry in self._previous_data:
                    if entry['capture']['started'].replace('-', '').startswith(date):
                        return entry
        return None
        
    def run(self):
        """
        Start the server thread.
        """
        
        server_thread = threading.Thread(target=self.serve_forever)
        server_thread.daemon_threads = True
        server_thread.start()


_getRE = re.compile(r'GET (/.*?(\?.*)?) HTTP.+')


class HandlerRegistry:
    """
    Helper class to make it easier to add new endpoints to a TelemetryHandler.
    """
    
    _handlers = {}
    
    @classmethod
    def register(cls: "HandlerRegistry", path: str) -> Callable:
        def wrapper(func):
            cls._handlers[path] = func
            return func
        return wrapper
        
    def __contains__(self, path: str) -> bool:
        return path in self._handlers
        
    def __getitem__(self, path: str) -> Callable:
        return self._handlers[path]


class  TelemetryHandler(BaseHTTPRequestHandler):
    """
    Request handler for TelemetryServer.
    """
    
    _handlers = HandlerRegistry()
    
    def do_GET(self):
        m = _getRE.search(self.requestline)
        if m:
            self.handle_request(m.group(1))
        else:
            self.send_response(500)
            self.wfile.write(bytes('Internal Error - parsing request', 'utf-8'))
            
    def handle_request(self, req: str):
        params = {}
        if req.find('?') != -1:
            req, params = req.split('?', 1)
            params = params.split('&')
            params = {entry.split('=')[0]: uquote_plus(entry.split('=')[1]) for entry in params}
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
                
        try:
            handler = self._handlers[req]
            handler(self, params)
            
        except KeyError:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()

            self.wfile.write(bytes('URL not found', 'utf-8'))
            
        except Exception as e:
            self.send_response(500)
            self.wfile.write('Internal Error - processing request')
            
    @HandlerRegistry.register('/')
    @HandlerRegistry.register('/index.html')
    def get_index(self, params: Dict[str,Any]):
        data = self.server.get_previous_data()
        station_id = data['station_id']
        country_code = station_id[:2]
        latest_archive = get_archive_dir(self.server.log_dir)
        latest_archive = os.path.basename(latest_archive)
        
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        
        self.wfile.write(bytes(f"""<html>
<body>
<h2>RMS Telemetry Server for {data['station_id']}</h2>
<h4>Current</h4>
<a href="/latest">Status</a><br />
<a href="/latest/image">Latest Image (only active when capturing)</a></br>
<a href="/system">System status</a><br />

<h4>Last Completed Run</h4>
<a href="/previous">Status</a><br />
<a href="/previous/radiants">Radiants image</a><br />
<a href="/previous/image">Stacked meteors image</a><br />
<a href="https://globalmeteornetwork.org/weblog/{country_code}/{station_id}/{latest_archive}_detected/">Weblog entry</a><br />

<h4>Telemetry History</h4>
<a href="/previous/dates">Listing of available dates</a><br />
</body>
</html>
        """, 'utf-8'))
        self.wfile.flush()
    
    @HandlerRegistry.register('/latest')
    def get_latest_status(self, params: Dict[str,Any]):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        self.wfile.write(bytes(json.dumps(self.server.get_data()), "utf-8"))
        self.wfile.flush()
        
    @HandlerRegistry.register('/latest/image')
    def get_latest_image(self, params: Dict[str,Any]):
        filename = get_image(self.server.log_dir)
        if filename and filename.find('stack') == -1:
            data = get_image_data(filename)
            
            self.send_response(200)
            self.send_header('Content-Type', data['content-type'])
            self.send_header('Last-Modified', data['last-modified'])
            self.end_headers()
            
            self.wfile.write(data['data'])
                
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()

            self.wfile.write(bytes('Capture is not active', 'utf-8'))
        self.wfile.flush()
        
    @HandlerRegistry.register('/system')
    def get_latest_system(self, params: Dict[str,Any]):
        data = {}
        data['system'] = get_system_info(self.server.log_dir)
        data['memory'] = get_memory_info(self.server.log_dir)
        data['disk'] = get_disk_info(self.server.log_dir)
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        self.wfile.write(bytes(json.dumps(data), "utf-8"))
        self.wfile.flush()
        
    @HandlerRegistry.register('/previous')
    def get_previous_status(self, params: Dict[str,Any]):
        date = None
        if 'date' in params:
            date = str(params['date'])
            
        data = self.server.get_previous_data(date=date)
        if data:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            self.wfile.write(bytes(json.dumps(data), "utf-8"))
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()

            self.wfile.write(bytes('URL not found', 'utf-8'))
        self.wfile.flush()
        
    @HandlerRegistry.register('/previous/dates')
    def get_previous_dates(self, params: Dict[str,Any]):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()

        self.wfile.write(bytes(json.dumps(self.server.get_previous_dates()), "utf-8"))
        self.wfile.flush()
        
    @HandlerRegistry.register('/previous/radiants')
    def get_previous_radiants(self, params: Dict[str,Any]):
        date = None
        if 'date' in params:
            date = params['date']
            
        filename = get_radiants(self.server.log_dir, date=date)
        if filename:
            data = get_image_data(filename)
            
            self.send_response(200)
            self.send_header('Content-Type', data['content-type'])
            self.send_header('Last-Modified', data['last-modified'])
            self.end_headers()
            
            self.wfile.write(data['data'])
                
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()

            self.wfile.write(bytes('Not found', 'utf-8'))
        self.wfile.flush()
        
    @HandlerRegistry.register('/previous/image')
    def get_previous_image(self, params: Dict[str,Any]):
        date = None
        if 'date' in params:
            date = params['date']
            
        filename = get_image(self.server.log_dir, date=date)
        if filename:
            data = get_image_data(filename)
            
            self.send_response(200)
            self.send_header('Content-Type', data['content-type'])
            self.send_header('Last-Modified', data['last-modified'])
            self.end_headers()
            
            self.wfile.write(data['data'])
                
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()

            self.wfile.write(bytes('URL not found', 'utf-8'))
        self.wfile.flush()
