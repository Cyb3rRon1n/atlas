import psutil


def collect_storage():

    drives = []

    for partition in psutil.disk_partitions():

        try:
            usage = psutil.disk_usage(partition.mountpoint)

            drives.append(
                {
                    "device": partition.device,
                    "mountpoint": partition.mountpoint,
                    "filesystem": partition.fstype,
                    "total_gb": round(
                        usage.total / (1024**3),
                        2
                    ),
                    "used_percent": usage.percent,
                }
            )

        except PermissionError:
            continue

    return drives
