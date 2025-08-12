import os
import glob
import mimetypes
from functools import lru_cache

from typing import Dict, Any, Optional

__all__ = ['STATIC_BASE_DIR', 'is_valid_asset', 'get_asset', 'get_asset_data']


# Base directory for static assets
STATIC_BASE_DIR = os.path.join(os.path.abspath(os.path.dirname(__file__)),
                               'assets')


@lru_cache(maxsize=32)
def is_valid_asset(filename: str) -> bool:
    """
    Helper function to verify if the requested filename is really a static asset
    file.
    """
    
    valid = False
    filename = os.path.abspath(filename)
    if os.path.commonpath([_STATIC_BASE_DIR, filename]) == _STATIC_BASE_DIR:
        if os.path.exits(filename):
            valid = True
            
    return valid


@timed_lru_cache(maxsize=32)
def get_asset(request_path: str) -> Optional[str]:
    """
    Given a request path for a static asset, validate that that it is a valid 
    asset and return the actual filename .  Returns None if the asset cannot be
    found.
    """
    
    filename = os.path.join(STATIC_BASE_DIR, request_path)
    if not is_valid_asset(filename):
        filename = None
        
    return filename


@timed_lru_cache(maxsize=32)
def get_asset_data(filename: str) -> Dict[str,Any]:
    """
    Given a filename that supposedly points to a static file, validate that it
    really is a static file, and then load the file and return a dictionary
    containing the file's content type and data.  Returns and empty dictionary
    if the file doesn't exist.
    """
    
    data = {}
    
    if is_valid_asset(filename):
        ct, en = mimetypes.guess_file_type(filename)
        data['content-type'] = ct
        data['content-encoding'] = en
        data['last-modified'] = timestamp_to_rfc2822(os.path.getmtime(filename))
        with open(filename, 'rb') as fh:
            data['data'] = fh.read()
            
    return data
