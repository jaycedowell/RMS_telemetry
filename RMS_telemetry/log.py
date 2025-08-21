import re
from collections import deque

from .utils import timestamp_to_iso, iso_to_timestamp, iso_age

from typing import Optional, Dict, Any

__all__ = ['parse_log_line']


# RegEx for parsing a line in the log
_logRE = re.compile(r'(?P<date>\d{4}/\d{2}/\d{2}) (?P<time>\d{2}:\d{2}:\d{2})-(?P<level>[A-Z]*?)-(?P<module>.*?)-line:(?P<line>\d+) - (?P<message>.*)')

# RegEx for parsing interesting lines in the "Observation Summary"
_obsRE = re.compile(r'^(?P<parameter>[a-z_]*)\s*: ?(?P<value>.*)')

# State variable to keep track of how the capture is progressing across files
_CAPTURE_STARTED = False

# Dummy time when we don't have a real time to report
_DUMMY_TIME = timestamp_to_iso(0)

# Pending camera info from Reprocess about the astronometry
_PENDING_CAMREA = None

# Line lookback state to help deal with determining when an observation summary
# was generated
_LOOKBACK_BUFFER = deque([], 5)

# State variable for processing converting the FITS file counters into a
# filled fraction
_EXPECTED_FITS = None


def parse_log_line(line: str, data: Optional[Dict[str,Any]]=None) -> Dict[str, Any]:
    """
    Given a line from the RMS log file, parse it and return a dictionary
    containing relavant information in that line.  If the data keyword is not
    None then the output dictionary will contain an updated version of the
    input.
    
    This functions works with log lines that look like:
      2025/08/09 13:19:51-INFO-EventMonitor-line:2144 - Next EventMonitor run : 13:49:51 UTC; 30.0 minutes from now
      2025/08/09 13:49:52-INFO-EventMonitor-line:2144 - Next EventMonitor run : 14:19:52 UTC; 30.0 minutes from now
      2025/08/09 13:49:52-INFO-EventMonitor-line:2148 - Next Capture start    : 02:26:43 UTC
      ...
      2025/08/10 00:50:23-INFO-EventMonitor-line:2146 - Next Capture start    : 02:26:43 UTC; 96.0 minutes from now
      
    As well as "Observation Summary" entries like:
      camera_fov_h                    : 88.58 
      camera_fov_v                    : 46.955651 
      camera_information              : 50H20L 
      camera_lens                     : 4mm 
    """
    
    global _CAPTURE_STARTED
    global _PENDING_CAMREA
    global _LOOKBACK_BUFFER
    global _EXPECTED_FITS
    
    if not data:
        data = {'capture': {},
                'detections': {},
                'camera': {},
                'upload': {}
               }
    for key in ('capture', 'detections', 'camera', 'upload'):
        if key not in data:
            data[key] = {}
            if key == 'detections':
                data[key]['n_star'] = 0
            if key == 'upload':
                data[key]['attempted'] = []
                data[key]['completed'] = []
                
    mtch = _logRE.search(line)
    if mtch:
        dt = f"{mtch.group('date')}T{mtch.group('time')}Z"
        dt = dt.replace('/', '-')
        llevel = mtch.group('level')
        mod = mtch.group('module')
        lnum = int(mtch.group('line'), 10)
        message = mtch.group('message')
        
        if mod == 'StartCapture':
            if message.startswith('Starting capture'):
                _CAPTURE_STARTED = True
                
                _, _, _, duration, _ = message.split(None)
                duration = float(duration)
                data['capture']['running'] = True
                data['capture']['duration_hr'] = duration
                data['capture']['started'] = dt
                data['capture']['latest_block'] = _DUMMY_TIME
                data['capture']['block_max_age_s'] = 0.0
                data['capture']['n_frames_dropped'] = 0
                data['capture']['latest_all_white'] = _DUMMY_TIME
                data['capture']['updated'] = dt
                data['detections']['n_meteor'] = 0
                data['detections']['last_meteor'] = _DUMMY_TIME
                data['detections']['n_meteor_final'] = 0
                data['detections']['updated'] = dt
                if 'next_start' in data['capture']:
                    del data['capture']['next_start']
            elif message.startswith('Ending capture...'):
                data['capture']['running'] = False
                data['capture']['updated'] = dt
            elif message.startswith('Next start time:'):
                if _CAPTURE_STARTED:
                    data['end_of_day'] = True
                    _CAPTURE_STARTED = False
                else:
                    _, nsdt = message.split(':', 1)
                    nsdt = nsdt.strip()
                    nsdt, _ = nsdt.rsplit('.', 1)
                    nsdt = nsdt.replace(' ', 'T')
                    nsdt += 'Z'
                    nsdt = nsdt.replace('/', '-')
                    
                    data['capture']['next_start'] = nsdt
                    data['capture']['updated'] = dt
                    
        elif mod == 'EventMonitor':
            if message.startswith('Next Capture start'):
                _, nst= message.split(':', 1)
                nst = nst.strip()
                nst, _ = nst.split(' UTC', 1)
                nsdt = f"{mtch.group('date')}T{nst}Z"
                nsdt = nsdt.replace('/', '-')
                
                age = iso_age(nsdt, ref=dt)
                if age > 0:
                    # Must be in the future
                    ts = iso_to_timestamp(nsdt)
                    ts += 86400
                    nsdt = timestamp_to_iso(ts)
                data['capture']['next_start'] = nsdt
                data['capture']['updated'] = dt
                
        elif mod == 'BufferedCapture':
            if message.startswith("Block's max frame age:"):
                _, bage, ndropped = message.split(':', 2)
                bage, _ = bage.split(None, 1)
                bage = float(bage)
                ndropped = int(ndropped)
                data['capture']['latest_block'] = dt
                data['capture']['block_max_age_s'] = bage
                data['capture']['n_frames_dropped'] = ndropped
                data['capture']['updated'] = dt
                
        elif mod == 'VideoExtraction':
            if message.find('frames are all white') != -1:
                data['capture']['latest_all_white'] = dt
                data['capture']['updated'] = dt
                
        elif mod == 'DetectStarsAndMeteors':
            if message.startswith('Detected stars:'):
                _, nstar = message.split(':', 1)
                nstar = int(nstar, 10)
                data['detections']['n_star'] = nstar
                data['detections']['updated'] = dt
            elif message.find('detected meteors:') != -1:
                _, nmeteor = message.rsplit(':', 1)
                nmeteor = int(nmeteor, 10)
                try:
                    data['detections']['n_meteor'] += nmeteor
                except KeyError:
                    data['detections']['n_meteor'] = nmeteor
                if nmeteor > 0:
                    data['detections']['last_meteor'] = dt
                data['detections']['updated'] = dt
                
        elif mod == 'MLFilter':
            if message.startswith('FTPdetectinfo filtered,'):
                nmeteor_final, _ = message.split('/', 1)
                _, nmeteor_final = nmeteor_final.rsplit(None, 1)
                nmeteor_final = int(nmeteor_final, 10)
                data['detections']['n_meteor_final'] = nmeteor_final
                data['detections']['updated'] = dt
                
        elif mod == 'Reprocess':
            if message.startswith('Astrometric calibration'):
                value = False
                if message.find('SUCCESSFUL') != -1:
                    value = True
                _PENDING_CAMREA = {'astrometry_good': value,
                                   'updated': dt}
                
        elif mod == 'UploadManager':
            if message.startswith('Starting upload of'):
                filename = os.path.basename(message.split()[-1])
                if filename in data['upload']['attempted']:
                    del data['upload']['attempted'][data['upload']['attempted'].index(filename)]
                data['upload']['attempted'].append(filename)
                data['upload']['updated'] = dt
            elif message.startswith('Upload successful!'):
                filename = data['upload']['attempted'].pop()
                data['upload']['completed'].append(filename)
                data['upload']['updated'] = dt
                
        if llevel in ('ERROR', 'CRITICAL'):
            llevel = llevel.lower()
            if llevel not in data:
                data[llevel] = []
            sline = line.strip()
            if sline not in data[llevel]:
                data[llevel].append(sline)
                
        _LOOKBACK_BUFFER.append(dt)
        
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
            elif param.startswith('jitter_quality'):
                data['camera']['jitter_quality'] = value
            elif param.startswith('photometry_good'):
                if _PENDING_CAMREA is not None:
                    data['camera']['astrometry_good'] = _PENDING_CAMREA['astrometry_good']
                    _PENDING_CAMREA = None
                data['camera']['photometry_good'] = value
            elif param.startswith('total_expected_fits'):
                _EXPECTED_FITS = value
            elif param.startswith('total_fits'):
                if _EXPECTED_FITS is not None:
                    data['camera']['fits_fill'] = value / _EXPECTED_FITS * 100.0
                    _EXPECTED_FITS = None
                    
            if _LOOKBACK_BUFFER:
                data['camera']['updated'] = _LOOKBACK_BUFFER[-1]
                
    return data
