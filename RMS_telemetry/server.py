import os
import re
import copy
import json
import threading
from collections import deque
from datetime import datetime, timedelta

from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from socketserver import BaseRequestHandler
from urllib.parse import unquote_plus

from .static import get_asset, get_asset_data
from .images import get_radiants, get_stack, get_image, get_image_data, fits_to_movie
from .data import get_meteor_details, get_meteor_fits_file
from .utils import timestamp_to_iso, iso_to_timestamp, timestamp_to_rfc2822, get_archive_dir
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
        self._last_modified = _DUMMY_TIME
        self._previous_data = deque([], self._max_history)
        self._previous_last_modified = _DUMMY_TIME
        self._system_data = {}
        self._system_last_modified = _DUMMY_TIME
        self._lock = threading.RLock()
        
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
        
    @property
    def last_modified(self):
        """
        Return a RFC2822 time of when the main data structure was last modified.
        """
        
        return self._last_modified
        
    @property
    def previous_last_modified(self):
        """
        Return a RFC2822 time of when the history data structure was last modified.
        """
        
        return self._previous_last_modified
        
    @property
    def system_last_modified(self):
        """
        Return a RFC2822 time of when the system data structure was last modified.
        """
        
        return self._system_last_modified
        
    def set_data(self, data_obj: Dict[str,Any]):
        """
        Update the state with the most recent data.
        """
        
        with self._lock:
            if 'end_of_day' in data_obj:
                if data_obj['end_of_day']:
                    self._previous_data.append(copy.deepcopy(self._data))
                    try:
                        updated = max([self._data[key]['updated'] for key in ('capture', 'detections', 'camera', 'upload') if key in self._data and 'updated' in self._data[key]])
                    except ValueError:
                        updated = _DUMMY_TIME
                    updated = iso_to_timestamp(updated)
                    self._previous_last_modified = timestamp_to_rfc2822(updated)
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
                        data_obj['upload']['attempted'] = []
                        data_obj['upload']['completed'] = []
                        
                    for llevel in ('error', 'critical'):
                        if llevel in data_obj:
                            del data_obj[llevel]
                            
            self._data = data_obj
            try:
                updated = max([data_obj[key]['updated'] for key in ('capture', 'detections', 'camera', 'upload') if key in data_obj and 'updated' in data_obj[key]])
            except ValueError:
                updated = _DUMMY_TIME
            updated = iso_to_timestamp(updated)
            self._last_modified = timestamp_to_rfc2822(updated)
            
    def get_data(self) -> Dict[str,Any]:
        """
        Return the most recent state.
        """
        
        with self._lock:
            return copy.deepcopy(self._data)
            
    def get_previous_dates(self) -> List[str]:
        """
        Return a list of YYYYMMDD dates in the history.
        """
        
        with self._lock:
            dates = []
            for entry in self._previous_data:
                if 'capture' not in entry:
                    continue
                if 'started' not in entry['capture']:
                    continue
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
        
        with self._lock:
            if self._previous_data:
                if date is None:
                    return self._previous_data[-1]
                else:
                    for entry in self._previous_data:
                        if 'capture' in entry and 'started' in entry['capture']:
                            if entry['capture']['started'].replace('-', '').startswith(date):
                                return entry
        return None
        
    def set_system_data(self, data_obj: Dict[str,Any]):
        with self._lock:
            self._system_data = data_obj
            try:
                updated = max([data_obj[key]['updated'] for key in ('system', 'memory', 'network', 'disk') if key in data_obj and 'updated' in data_obj[key]])
            except ValueError:
                updated = _DUMMY_TIME
            updated = iso_to_timestamp(updated)
            self._system_last_modified = timestamp_to_rfc2822(updated)
            
    def get_system_data(self) -> Dict[str,Any]:
        with self._lock:
            return copy.deepcopy(self._system_data)
        
    def run(self):
        """
        Start the server thread.
        """
        
        server_thread = threading.Thread(target=self.serve_forever)
        server_thread.daemon_threads = True
        server_thread.start()


# RegEx to match a GET request
_getRE = re.compile(r'GET (/.*?(\?.*)?) HTTP.+')


