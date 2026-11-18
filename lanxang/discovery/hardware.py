import psutil


def collect_cpu():
    return {
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "cpu_frequency": psutil.cpu_freq()._asdict()
        if psutil.cpu_freq()
        else None,
    }


def collect_memory():
    memory = psutil.virtual_memory()

    return {
        "total_gb": round(memory.total / (1024**3), 2),
        "available_gb": round(memory.available / (1024**3), 2),
        "used_percent": memory.percent,
    }


def collect_hardware():
    return {
        "cpu": collect_cpu(),
        "memory": collect_memory(),
    }
