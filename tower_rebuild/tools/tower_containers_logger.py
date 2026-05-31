from __future__ import annotations

import argparse
import csv
import threading
import time
from datetime import datetime
from pathlib import Path

import serial
import serial.tools.list_ports


TANK_IDS = ("TANK_1", "TANK_2", "TANK_3", "TANK_4")
CSV_COLUMNS = ("timestamp", "tank1", "tank2", "tank3", "tank4")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Continuously log four Arduino tank fill percentages into a CSV feed.")
    parser.add_argument("--output", required=True, help="CSV path to append timestamp,tank1,tank2,tank3,tank4 rows into.")
    parser.add_argument("--baud-rate", type=int, default=9600, help="Serial baud rate.")
    parser.add_argument("--scan-interval", type=float, default=2.0, help="Seconds between port scans.")
    parser.add_argument("--log-interval", type=float, default=5.0, help="Seconds between CSV writes after the first live sample.")
    parser.add_argument("--stale-threshold", type=float, default=60.0, help="Age in seconds after which a tank sample is treated as stale/blank.")
    return parser


class TankLogger:
    def __init__(self, output_path: Path, baud_rate: int, scan_interval: float, log_interval: float, stale_threshold: float) -> None:
        self.output_path = output_path
        self.baud_rate = int(baud_rate)
        self.scan_interval = float(scan_interval)
        self.log_interval = float(log_interval)
        self.stale_threshold = float(stale_threshold)
        self.lock = threading.Lock()
        self.active_ports: set[str] = set()
        self.latest_data = {
            tank_id: {"pct": None, "timestamp": None}
            for tank_id in TANK_IDS
        }
        self.has_written_live_sample = False
        self.last_write_monotonic = 0.0

    def ensure_csv(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        if self.output_path.exists():
            return
        with self.output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(CSV_COLUMNS)

    def scan_ports_loop(self) -> None:
        while True:
            try:
                ports = serial.tools.list_ports.comports()
            except Exception:
                time.sleep(self.scan_interval)
                continue
            for port in ports:
                port_name = str(port.device or "").strip()
                if not port_name:
                    continue
                with self.lock:
                    if port_name in self.active_ports:
                        continue
                    self.active_ports.add(port_name)
                thread = threading.Thread(target=self.read_serial_port, args=(port_name,), daemon=True)
                thread.start()
            time.sleep(self.scan_interval)

    def read_serial_port(self, port_name: str) -> None:
        try:
            serial_port = serial.Serial(port_name, self.baud_rate, timeout=2)
            time.sleep(2)
            while True:
                try:
                    line = serial_port.readline().decode(errors="ignore").strip()
                except Exception:
                    break
                if not line or not line.startswith("ID:"):
                    continue
                tank_id = None
                pct = None
                for part in line.split(","):
                    current = str(part or "").strip()
                    if current.startswith("ID:"):
                        tank_id = current.replace("ID:", "", 1).strip()
                    elif current.startswith("PCT:"):
                        try:
                            pct = float(current.replace("PCT:", "", 1).strip())
                        except ValueError:
                            pct = None
                if tank_id in TANK_IDS and pct is not None:
                    with self.lock:
                        self.latest_data[tank_id]["pct"] = max(0.0, min(100.0, pct))
                        self.latest_data[tank_id]["timestamp"] = time.time()
        finally:
            with self.lock:
                self.active_ports.discard(port_name)

    def current_csv_row(self) -> list[object]:
        now = time.time()
        row: list[object] = [datetime.now().strftime("%Y-%m-%d %H:%M:%S")]
        with self.lock:
            for tank_id in TANK_IDS:
                pct = self.latest_data[tank_id]["pct"]
                last_seen = self.latest_data[tank_id]["timestamp"]
                if pct is None or last_seen is None or (now - float(last_seen)) > self.stale_threshold:
                    row.append("")
                else:
                    row.append(round(float(pct), 2))
        return row

    def has_live_values(self, row: list[object]) -> bool:
        return any(str(value).strip() for value in row[1:])

    def write_csv_loop(self) -> None:
        self.ensure_csv()
        while True:
            row = self.current_csv_row()
            now_monotonic = time.monotonic()
            should_write = False
            if not self.has_written_live_sample:
                should_write = self.has_live_values(row)
            elif (now_monotonic - self.last_write_monotonic) >= self.log_interval:
                should_write = True
            if should_write:
                try:
                    with self.output_path.open("a", newline="", encoding="utf-8") as handle:
                        writer = csv.writer(handle)
                        writer.writerow(row)
                    self.has_written_live_sample = self.has_live_values(row) or self.has_written_live_sample
                    self.last_write_monotonic = now_monotonic
                except PermissionError:
                    pass
            time.sleep(1)

    def run_forever(self) -> None:
        self.ensure_csv()
        threading.Thread(target=self.scan_ports_loop, daemon=True).start()
        threading.Thread(target=self.write_csv_loop, daemon=True).start()
        while True:
            time.sleep(1)


def main() -> None:
    args = build_parser().parse_args()
    logger = TankLogger(
        output_path=Path(args.output).expanduser().resolve(),
        baud_rate=args.baud_rate,
        scan_interval=args.scan_interval,
        log_interval=args.log_interval,
        stale_threshold=args.stale_threshold,
    )
    logger.run_forever()


if __name__ == "__main__":
    main()
