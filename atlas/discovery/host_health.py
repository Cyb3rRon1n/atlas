import json
import os
import time
import urllib.request

import psutil


def get_host_health(status_urls=None):
    """
    The host's vital signs in one call: when it last booted (an
    unexplained restart is often the whole story), load, memory, the
    hottest reading per temperature sensor, root disk, plus any configured
    JSON status feeds (e.g. a RAID-card watchdog).
    """

    boot = psutil.boot_time()
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    temperatures = {}

    try:
        for sensor, readings in (psutil.sensors_temperatures() or {}).items():
            values = [reading.current for reading in readings if reading.current]
            if values:
                temperatures[sensor] = max(values)

    except (AttributeError, OSError):
        pass

    feeds = {}

    for name, url in (status_urls or {}).items():

        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                feeds[name] = json.load(response)

        except Exception as error:
            feeds[name] = {"error": str(error)}

    return {
        "booted_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(boot)),
        "uptime_hours": round((time.time() - boot) / 3600, 1),
        "load_average": [round(value, 2) for value in os.getloadavg()],
        "cpu_count": psutil.cpu_count(),
        "memory_percent": memory.percent,
        "swap_percent": psutil.swap_memory().percent,
        "root_disk_percent": disk.percent,
        "max_temperature_c_by_sensor": temperatures,
        "status_feeds": feeds
    }
