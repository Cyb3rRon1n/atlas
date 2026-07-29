from atlas.monitoring.collector import evaluate_thresholds


def diff_monitoring(previous, current, thresholds):
    """
    previous/current are each {"metrics": {...}, "containers": {...}}
    or falsy. Returns a list of change dicts for metrics that flipped
    exceeded-state since the last scan - crossed (previously under,
    now at/over) or recovered (previously at/over, now under) -
    evaluated against the *current* thresholds both times, since
    threshold config itself isn't versioned per snapshot. previous
    being falsy (no prior scan) means there is no baseline to diff
    against, so nothing is reported - same rule as Proxmox's
    diff_virtualization.
    """

    if not previous:
        return []


    changes = []

    previous_host_exceeded = evaluate_thresholds(
        previous.get("metrics", {}), thresholds
    )

    current_host_exceeded = evaluate_thresholds(
        current.get("metrics", {}), thresholds
    )

    for name, is_exceeded in current_host_exceeded.items():

        was_exceeded = previous_host_exceeded.get(name, False)

        if is_exceeded and not was_exceeded:

            changes.append({
                "type": "host_metric_crossed",
                "metric": name
            })

        elif was_exceeded and not is_exceeded:

            changes.append({
                "type": "host_metric_recovered",
                "metric": name
            })


    previous_containers = previous.get("containers", {})
    current_containers = current.get("containers", {})

    for container_name, values in current_containers.items():

        previous_values = previous_containers.get(container_name, {})

        was_exceeded_by_metric = evaluate_thresholds(previous_values, thresholds)
        is_exceeded_by_metric = evaluate_thresholds(values, thresholds)

        for metric_name, is_exceeded in is_exceeded_by_metric.items():

            was_exceeded = was_exceeded_by_metric.get(metric_name, False)

            if is_exceeded and not was_exceeded:

                changes.append({
                    "type": "container_metric_crossed",
                    "container": container_name,
                    "metric": metric_name
                })

            elif was_exceeded and not is_exceeded:

                changes.append({
                    "type": "container_metric_recovered",
                    "container": container_name,
                    "metric": metric_name
                })

    return changes


def format_change(change) -> str:

    change_type = change["type"]

    if change_type == "host_metric_crossed":
        return f"! Host {change['metric']} crossed threshold"

    if change_type == "host_metric_recovered":
        return f"✓ Host {change['metric']} back under threshold"

    if change_type == "container_metric_crossed":
        return (
            f"! Container '{change['container']}' {change['metric']} "
            f"crossed threshold"
        )

    if change_type == "container_metric_recovered":
        return (
            f"✓ Container '{change['container']}' {change['metric']} "
            f"back under threshold"
        )

    return f"? Unknown change: {change}"
