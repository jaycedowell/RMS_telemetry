import os
import glob
import time
import subprocess
from datetime import datetime

from typing import Optional, Dict, Any, Union


__all__ = ['get_archive_dir', 'get_capture_dir', 'get_disk_info',
           'datetime_to_iso', 'timestamp_to_iso', 'now_as_iso',
           'timestamp_to_rfc2822']


def datetime_to_iso(dt: datetime) -> str:
    """
    Convert a datetime instance into a ISO8601 format that doesn't contain
    fractions of a second.
    """
    
    iso = dt.isoformat()
    iso = iso.rsplit('.')[0]
    return iso+'Z'


def timestamp_to_iso(ts: Union[int,float]) -> str:
    """
    Convert a UNIX timestamp into a ISO8601 format that doesn't contain
    fractions of a second.
    """
    dt = datetime.utcfromtimestamp(ts)
    return datetime_to_iso(dt)


def now_as_iso() -> str:
    """
    Return the current time as a ISO8601 format that doesn't contain fractions
    of a second.
    """
    
    return timestamp_to_iso(time.time())


def timestamp_to_rfc2822(ts: Union[int,float]) -> str:
    """
    Convert a UNIX timestamp into a RFC2822 time.
    """
    
    dt = datetime.utcfromtimestamp(ts)
    return dt.strftime('%a, %d %b %Y %X %z')


def get_archive_dir(log_dir: str, date: Optional[str]=None) -> Optional[str]:
    """
    Given a path to location of the RMS logs and, optionally a date in YYYYMMDD
    format, return the corresponding archive directory.  Return None if the
    directory cannot be determined.
    """
    
    data_dir = os.path.join(log_dir, '..', 'ArchivedFiles')
    data_dir = os.path.abspath(data_dir)
    
    entries = glob.glob(os.path.join(data_dir, '*'))
    if date:
        entries = list(filter(lambda x: x.find(date) != -1, entries))
        
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


def get_capture_dir(log_dir: str, date: Optional[str]=None) -> Optional[str]:
    """
    Given a path to location of the RMS logs and, optionally a date in YYYYMMDD
    format, return the corresponding captured files directory.  Return None if
    the directory cannot be determined.
    """
    
    data_dir = os.path.join(log_dir, '..', 'CapturedFiles')
    data_dir = os.path.abspath(data_dir)
    
    entries = glob.glob(os.path.join(data_dir, '*'))
    if date:
        entries = list(filter(lambda x: x.find(date) != -1, entries))
        
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


def get_disk_info(log_dir: str, data: Optional[Dict[str,Any]]=None) -> Dict[str,Any]:
    """
    Poll the disk usage associated with the log directory and return the results
    as a dictionary.  If the data keyword is not None then the output dictionary
    will contain an updated version of the input.
    """
    
    if data is None:
        data = {'disk': {}}
    if 'disk' not in data:
        data['disk'] = {}
        
    try:
        dt = now_as_iso()
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
