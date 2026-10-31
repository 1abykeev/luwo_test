"""Sample the memory and CPU of the backend process while a load test runs.

    python loadtest/sample_process.py <pid> <seconds> <out.csv>

Writes one line per second (rss in MB, cpu in % of ONE core, so 250 means 2.5 cores busy) and prints the
average and maximum at the end. Child processes (uvicorn workers) are included."""

import csv
import sys
import time

import psutil


def main(pid: int, seconds: int, out_path: str) -> None:
    root = psutil.Process(pid)
    rows = []
    root.cpu_percent(None)
    for child in root.children(recursive=True):
        child.cpu_percent(None)
    with open(out_path, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["second", "rss_mb", "cpu_percent", "threads"])
        for second in range(seconds):
            time.sleep(1)
            try:
                procs = [root, *root.children(recursive=True)]
                rss = sum(p.memory_info().rss for p in procs) / 1024 / 1024
                cpu = sum(p.cpu_percent(None) for p in procs)
                threads = sum(p.num_threads() for p in procs)
            except psutil.NoSuchProcess:
                break
            rows.append((rss, cpu))
            writer.writerow([second + 1, round(rss, 1), round(cpu, 1), threads])
            handle.flush()
    if rows:
        rss_values = [r for r, _ in rows]
        cpu_values = [c for _, c in rows]
        print(f"rss MB: avg {sum(rss_values)/len(rss_values):.0f}, max {max(rss_values):.0f}")
        print(f"cpu % of one core: avg {sum(cpu_values)/len(cpu_values):.0f}, max {max(cpu_values):.0f}")


if __name__ == "__main__":
    main(int(sys.argv[1]), int(sys.argv[2]), sys.argv[3])
