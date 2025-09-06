"""
RMS-compatible external script for converting nightly FITS files into movies for
RMS_telemetry.
"""

import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

import glob
import time

from RMS.Logger import getLogger

from RMS_telemetry.images import fits_to_image, fits_to_movie


log = getLogger("logger")

def rmsExternal(captured_night_dir, archived_night_dir, config):
    fits_list = glob.glob(os.path.join(archived_night_dir, 'FF_*.fits'))
    for fitsname in fits_list:
        t0 = time.time()
        success = fits_to_image(fitsname)
        t1 = time.time()
        
        if success is not None:
            log.debug(f"Converted {os.path.basename(fitsname)} to png in {t1-t0:.1f} s")
        else:
            log.warning(f"Failed to convert {os.path.basename(fitsname)} to png")
            
        t0 = time.time()
        success = fits_to_movie(fitsname)
        t1 = time.time()
        
        if success is not None:
            log.debug(f"Converted {os.path.basename(fitsname)} to mp4 in {t1-t0:.1f} s")
        else:
            log.warning(f"Failed to convert {os.path.basename(fitsname)} to mp4")
