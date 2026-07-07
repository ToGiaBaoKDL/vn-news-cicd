from __future__ import annotations

import argparse
import time
from typing import Any

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Spark standalone cluster state.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    master = subparsers.add_parser("master", help="Validate the Spark master UI JSON endpoint.")
    master.add_argument("--master-url", required=True)

    worker = subparsers.add_parser("worker", help="Validate that a worker is registered alive.")
    worker.add_argument("--master-url", required=True)
    worker.add_argument("--worker-host", required=True)
    worker.add_argument("--attempts", type=int, default=12)
    worker.add_argument("--sleep-seconds", type=float, default=5.0)
    return parser.parse_args()


def fetch_master_payload(master_url: str) -> dict[str, Any]:
    response = httpx.get(master_url, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Spark master response must be a JSON object")
    return payload


def worker_is_alive(payload: dict[str, Any], worker_host: str) -> bool:
    workers = payload.get("workers", [])
    return any(
        isinstance(worker, dict)
        and worker.get("host") == worker_host
        and worker.get("state") == "ALIVE"
        for worker in workers
    )


def validate_master(master_url: str) -> None:
    fetch_master_payload(master_url)
    print(f"validated Spark master: {master_url}")


def validate_worker(master_url: str, worker_host: str, attempts: int, sleep_seconds: float) -> None:
    for _ in range(attempts):
        if worker_is_alive(fetch_master_payload(master_url), worker_host):
            print(f"validated Spark worker registration: {worker_host} -> {master_url}")
            return
        time.sleep(sleep_seconds)
    raise RuntimeError(f"Spark worker is not registered as ALIVE on master: {worker_host}")


def main() -> None:
    args = parse_args()
    if args.command == "master":
        validate_master(args.master_url)
        return
    if args.command == "worker":
        validate_worker(args.master_url, args.worker_host, args.attempts, args.sleep_seconds)
        return
    raise ValueError(f"Unsupported Spark validation command: {args.command}")


if __name__ == "__main__":
    main()