class URLNotFoundError(RuntimeError):
    """
    Exception class for when a request would return a 404.
    """
    
    pass


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
            params = {entry.split('=')[0]: unquote_plus(entry.split('=')[1]) for entry in params}
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
            req = '/index.html'
        elif req == '/favicon.ico':
            req = '/images/favicon.ico'
        elif req == '/previous/details.html':
            req = '/details.html'
            
        try:
            handler = self._handlers[req]
            handler(self, params)
            
        except KeyError:
            self.get_static_asset(req, params)
            
        except URLNotFoundError:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()

            self.wfile.write(bytes('The requested URL was not found on this server because a capture is not active.', 'utf-8'))
            
        except Exception as e:
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            
            self.wfile.write(bytes('Internal Error - processing request', 'utf-8'))
            
    @HandlerRegistry.register('/latest')
    def get_latest_status(self, params: Dict[str,Any]):
        mtime = self.server.last_modified
        
        if self.headers.get('If-Modified-Since') == mtime:
            self.send_response(304)
            self.send_header('Last-Modified', mtime)
            self.send_header('Cache-Control', 'max-age=30, must-revalidate')
            self.end_headers()
            return
            
        data = self.server.get_data()
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Last-Modified', mtime)
        self.send_header('Cache-Control', 'max-age=30, must-revalidate')
        self.end_headers()

        self.wfile.write(bytes(json.dumps(data), "utf-8"))
        self.wfile.flush()
        
    @HandlerRegistry.register('/latest/image')
    def get_latest_image(self, params: Dict[str,Any]):
        filename = get_image(self.server.log_dir)
        if filename is None:
            raise URLNotFoundError()
            
        mtime = os.path.getmtime(filename)
        mtime = timestamp_to_rfc2822(mtime)
        
        if self.headers.get('If-Modified-Since') == mtime:
            self.send_response(304)
            self.send_header('Last-Modified', mtime)
            self.send_header('Cache-Control', 'max-age=30, must-revalidate')
            self.end_headers()
            return
            
        data = get_image_data(filename)
        
        self.send_response(200)
        self.send_header('Content-Type', data['content-type'])
        self.send_header('Last-Modified', data['last-modified'])
        self.send_header('Cache-Control', 'max-age=30, must-revalidate')
        self.end_headers()
        
        self.wfile.write(data['data'])
        self.wfile.flush()
        
    @HandlerRegistry.register('/system')
    def get_latest_system(self, params: Dict[str,Any]):
        mtime = self.server.system_last_modified
        
        if self.headers.get('If-Modified-Since') == mtime:
            self.send_response(304)
            self.send_header('Last-Modified', mtime)
            self.send_header('Cache-Control', 'max-age=30, must-revalidate')
            self.end_headers()
            return
            
        data = self.server.get_system_data()
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Last-Modified', mtime)
        self.send_header('Cache-Control', 'max-age=30, must-revalidate')
        self.end_headers()

        self.wfile.write(bytes(json.dumps(data), "utf-8"))
        self.wfile.flush()
        
    @HandlerRegistry.register('/previous')
    def get_previous_status(self, params: Dict[str,Any]):
        date = None
        if 'date' in params:
            date = str(params['date'])
            
        mtime = self.server.previous_last_modified
        
        if self.headers.get('If-Modified-Since') == mtime:
            self.send_response(304)
            self.send_header('Last-Modified', mtime)
            self.send_header('Cache-Control', 'max-age=300, must-revalidate')
            self.end_headers()
            return
            
        data = self.server.get_previous_data(date=date)
        if data is None:
            raise URLNotFoundError()
            
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Last-Modified', mtime)
        self.send_header('Cache-Control', 'max-age=300, must-revalidate')
        self.end_headers()

        self.wfile.write(bytes(json.dumps(data), "utf-8"))
        self.wfile.flush()
        
    @HandlerRegistry.register('/previous/dates')
    def get_previous_dates(self, params: Dict[str,Any]):
        mtime = self.server.previous_last_modified
        
        if self.headers.get('If-Modified-Since') == mtime:
            self.send_response(304)
            self.send_header('Last-Modified', mtime)
            self.send_header('Cache-Control', 'max-age=300, must-revalidate')
            self.end_headers()
            return
            
        data = self.server.get_previous_dates()
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Last-Modified', mtime)
        self.send_header('Cache-Control', 'max-age=300, must-revalidate')
        self.end_headers()

        self.wfile.write(bytes(json.dumps(data), "utf-8"))
        self.wfile.flush()
        
    @HandlerRegistry.register('/previous/radiants')
    def get_previous_radiants(self, params: Dict[str,Any]):
        date = None
        if 'date' in params:
            date = str(params['date'])
            
        filename = get_radiants(self.server.log_dir, date=date)
        if filename is None:
            raise URLNotFoundError()
            
        mtime = os.path.getmtime(filename)
        mtime = timestamp_to_rfc2822(mtime)
        
        if self.headers.get('If-Modified-Since') == mtime:
            self.send_response(304)
            self.send_header('Last-Modified', mtime)
            self.send_header('Cache-Control', 'max-age=300, must-revalidate')
            self.end_headers()
            return
            
        data = get_image_data(filename)
        
        self.send_response(200)
        self.send_header('Content-Type', data['content-type'])
        self.send_header('Last-Modified', data['last-modified'])
        self.send_header('Cache-Control', 'max-age=300, must-revalidate')
        self.end_headers()
        
        self.wfile.write(data['data'])
        self.wfile.flush()
        
    @HandlerRegistry.register('/previous/image')
    def get_previous_image(self, params: Dict[str,Any]):
        date = None
        if 'date' in params:
            date = str(params['date'])
            
        filename = get_stack(self.server.log_dir, date=date)
        if filename is None:
            raise URLNotFoundError()
            
        mtime = os.path.getmtime(filename)
        mtime = timestamp_to_rfc2822(mtime)
        
        if self.headers.get('If-Modified-Since') == mtime:
            self.send_response(304)
            self.send_header('Last-Modified', mtime)
            self.send_header('Cache-Control', 'max-age=300, must-revalidate')
            self.end_headers()
            return
            
        data = get_image_data(filename)
        
        self.send_response(200)
        self.send_header('Content-Type', data['content-type'])
        self.send_header('Last-Modified', data['last-modified'])
        self.send_header('Cache-Control', 'max-age=300, must-revalidate')
        self.end_headers()
        
        self.wfile.write(data['data'])
        self.wfile.flush()
        
    @HandlerRegistry.register('/previous/details')
    def get_previous_details(self, params: Dict[str,Any]):
        date = None
        if 'date' in params:
            date = str(params['date'])
            
        mtime = self.server.previous_last_modified
        
        data = self.server.get_previous_data(date=date)
        if data is None:
            raise URLNotFoundError()
            
        station_id = data['station_id']
        started = data['capture']['started']
        date = started[:10].replace('-', '')
        n_meteor_final = data['detections']['n_meteor_final']
        data = get_meteor_details(self.server.log_dir, date=date)
        if data is None:
            raise URLNotFoundError()
            
        data = {'station_id': station_id,
                'capture_started': started,
                'n_meteor_final': n_meteor_final,
                'meteors': data
               }
        
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Last-Modified', mtime)
        self.send_header('Cache-Control', 'max-age=300, must-revalidate')
        self.end_headers()

        self.wfile.write(bytes(json.dumps(data), "utf-8"))
        self.wfile.flush()
        
    @HandlerRegistry.register('/previous/meteor')
    def get_previous_meteor(self, params: Dict[str,Any]):
        date = None
        duration = None
        format = 'png'
        if 'date' in params:
            date = str(params['date'])
        if 'duration' in params:
            duration = float(params['duration'])
        if 'format' in params:
            format = str(params['format'])
            
        if date is None:
            raise URLNotFoundError()
        if format not in ('png', 'mp4'):
            raise ValueError()
        format = '.' + format
            
        filename = get_meteor_fits_file(self.server.log_dir, date)
        if filename is None:
            raise URLNotFoundError()
            
        if format == '.mp4':
            filename = fits_to_movie(filename, tstart=date, duration=duration)
        data = get_image_data(filename.replace('.fits', format))
        if data is None:
            raise URLNotFoundError()
            
        self.send_response(200)
        self.send_header('Content-Type', data['content-type'])
        self.send_header('Last-Modified', data['last-modified'])
        self.send_header('Cache-Control', 'max-age=300, must-revalidate')
        self.end_headers()
        
        self.wfile.write(data['data'])
        self.wfile.flush()
        
    def get_static_asset(self, req: str, params: Dict[str,Any]):
        filename = get_asset(req)
        
        if filename:
            mtime = os.path.getmtime(filename)
            mtime = timestamp_to_rfc2822(mtime)
            
            if self.headers.get('If-Modified-Since') == mtime:
                self.send_response(304)
                self.send_header('Last-Modified', mtime)
                self.send_header('Cache-Control', 'max-age=600, must-revalidate')
                self.end_headers()
                return
                
            data = get_asset_data(filename)
            
            self.send_response(200)
            self.send_header('Content-Type', data['content-type'])
            if data['content-encoding'] is not None:
                self.send_header('Content-Encoding', data['content-encoding'])
            self.send_header('Last-Modified', data['last-modified'])
            self.send_header('Cache-Control', 'max-age=600, must-revalidate')
            self.end_headers()
            
            self.wfile.write(data['data'])
            
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()

            self.wfile.write(bytes('The requested URL was not found on this server.', 'utf-8'))
            
