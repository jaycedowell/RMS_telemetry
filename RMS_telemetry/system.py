import time
import subprocess
from collections import namedtuple

from .utils import timestamp_to_iso, now_as_iso, timed_lru_cache

from typing import Optional, Dict, Any

__all__ = ['get_disk_info', 'get_memory_info', 'get_system_info',
           'get_network_info']


@timed_lru_cache(seconds=300)
def get_disk_info(log_dir: str) -> Dict[str,Any]:
    """
    Poll the disk usage associated with the log directory and return the results
    as a dictionary.
    """
    
    data = {}
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
            data['total_gb'] = total
            data['used_gb'] = used
            data['free_gb'] = free
            data['updated'] = dt
    except subprocess.CalledProcessError as e:
        print(f"WARNING: Failed to determine the disk usage: {str(e)}")
        
    return data


@timed_lru_cache(seconds=60)
def get_memory_info(log_dir: str) -> Dict[str,Any]:
    """
    Poll the memory usage and return the results as a dictionary.
    """
    
    data = {}
    with open('/proc/meminfo', 'r') as fh:
        for line in fh:
            if line.startswith('MemTotal:'):
                _, value, units = line.split(None, 2)
                value = int(value, 10)
                data['total_gb'] = value / 1000**2
            elif line.startswith('MemFree:'):
                _, value, units = line.split(None, 2)
                value = int(value, 10)
                data['free_gb'] = value / 1000**2
            elif line.startswith('MemAvailable:'):
                _, value, units = line.split(None, 2)
                value = int(value, 10)
                data['available_gb'] = value / 1000**2
                break
                
    data['updated'] = now_as_iso()
    return data


@timed_lru_cache(seconds=60)
def get_system_info(log_dir: str) -> Dict[str,Any]:
    """
    Poll system information (hostname, uptime, load, etc.) and return the
    results as a dictionary.
    """
    
    data = {}
    
    # Hostname
    with open('/etc/hostname', 'r') as fh:
        data['hostname'] = fh.read().strip()
        
    # Uptime
    with open('/proc/uptime', 'r') as fh:
        fields = fh.read().split(None)
        uptime = int(float(fields[0]))
        days = uptime // 86400
        hours = uptime // 3600 % 24
        minutes = uptime // 60 % 60
        seconds = uptime % 60
        
        value = ''
        if days > 0:
            value = f"{days} days, {hours}:{minutes:02d}"
        elif hours > 0:
            value = f"{hours}:{minutes:02d}"
        elif minutes > 0:
            value = f"{minutes} min"
        else:
            value = f"{seconds} s"
        data['uptime'] = value
        
    # Load averages
    with open('/proc/loadavg', 'r') as fh:
        fields = fh.read().split(None)
        data['load_avg_1min'] = float(fields[0])
        data['load_avg_5min'] = float(fields[1])
        data['load_avg_15min'] = float(fields[2])
        
    # Temperature
    with open('/sys/class/hwmon/hwmon0/temp1_input', 'r') as fh:
        temp = float(fh.read()) / 1000
        data['cpu_temperature_c'] = temp
    
    data['updated'] = now_as_iso()
    return data


# State variable to keep track of the network
_NETWORK_CACHE = {'addr': {},
                  'stat': {}
                 }

# Helper for storing network stats
NetStats = namedtuple('NetStats', ['t', 'rx', 'tx'])

@timed_lru_cache(seconds=60)
def get_network_info(log_dir: str) -> Dict[str,Any]:
    """
    Poll the network interfaces and return information about them as a
    dictionary.
    """
    
    global _NETWORK_CACHE
    
    data = {}
    
    # Get the current interface statistics
    t0 = time.time()
    new_stat = {}
    with open('/proc/net/dev', 'r') as fh:
        for line in fh:
            if line.startswith('Inter-') or line.startswith(' face'):
                continue
            if len(line) < 3:
                continue
                
            fields = line.strip().split()
            dev = fields[0].replace(':', '')
            if dev == 'lo':
                continue
            rx_bytes, tx_bytes = int(fields[1], 10), int(fields[9], 10)
            new_stat[dev] = NetStats(t0, rx_bytes, tx_bytes)
            
    # Refresh the address list, if needed
    for dev in new_stat:
        if dev not in _NETWORK_CACHE['addr']:
            try:
                addr_info = subprocess.check_output(['ip', 'address', 'show', 'dev', dev],
                                                    text=True)
                
                for line in addr_info.split('\n'):
                    line = line.strip()
                    if line.startswith('inet '):
                        _, addr, _ = line.split(None, 2)
                        addr, _ = addr.split('/', 1)
                        _NETWORK_CACHE['addr'][dev] = addr
            except subprocess.CalledProcessError as e:
                print(f"WARNING: failed to query IP address for '{dev}': {str(e)}")
            except Exception as e:
                print(f"WARNING: failed to determine IP address for '{dev}': {str(e)}")
                
    # Compute lifetime bytes received/transmitted and current average data rates
    old_stat = _NETWORK_CACHE['stat']
    for dev in new_stat:
        if dev not in _NETWORK_CACHE['addr']:
            continue
            
        try:
            rx_rate = (new_stat[dev].rx - old_stat[dev].rx) / (new_stat[dev].t - old_stat[dev].t)
            tx_rate = (new_stat[dev].tx - old_stat[dev].tx) / (new_stat[dev].t - old_stat[dev].t)
        except KeyError:
            rx_rate = tx_rate = 0.0
            
        data[dev] = {'ip': _NETWORK_CACHE['addr'][dev],
                     'rx_gb': new_stat[dev][1]/1000**3,
                     'tx_gb': new_stat[dev][2]/1000**3,
                     'rx_kbps': rx_rate/1000,
                     'tx_kbps': tx_rate/1000
                    }
        
    # Update the cache for next time
    _NETWORK_CACHE['stat'] = new_stat
    
    data['updated'] = timestamp_to_iso(t0)
    return data
