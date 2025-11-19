# hypervisor_monitor.py
try:
    import libvirt
except ImportError:
    libvirt = None

import logging
logger = logging.getLogger("hypervisor_monitor")

class HypervisorMonitor:
    def __init__(self, uri="qemu:///system"):
        if libvirt is None:
            raise RuntimeError("libvirt-python not installed")
        self.conn = libvirt.open(uri)
        if self.conn is None:
            raise RuntimeError(f"Failed to open libvirt URI {uri}")

    def list_domains(self):
        domains = []
        for id in self.conn.listDomainsID():
            dom = self.conn.lookupByID(id)
            info = dom.info()
            # info => (state, maxMem, memory, nrVirtCpu, cpuTime)
            domains.append({
                "name": dom.name(),
                "id": dom.ID(),
                "state": info[0],
                "maxMemKB": info[1],
                "memKB": info[2],
                "vcpus": info[3],
                "cpuTime": info[4]
            })
        # also list inactive / defined domains
        for name in self.conn.listDefinedDomains():
            dom = self.conn.lookupByName(name)
            info = dom.info()
            domains.append({
                "name": dom.name(),
                "id": None,
                "state": info[0],
                "maxMemKB": info[1],
                "memKB": info[2],
                "vcpus": info[3],
                "cpuTime": info[4]
            })
        return domains

    def close(self):
        if self.conn:
            self.conn.close()

if __name__ == "__main__":
    hm = HypervisorMonitor()
    print(hm.list_domains())
    hm.close()
