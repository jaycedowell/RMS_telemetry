import os
import glob
import mimetypes

from .utils import get_archive_dir, get_frames_dir, timestamp_to_rfc2822, timed_lru_cache

from typing import Optional, Dict, Any

__all__ = ['get_radiants', 'get_stack', 'get_image', 'get_image_data']


@timed_lru_cache(seconds=300)
def get_radiants(log_dir: str, date: Optional[str]=None) -> Optional[str]:
    """
    Given a path to location of the RMS logs and, optionally a date in YYYYMMDD
    format, return the filename of the corresponding _radiants.png file.  If a
    date is not provided then the most recent file is returned.  Returns None if
    the image cannot be found.
    """
    
    data_dir = get_archive_dir(log_dir, date=date)
    
    radiants_image = None
    if data_dir:
        radiants_image = os.path.basename(data_dir)
        radiants_image += '_radiants.png'
        radiants_image = os.path.join(data_dir, radiants_image)
        if not os.path.exists(radiants_image):
            radiants_image = None
            
    return radiants_image


@timed_lru_cache(seconds=300)
def get_stack(log_dir: str, date: Optional[str]=None) -> Optional[str]:
    """
    Given a path to location of the RMS logs and, optionally a date in YYYYMMDD
    format, return the filename of the corresponding _stack_*_meteors.jpg file.
    If a date is not provided then the most recent file is returned.  Returns
    None if the image cannot be found.
    """
    
    data_dir = get_archive_dir(log_dir, date=date)
    
    stack_image = None
    if data_dir:
        stack_image = os.path.basename(data_dir)
        stack_image += '_stack_*_meteors.jpg'
        stack_image = os.path.join(data_dir, stack_image)
        files = glob.glob(stack_image)
        if files:
            stack_image = files[-1]
            
    return stack_image


@timed_lru_cache(seconds=10)
def get_image(log_dir: str, date: Optional[str]=None) -> Optional[str]:
    """
    Given a path to location of the RMS logs and, optionally a date in YYYYMMDD
    format, return the filename of the most recent JPEG image.  If a date is not
    provided then the most recent file is returned.  Returns None if the image
    cannot be found.
    """
    
    data_dir = get_frames_dir(log_dir, date=date)
    
    latest_image = None
    if data_dir:
        files = glob.glob(os.path.join(data_dir, '*.jpg'))
        files.sort()
        if files:
            latest_image = files[-1]
            
    return latest_image


@timed_lru_cache(seconds=300)
def get_image_data(filename: str) -> Dict[str,Any]:
    """
    Given a filename that points to an image, load the image and return a
    dictionary containing the image content type and data.  Returns and empty
    dictionary if the file doesn't exist.
    """
    
    data = {}
    if os.path.exists(filename):
        try:
            ct, en = mimetypes.guess_file_type(filename)
        except AttributeError:
            ct, en = mimetypes.guess_type(filename)
        data['content-type'] = ct
        data['content-encoding'] = en
        data['last-modified'] = timestamp_to_rfc2822(os.path.getmtime(filename))
        with open(filename, 'rb') as fh:
            data['data'] = fh.read()
            
    return data
