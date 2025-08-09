import subprocess

from .utils import now_as_iso, timed_lru_cache

from typing import Optional, Dict, Any

__all__ = ['get_disk_info', 'get_memory_info', 'get_system_info']


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
