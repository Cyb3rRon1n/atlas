def device_status(sightings, ok_runs):
    """
    seen      - some source saw it on its latest successful run (or it's in its
                one-run grace window)
    quiet     - every source that has seen it missed its last two successful runs
    invisible - only the operator's manual entry; no source has ever seen it

    Only successful runs count, so a failed scan or an unreachable Proxmox
    never makes devices look like they vanished.
    """

    observed = [sighting for sighting in sightings if sighting["source"] != "manual"]

    if not observed:
        return "invisible"

    def runs(sighting):
        return ok_runs.get(sighting["source"], [])

    if all(len(runs(s)) >= 2 and s["last_seen"] < runs(s)[1] for s in observed):
        return "quiet"

    return "seen"
