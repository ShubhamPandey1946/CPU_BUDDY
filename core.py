# core.py
import threading
import logging
import json
import signal
import time

from process_monitor import ProcessMonitor
from alert_engine import AlertEngine
from hypervisor_monitor import HypervisorMonitor   # <-- IMPORTANT

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
logger = logging.getLogger("cpu_buddy_core")


def load_config(path="config.json"):
    with open(path, "r") as f:
        return json.load(f)


def main():
    cfg = load_config()
    stop_event = threading.Event()

    # PROCESS MONITOR
    pm = ProcessMonitor(poll_interval=cfg.get("poll_interval", 2))

    # ALERT ENGINE
    ae = AlertEngine(cfg)

    # HYPERVISOR MONITOR (if enabled)
    hm = None
    if cfg.get("use_hypervisor", False):
        try:
            hm = HypervisorMonitor(uri=cfg["hypervisor"]["uri"])
            logger.info("Hypervisor monitor initialized.")
        except Exception as e:
            logger.error("Failed to initialize HypervisorMonitor: %s", e)
            hm = None

    # To calculate VM cpuTime deltas (interval)
    last_snapshot_time = time.time()

    # Callback for process monitor
    def on_snapshot(data):
        nonlocal last_snapshot_time

        # Calculate snapshot interval
        now = time.time()
        interval = now - last_snapshot_time
        last_snapshot_time = now

        # Add VM data if hypervisor enabled
        if hm:
            try:
                vms = hm.list_domains()
            except Exception as e:
                logger.error("Failed to read VMs: %s", e)
                vms = []
        else:
            vms = []

        # Add VMs & interval to snapshot passed to AlertEngine
        data["vms"] = vms
        data["interval"] = interval

        logger.info(f"VMs detected: {data['vms']}")



        try:
            ae.check_and_alert(data)
        except Exception as e:
            logger.exception("Error in alert engine: %s", e)

    # Start process monitor thread
    t = threading.Thread(target=pm.run, args=(on_snapshot, stop_event), daemon=True)
    t.start()

    # Shutdown handler
    def handle_signals(sig, frame):
        logger.info("Shutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, handle_signals)
    signal.signal(signal.SIGTERM, handle_signals)

    logger.info("CPU_BUDDY core running with hypervisor support. Press Ctrl-C to stop.")
    try:
        while not stop_event.is_set():
            stop_event.wait(1)
    finally:
        logger.info("Exited.")


if __name__ == "__main__":
    main()
