import os
import glob
import numpy as np
import shutil
import tempfile
import mimetypes
import subprocess

from astropy.io import fits as astrofits

import matplotlib
matplotlib.use('Agg')
matplotlib.rcParams['savefig.pad_inches'] = 0
from matplotlib import pyplot as plt

from .utils import get_archive_dir, get_frames_dir, timestamp_to_rfc2822, timed_lru_cache

from typing import Optional, Dict, Any

__all__ = ['get_radiants', 'get_stack', 'get_image', 'get_image_data', 'get_fits_data',
           'fits_to_movie']


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


@timed_lru_cache(seconds=300)
def get_fits_data(filename: str) -> Dict[str,Any]:
    """
    Given a filename that points to a FITS image, load the MAXPIX frame, convert
    it to PNG, and return a dictionary containing the image content type and
    data.  Returns and empty dictionary if the file doesn't exist or if there
    was an error converting the image.
    """
    
    data = {}
    if os.path.exists(filename):
        tempdir = tempfile.mkdtemp()
        
        try:
            fits = astrofits(filename)
            maxpix = fits[1].data
            
            fig = plt.figure()
            ax = fig.gca()
            ax.clear()
            ax.imshow(maxpix, cmap='gray')
            ax.axis('off')
            plt.draw()
            fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
            plt.savefig(os.path.join(tempdir, 'frame.png'), bbox_inches='tight')
            
            data = get_image_data(os.path.join(tempdir, 'frame.png'))
            
        except Exception as e:
            data = {}
            
        finally:
            shutil.rmtree(tempdir)
            
    return data


def fits_to_movie(filename: str, persist: bool=False) -> Optional[str]:
    """
    Given the name of a FITS file, convert it into a movie and return the
    filename of that movie.  If the FITS file does not exist or the movie
    cannot be created None is returned instead.
    
    .. note:: The `persist` keyword changes the movie style to max hold so that
              the meteor trail persists until the end of the video.
    """
    
    mp4name = None
    if os.path.exists(filename):
        tempdir = tempfile.mkdtemp()
        
        try:
            mp4name = filename.replace('.fits', '.mp4')
            if not os.path.exists(mp4name):
                fits = astrofits(filename)
                nframe = fits[0].header['NFRAMES']
                maxpix = fits[1].data
                maxfrm = fits[2].data
                avgpix = fits[3].data
                stdpix = fits[4].data
                
                fig = plt.figure()
                ax = fig.gca()
                for i in range(nframe):
                    if persist:
                        frame = np.where(maxfrm <= i, maxpix, avgpix)
                    else:
                        frame = np.where(maxfrm == i, maxpix, avgpix)
                    ax.clear()
                    ax.imshow(frame, cmap='gray')
                    ax.axis('off')
                    plt.draw()
                    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
                    plt.savefig(os.path.join(tempdir, f"frame_{i:03d}.png"), bbox_inches='tight')
                    
                subprocess.check_call(['ffmpeg', '-i', os.path.join(tempdir, 'frame_%003d.png'),
                                       '-framerate', '25', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                                       mp4name])
                
        except Exception as e:
            print(f"WARNING: failed to convert FITS file to movie: {str(e)}")
            mp4name = None
            
        finally:
            shutil.rmtree(tempdir)
            
    return mp4name
