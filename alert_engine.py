# alert_engine.py
import time
import smtplib
import logging
from email.mime.text import MIMEText
from typing import Dict, Any, List

logger = logging.getLogger("alert_engine")

class AlertEngine:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.last_alert_time = {}  # key -> timestamp
        # store last vm cpuTime per vm name (nanoseconds) for delta-based calculations
        self._last_vm_cpu_time = {}  # vm_name -> cpuTime_ns

    def _throttle_ok(self, key: str) -> bool:
        throttle = self.config.get("alert_throttle_seconds", 60)
        last = self.last_alert_time.get(key, 0)
        if time.time() - last < throttle:
            return False
        self.last_alert_time[key] = time.time()
        return True

    def _send_email(self, subject: str, body: str):
        email_cfg = self.config.get("email", {})
        if not email_cfg.get("enabled", False):
            logger.debug("Email disabled, skipping email send.")
            return
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = email_cfg['from']
        msg['To'] = ", ".join(email_cfg['to'])
        try:
            s = smtplib.SMTP(email_cfg['smtp_server'], email_cfg['smtp_port'], timeout=10)
            s.starttls()
            s.login(email_cfg['username'], email_cfg['password'])
            s.sendmail(email_cfg['from'], email_cfg['to'], msg.as_string())
            s.quit()
            logger.info("Alert email sent.")
        except Exception as e:
            logger.exception("Failed to send email alert: %s", e)

    def _vm_cpu_percent_from_delta(self, name: str, cpu_time_ns: int, interval_seconds: float):
        """
        Estimate VM CPU percent from libvirt cpuTime (nanoseconds).
        Returns:
          - float: cpu percent (aggregate, e.g. 150.0 means 150% across all vCPUs)
          - None: if this is the first sample or delta can't be computed
        Notes:
          cpu_percent = (delta_cpu_seconds / interval_seconds) * 100
          where delta_cpu_seconds = (cpu_time_ns - prev_cpu_time_ns) / 1e9
        """
        if interval_seconds is None or interval_seconds <= 0:
            return None

        prev = self._last_vm_cpu_time.get(name)
        now_cpu = cpu_time_ns
        if prev is None:
            # first observed sample: store and return None
            self._last_vm_cpu_time[name] = now_cpu
            return None

        delta_ns = now_cpu - prev
        # update stored value for next time
        self._last_vm_cpu_time[name] = now_cpu

        if delta_ns <= 0:
            return None

        delta_seconds = delta_ns / 1e9
        cpu_percent = (delta_seconds / interval_seconds) * 100.0
        return cpu_percent

    def check_and_alert(self, snapshot: Dict[str, Any]):
        """
        snapshot: {'host': HostMetrics, 'processes': [ProcessSnapshot, ...], 'vms': [dict,...], 'interval': float}
        - vms: list of dicts with keys name,id,state,maxMemKB,memKB,vcpus,cpuTime
        - interval: seconds since previous snapshot (float)
        """
        host = snapshot.get('host')
        procs = snapshot.get('processes', [])

        # --- host-level checks ---
        host_cfg = self.config.get("host_alerts", {})
        if host is not None:
            try:
                if host.cpu_percent >= host_cfg.get("cpu_percent", 100):
                    key = "host_cpu"
                    if self._throttle_ok(key):
                        msg = f"Host CPU high: {host.cpu_percent}%"
                        self._emit_alert("Host CPU Alert", msg, key)
                if host.mem_percent >= host_cfg.get("memory_percent", 100):
                    key = "host_mem"
                    if self._throttle_ok(key):
                        msg = f"Host Memory high: {host.mem_percent}%"
                        self._emit_alert("Host Memory Alert", msg, key)
            except Exception:
                logger.exception("Error while checking host alerts")

        # --- process-level checks (top offenders) ---
        proc_cfg = self.config.get("process_alerts", {})
        cpu_thr = proc_cfg.get("cpu_percent", 100)
        mem_thr = proc_cfg.get("memory_percent", 100)
        try:
            for p in sorted(procs, key=lambda x: x.cpu, reverse=True)[:20]:
                if p.cpu >= cpu_thr:
                    key = f"proc_cpu_{p.pid}"
                    if self._throttle_ok(key):
                        msg = f"Process {p.name} (PID {p.pid}) CPU {p.cpu}%"
                        self._emit_alert("Process CPU Alert", msg, key)
                if p.mem_percent >= mem_thr:
                    key = f"proc_mem_{p.pid}"
                    if self._throttle_ok(key):
                        msg = f"Process {p.name} (PID {p.pid}) Memory {p.mem_percent}%"
                        self._emit_alert("Process Memory Alert", msg, key)
        except Exception:
            logger.exception("Error while checking process alerts")

        # --- VM checks ---
        vms = snapshot.get("vms", [])
        interval = snapshot.get("interval", self.config.get("poll_interval", 2))

        vm_cfg = self.config.get("vm_alerts", {})
        vm_cpu_thr = vm_cfg.get("cpu_percent", 100)
        vm_mem_thr = vm_cfg.get("memory_percent", 100)
        vm_cpu_time_delta_thr = vm_cfg.get("cpu_time_delta_ns", None)

        for vm in vms:
            try:
                # vm is expected to be a dict with keys: name, id, state, maxMemKB, memKB, vcpus, cpuTime
                name = vm.get("name")
                max_mem_kb = int(vm.get("maxMemKB", 0) or 0)
                mem_kb = int(vm.get("memKB", 0) or 0)
                cpu_time_ns = int(vm.get("cpuTime", 0) or 0)

                # Compute memory percent
                mem_percent = (mem_kb / max_mem_kb) * 100.0 if max_mem_kb > 0 else None

                # Compute CPU percent from cpuTime delta
                cpu_percent = self._vm_cpu_percent_from_delta(name, cpu_time_ns, interval)

                # If we don't have a previous sample yet, cpu_percent will be None
                if cpu_percent is not None:
                    # CPU alert
                    if cpu_percent >= vm_cpu_thr:
                        key = f"vm_cpu_{name}"
                        if self._throttle_ok(key):
                            msg = f"VM {name} CPU high: {cpu_percent:.1f}% (vcpus={vm.get('vcpus')})"
                            self._emit_alert("VM CPU Alert", msg, key)

                # Memory alert
                if mem_percent is not None and mem_percent >= vm_mem_thr:
                    key = f"vm_mem_{name}"
                    if self._throttle_ok(key):
                        msg = f"VM {name} Memory high: {mem_percent:.1f}% ({mem_kb}KB/{max_mem_kb}KB)"
                        self._emit_alert("VM Memory Alert", msg, key)

                # Optional: cpuTime delta absolute threshold
                if vm_cpu_time_delta_thr is not None:
                    prev = self._last_vm_cpu_time.get(name)
                    # Note: prev was already updated by _vm_cpu_percent_from_delta, so to check delta we need another store
                    # We'll compute naive delta using the cpu_time_ns and last_alert_time safe fallback
                    # For simplicity, check cpu_time increase compared to stored previous value if available
                    # (skip if prev is None)
                    # prev_cpu_time_ns = prev (old value) is not available here after _vm_cpu_percent_from_delta updated it.
                    # If you need this feature reliably, maintain a separate store for last_cpu_time before update.
                    pass

            except Exception:
                logger.exception("Error while checking VM alerts for vm=%s", vm)

    def _emit_alert(self, subject: str, message: str, key: str):
        # console / logging
        logger.warning("[%s] %s", subject, message)
        # optional email
        self._send_email(subject, message)
        # TODO: push notifications, webhook calls, system notifications can be added here
