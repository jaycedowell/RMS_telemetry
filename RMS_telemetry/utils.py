import os
import glob
import time
from datetime import datetime
from functools import lru_cache, wraps

from typing import Optional, Union


__all__ = ['get_archive_dir', 'get_capture_dir', 'get_frames_dir',
           'datetime_to_iso', 'timestamp_to_iso', 'now_as_iso', 'iso_age',
           'timestamp_to_rfc2822', 'timed_lru_cache']


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


def iso_age(iso: str) -> float:
    """
    Given a ISO8601 time, figure out how old the timestamp is and return that
    value in seconds.
    
    .. note:: Negative age = time is in the future
    """
    
    now = datetime.utcnow()
    try:
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%sZ")
    age = now - dt
    return age.total_seconds()


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


def get_frames_dir(log_dir: str, date: Optional[str]=None) -> Optional[str]:
    """
    Given a path to location of the RMS logs and, optionally a date in YYYYMMDD
    format, return the corresponding frames files directory.  Return None if
    the directory cannot be determined.
    """
    
    data_dir = os.path.join(log_dir, '..', 'FramesFiles')
    data_dir = os.path.abspath(data_dir)
    
    parent_path = data_dir
    latest_entry = None
    for depth in range(3):
        entries = glob.glob(os.path.join(parent_path, '*'))
        if date:
            if depth == 0:
                entries = list(filter(lambda x: x.find(date[:4]) != -1, entries))
            else:
                entries = list(filter(lambda x: x.find(date) != -1, entries))
            
        latest_mtime = 0
        for entry in entries:
            if not os.path.isdir(entry):
                continue
                
            mtime = os.path.getmtime(entry)
            if mtime > latest_mtime:
                latest_entry = entry
                latest_mtime = mtime
                
        parent_path = os.path.join(parent_path, os.path.basename(latest_entry))
            
    return latest_entry


def timed_lru_cache(seconds: int=600, maxsize: int=8):
    def decorator(func):
        func = lru_cache(maxsize=maxsize)(func)
        func.lifetime = seconds
        func.expiration = time.time() + func.lifetime

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Check if cache has expired
            if time.time() >= func.expiration:
                func.cache_clear()
                func.expiration = time.time() + func.lifetime
            return func(*args, **kwargs)

        return wrapper
    return decorator
