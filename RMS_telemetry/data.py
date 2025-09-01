import os
import glob
import json

from .utils import iso_to_timestamp, get_archive_dir, timed_lru_cache

from typing import Optional, Dict, Any, List

__all__ = ['get_established_showers', 'get_shower_breakdown', 'get_shower_details',
           'get_meteor_details', 'get_observation_summary', 'get_fits_listing',
           'get_meteor_fits_file']


def get_established_showers() -> Dict[str,Dict[str,Any]]:
    """
    Load in the RMS list of established meteor showers and return a dictionary
    of dictionaries containing the contents.
    """
    
    showers = {}
    if os.path.exists('/home/rms/source/RMS/share/established_showers.csv'):
        with open('/home/rms/source/RMS/share/established_showers.csv', 'r') as fh:
            for line in fh:
                if len(line) < 3:
                    continue
                if line[0] == '#':
                    continue
                    
                fields = line.split('|')
                iau, code, name = int(fields[0], 10), fields[1].strip(), fields[2].strip()
                try:
                    sol_begin, sol_max, sol_end = float(fields[3]), float(fields[4]), float(fields[5])
                except ValueError:
                    sol_begin = sol_max = sol_end = float(fields[4])
                ra, dra = float(fields[6]), float(fields[7])
                dec, ddec = float(fields[8]), float(fields[9])
                vg, dvg = float(fields[10]), float(fields[11])
                ref = fields[12].strip()
                showers[code] = {'iau_no': iau,
                                 'name': name,
                                 'sol_begin': sol_begin,
                                 'sol_max': sol_max,
                                 'sol_end': sol_end,
                                 'ra': ra,
                                 'delta_ra': dra,
                                 'dec': dec,
                                 'delta_dec': ddec,
                                 'vg': vg,
                                 'delta_vg': dvg,
                                 'reference': ref}
                
    return showers


_ESTALISHED_SHOWERS = get_established_showers()


@timed_lru_cache(seconds=3600)
def get_shower_breakdown(log_dir: str, date: Optional[str]=None) -> Optional[str]:
    """
    Given a path to location of the RMS logs and, optionally a date in YYYYMMDD
    format, return the meteor shower breakdown from a _radiants.txt file as a
    dictionary.  If a date is not provided then the most recent file is
    returned.  Returns None if the data cannot be found.
    """
    
    global _ESTALISHED_SHOWERS
    
    data_dir = get_archive_dir(log_dir, date=date)
    
    shower_data = None
    if data_dir:
        shower_data = os.path.basename(data_dir)
        shower_data += '_radiants.txt'
        shower_data = os.path.join(data_dir, shower_data)
        if not os.path.exists(shower_data):
            shower_data = None
        else:
            filename = shower_data
            
            shower_data = {}
            with open(filename, 'r') as fh:
                in_block = False
                for line in fh:
                    if line.startswith('# Code, Count, IAU link'):
                        in_block = True
                    elif in_block:
                        entry = line[1:].strip()
                        if len(entry) < 3:
                            break
                            
                        shwr, count, link = entry.split(',', 2)
                        shwr = shwr.strip()
                        if shwr == '...':
                            shwr = 'sporadic'
                        else:
                            try:
                                shwr = _ESTALISHED_SHOWERS[shwr]['name']
                            except KeyError:
                                pass
                        count = int(count, 10)
                        shower_data[shwr] = count
                        
    return shower_data


@timed_lru_cache(seconds=3600)
def get_shower_details(log_dir: str, date: Optional[str]=None) -> Optional[List[Dict[str,Any]]]:
    """
    Given a path to location of the RMS logs and, optionally a date in YYYYMMDD
    format, return the meteor shower details from a _radiants.txt file as a
    list of dictionaries, one per meteor.  If a date is not provided then the
    most recent file is returned.  Returns None if the data cannot be found.
    """
    
    global _ESTALISHED_SHOWERS
    
    data_dir = get_archive_dir(log_dir, date=date)
    
    radiants_data = None
    if data_dir:
        radiants_data = os.path.basename(data_dir)
        radiants_data += '_radiants.txt'
        radiants_data = os.path.join(data_dir, radiants_data)
        if not os.path.exists(radiants_data):
            radiants_data = None
        else:
            filename = radiants_data
            
            radiants_data = []
            with open(filename, 'r') as fh:
                for line in fh:
                    if len(line) < 3:
                        continue
                    if line[0] == '#':
                        continue
                        
                    fields = line.split(',')
                    date = fields[0].strip()
                    jd = float(fields[1])
                    sol = float(fields[2])
                    shwr = fields[3].strip()
                    if shwr == '...':
                        shwr = 'sporadic'
                    else:
                        try:
                            shwr = _ESTALISHED_SHOWERS[shwr]['name']
                        except KeyError:
                            pass
                    ra1, dec1 = float(fields[4]), float(fields[5])
                    ra2, dec2 = float(fields[6]), float(fields[7])
                    mag = float(fields[-3])
                    entry = {'date': f"{date[:4]}-{date[4:6]}-{date[6:8]}T{date[9:]}",
                             'timestamp': 0.0,
                             'start_jd': jd,
                             'sol': sol,
                             'shower': shwr,
                             'start_radec': (ra1, dec1),
                             'stop_radec': (ra2, dec2),
                             'mag': mag
                            }
                    entry['timestamp'] = iso_to_timestamp(entry['date'])
                    radiants_data.append(entry)
                    
    return radiants_data


