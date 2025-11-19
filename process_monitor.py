# process_monitor.py
import time
import psutil
import logging
from typing import List, Dict, Any

logger = logging.getLogger("process_monitor")

class ProcessSnapshot:
    def __init__(self, pid:int, name:str, cpu:float, mem_percent:float):
        self.pid = pid
        self.name = name
        self.cpu = cpu
        self.mem_percent = mem_percent

    def to_dict(self):
        return {"pid": self.pid, "name": self.name, "cpu": self.cpu, "mem_percent": self.mem_percent}

class HostMetrics:
    def __init__(self, cpu_percent:float, mem_percent:float):
        self.cpu_percent = cpu_percent
        self.mem_percent = mem_percent

    def to_dict(self):
        return {"cpu_percent": self.cpu_percent, "mem_percent": self.mem_percent}

class ProcessMonitor:
    def __init__(self, poll_interval:int = 2):
        self.poll_interval = poll_interval

    def sample_processes(self) -> List[ProcessSnapshot]:
        snapshots = []
        # call once to initialize cpu_percent counters
        for p in psutil.process_iter(['pid','name']):
            try:
                p.cpu_percent(interval=None)
            except Exception:
                pass
        # short sleep then sample
        time.sleep(0.1)
        for p in psutil.process_iter(['pid','name']):
            try:
                cpu = p.cpu_percent(interval=None)
                mem = p.memory_percent()
                snapshots.append(ProcessSnapshot(p.pid, p.info.get('name') or '', cpu, mem))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return snapshots

    def sample_host(self) -> HostMetrics:
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent
        return HostMetrics(cpu, mem)

    def run(self, callback, stop_event):
        """
        callback: function receiving {'host': HostMetrics, 'processes': [ProcessSnapshot, ...]}
        stop_event: threading.Event to stop
        """
        logger.info("ProcessMonitor started.")
        while not stop_event.is_set():
            host = self.sample_host()
            procs = self.sample_processes()
            callback({"host": host, "processes": procs})
            stop_event.wait(self.poll_interval)

if __name__ == "__main__":
    import threading, json, sys
    stop = threading.Event()
    pm = ProcessMonitor(2)
    def cb(data):
        print("Host:", data['host'].to_dict())
        top = sorted(data['processes'], key=lambda x: x.cpu, reverse=True)[:5]
        print("Top processes:")
        for t in top:
            print(t.to_dict())
    try:
        pm.run(cb, stop)
    except KeyboardInterrupt:
        stop.set()
        sys.exit(0)
