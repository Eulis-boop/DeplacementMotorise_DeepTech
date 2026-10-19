"""Interpret the actual, human-readable messages emitted by the .ino firmware."""
import re

POSITION = re.compile(r"^Estimated position:\s*([-+]?\d+(?:\.\d+)?)\s*mm$")


def parse_message(line):
    line = line.strip()
    match = POSITION.match(line)
    if match:
        return ("position", float(match.group(1)))
    if line == "Calibration accepted.":
        return ("calibrated", None)
    if line.startswith("Moving to "):
        return ("moving", None)
    if line in ("Target command completed.", "Already at nearest motor position."):
        return ("completed", None)
    if line in ("Motion stopped.", "Motor is already stationary."):
        return ("stopped", None)
    if line == "State: HOLDING":
        return ("idle", None)
    if line == "State: MOVING":
        return ("moving", None)
    if line.startswith("ERROR:") or line in (
        "Calibrate first with C.", "Stop and wait before calibration.",
        "Change jog after motion stops.", "Complete SETUP first.",
        "Stop motion before SETUP.",
    ):
        return ("error", line)
    if line in ("Position unknown. Use C <reading>.",
                "Actual position not yet calibrated."
                ):
        return ("unknown", None)
    if line == "MICROMETER CONTROLLER STARTED":
        return ("restarted", None)
    return ("info", line)