@timed_lru_cache(seconds=3600)
def get_meteor_details(log_dir: str, date: Optional[str]=None) -> Optional[List[Dict[str,Any]]]:
    """
    Given a path to location of the RMS logs and, optionally a date in YYYYMMDD
    format, return the meteor details from a .csv file as a list of dictionaries,
    one per meteor.  If a date is not provided then the most recent file is
    returned.  Returns None if the data cannot be found.
    """
    
    data_dir = get_archive_dir(log_dir, date=date)
    
    meteor_data = None
    if data_dir:
        meteor_data = os.path.basename(data_dir)
        meteor_data += '.csv'
        meteor_data = os.path.join(data_dir, meteor_data)
        if not os.path.exists(meteor_data):
            meteor_data = None
        else:
            filename = meteor_data
            
            shower_details = get_shower_details(log_dir, date=date)
            
            meteor_data = []
            with open(filename, 'r') as fh:
                for line in fh:
                    if len(line) < 3:
                        continue
                    if line.startswith('Ver,Y,M,D'):
                        continue
                        
                    fields = line.split(',')
                    y, m, d = int(fields[1], 10), int(fields[2], 10), int(fields[3], 10)
                    h, i, s = int(fields[4], 10), int(fields[5], 10), float(fields[6])
                    mag, dur = float(fields[7]), float(fields[8])
                    az1, alt1 = float(fields[9]), float(fields[10])
                    az2, alt2 = float(fields[11]), float(fields[12])
                    ra1, dec1 = float(fields[13]), float(fields[14])
                    ra2, dec2 = float(fields[15]), float(fields[16])
                    entry = {'date': f"{y:04d}-{m:02d}-{d:02d}T{h:02d}:{i:02d}:{s:09.6f}",
                             'timestamp': 0.0,
                             'mag': mag,
                             'dur': dur,
                             'start_azalt': (az1, alt1),
                             'stop_azalt': (az2, alt2),
                             'start_radec': (ra1, dec1),
                             'stop_radec': (ra2, dec2),
                             'shower': 'unknown'
                            }
                    entry['timestamp'] = iso_to_timestamp(entry['date'])
                    if shower_details is not None:
                        for meteor in shower_details:
                            if abs(meteor['timestamp'] - entry['timestamp']) < 0.25
                               and meteor['mag'] == entry['mag']:
                                entry['shower'] = meteor['shower']
                                break
                                
                    meteor_data.append(entry)
                    
    return meteor_data


@timed_lru_cache(seconds=3600)
def get_flux_time_intervals(log_dir: str, date: Optional[str]=None) -> Optional[str]:
    """
    Given a path to location of the RMS logs and, optionally a date in YYYYMMDD
    format, return the flux time intervals from a flux_time_intervals.json
    file as a dictionary.  If a date is not provided then the most recent file
    is returned.  Returns None if the data cannot be found.
    """
    
    data_dir = get_archive_dir(log_dir, date=date)
    
    fti_data = None
    if data_dir:
        fti_data = 'flux_time_intervals.json'
        fti_data = os.path.join(data_dir, fti_data)
        if not os.path.exists(fti_data):
            fti_data = None
        else:
            filename = fti_data
            
            fti_data = {}
            with open(filename, 'r') as fh:
                fti_data = json.load(fh)
                
    return fti_data


@timed_lru_cache(seconds=3600)
def get_observation_summary(log_dir: str, date: Optional[str]=None) -> Optional[str]:
    """
    Given a path to location of the RMS logs and, optionally a date in YYYYMMDD
    format, return the observation summary from a  _observation_summary.txt
    file as a dictionary.  If a date is not provided then the most recent file
    is returned.  Returns None if the data cannot be found.
    """
    
    data_dir = get_archive_dir(log_dir, date=date)
    
    obs_data = None
    if data_dir:
        obs_data = os.path.basename(data_dir)
        obs_data += '_observation_summary.json'
        obs_data = os.path.join(data_dir, obs_data)
        if not os.path.exists(obs_data):
            obs_data = None
        else:
            filename = obs_data
            
            obs_data = {}
            with open(filename, 'r') as fh:
                obs_data = json.load(fh)
                
    return obs_data


@timed_lru_cache(seconds=3600)
def get_fits_listing(log_dir: str, date: Optional[str]=None) -> Optional[List[str]]:
    """
    Given a path to location of the RMS logs and, optionally a date in YYYYMMDD
    format, return a list of FITS files.  If a date is not provided then the
    most recent listing is returned.  Returns None if there are not FITS files.
    """
    
    data_dir = get_archive_dir(log_dir, date=date)
    
    fits_list = None
    if data_dir:
        fits_list = os.path.join(data_dir, 'FF_*.fits')
        fits_list = glob.glob(fits_list)
        fits_list.sort()
        if len(fits_list) == 0:
            fits_list = None
            
    return fits_list


@timed_lru_cache(seconds=3600)
def get_meteor_fits_file(log_dir: str, datetime: str) -> Optional[str]:
    """
    Given a path to location of the RMS logs and a ISO8601 date/time for a
    meteor, return the filename of the associated FF FITS file.  Returns None
    if the FITS file does not exist or cannot be determined.
    """
    
    meteor_time = iso_to_timestamp(datetime)
    fits_list = get_fits_listing(log_dir, date=datetime[:10].replace('-', ''))
    
    fits_image = None
    for filename in fits_list:
        _, _, date, time, ms, _ = os.path.basename(filename).split('_', 5)
        fits_time = f"{date[:4]}-{date[4:6]}-{date[6:8]}T{time[:2]}:{time[2:4]}:{time[4:6]}.{ms}"
        fits_time = iso_to_timestamp(fits_time)
        
        if fits_time <= meteor_time:
            fits_image = filename
        else:
            break
            
    return fits_image 
