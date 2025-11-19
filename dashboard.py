# dashboard.py
import psutil
import tkinter as tk
from tkinter import ttk
from collections import deque
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

REFRESH_INTERVAL = 2000  # 2 seconds
MAX_DATA_POINTS = 30     # last 30 readings for graph

class CPUBuddyDashboard:
    def __init__(self, root):
        self.root = root
        self.root.title("CPU_BUDDY Live Dashboard")
        self.root.geometry("650x550")
        self.root.resizable(False, False)

        # --- Title ---
        title = tk.Label(root, text="CPU_BUDDY LIVE DASHBOARD",
                         font=("Segoe UI", 16, "bold"), fg="#00BFFF")
        title.pack(pady=10)

        # --- System Stats Frame ---
        frame_sys = ttk.LabelFrame(root, text="System Usage")
        frame_sys.pack(fill="x", padx=10, pady=5)

        # CPU Progress Bar
        self.cpu_label = tk.Label(frame_sys, text="CPU Usage: --%", font=("Segoe UI", 12))
        self.cpu_label.pack(anchor="w", padx=10, pady=3)
        self.cpu_bar = ttk.Progressbar(frame_sys, length=500)
        self.cpu_bar.pack(padx=10, pady=3)

        # Memory Progress Bar
        self.mem_label = tk.Label(frame_sys, text="Memory Usage: --%", font=("Segoe UI", 12))
        self.mem_label.pack(anchor="w", padx=10, pady=3)
        self.mem_bar = ttk.Progressbar(frame_sys, length=500)
        self.mem_bar.pack(padx=10, pady=3)

        # --- Control Buttons ---
        frame_btn = tk.Frame(root)
        frame_btn.pack(pady=5)
        self.running = True
        btn_start = tk.Button(frame_btn, text="Start Monitoring", command=self.start_monitoring)
        btn_start.pack(side="left", padx=10)
        btn_stop = tk.Button(frame_btn, text="Stop Monitoring", command=self.stop_monitoring)
        btn_stop.pack(side="left", padx=10)

        # --- Top Processes Frame ---
        frame_proc = ttk.LabelFrame(root, text="Top 5 CPU Consuming Processes")
        frame_proc.pack(fill="both", expand=True, padx=10, pady=5)

        self.tree = ttk.Treeview(frame_proc, columns=("pid", "name", "cpu", "mem"), show="headings", height=6)
        self.tree.heading("pid", text="PID")
        self.tree.heading("name", text="Process Name")
        self.tree.heading("cpu", text="CPU %")
        self.tree.heading("mem", text="Memory %")
        self.tree.column("pid", width=60, anchor="center")
        self.tree.column("name", width=250, anchor="w")
        self.tree.column("cpu", width=80, anchor="center")
        self.tree.column("mem", width=80, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)

        # --- Graph Frame ---
        frame_graph = ttk.LabelFrame(root, text="CPU & Memory Usage Graph (Last 30 readings)")
        frame_graph.pack(fill="both", expand=True, padx=10, pady=5)

        self.cpu_data = deque(maxlen=MAX_DATA_POINTS)
        self.mem_data = deque(maxlen=MAX_DATA_POINTS)
        self.fig = Figure(figsize=(6, 2), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_ylim(0, 100)
        self.ax.set_ylabel("Usage %")
        self.ax.set_xlabel("Time")
        self.line_cpu, = self.ax.plot([], [], label="CPU %", color="blue")
        self.line_mem, = self.ax.plot([], [], label="Memory %", color="green")
        self.ax.legend(loc="upper right")
        self.ax.grid(True)

        self.canvas = FigureCanvasTkAgg(self.fig, master=frame_graph)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        # --- Start Update Loop ---
        self.update_data()

    def start_monitoring(self):
        self.running = True

    def stop_monitoring(self):
        self.running = False

    def update_data(self):
        if self.running:
            # --- System metrics ---
            cpu = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory().percent

            self.cpu_label.config(text=f"CPU Usage: {cpu:.1f}%")
            self.mem_label.config(text=f"Memory Usage: {mem:.1f}%")

            # Color change based on usage
            self.cpu_bar['value'] = cpu
            self.cpu_bar.configure(style=self.get_bar_style(cpu))
            self.mem_bar['value'] = mem
            self.mem_bar.configure(style=self.get_bar_style(mem))

            # --- Graph update ---
            self.cpu_data.append(cpu)
            self.mem_data.append(mem)
            self.line_cpu.set_data(range(len(self.cpu_data)), self.cpu_data)
            self.line_mem.set_data(range(len(self.mem_data)), self.mem_data)
            self.ax.set_xlim(0, MAX_DATA_POINTS)
            self.canvas.draw()

            # --- Top processes ---
            for row in self.tree.get_children():
                self.tree.delete(row)

            procs = []
            for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    procs.append(p.info)
                except psutil.NoSuchProcess:
                    continue
            top = sorted(procs, key=lambda p: p['cpu_percent'], reverse=True)[:5]
            for p in top:
                self.tree.insert("", "end", values=(
                    p['pid'], p['name'][:30], f"{p['cpu_percent']:.1f}", f"{p['memory_percent']:.1f}"
                ))

        # Schedule next update
        self.root.after(REFRESH_INTERVAL, self.update_data)

    def get_bar_style(self, percent):
        style = ttk.Style()
        if percent < 50:
            style.configure("green.Horizontal.TProgressbar", foreground='green', background='green')
            return "green.Horizontal.TProgressbar"
        elif percent < 80:
            style.configure("yellow.Horizontal.TProgressbar", foreground='yellow', background='yellow')
            return "yellow.Horizontal.TProgressbar"
        else:
            style.configure("red.Horizontal.TProgressbar", foreground='red', background='red')
            return "red.Horizontal.TProgressbar"


if __name__ == "__main__":
    root = tk.Tk()
    app = CPUBuddyDashboard(root)
    root.mainloop()
