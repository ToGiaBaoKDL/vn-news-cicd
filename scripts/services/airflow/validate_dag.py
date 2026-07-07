from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate that an Airflow DAG is registered.")
    parser.add_argument("--expected-dag", required=True)
    return parser.parse_args()


def parse_dag_list(output: str) -> list[dict[str, Any]]:
    decoder = json.JSONDecoder()
    for json_start, character in enumerate(output):
        if character != "[":
            continue
        try:
            payload, _ = decoder.raw_decode(output[json_start:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
    raise ValueError("Airflow DAG list output did not contain a JSON array")


def has_dag(output: str, expected_dag: str) -> bool:
    return any(dag.get("dag_id") == expected_dag for dag in parse_dag_list(output))


def main() -> int:
    args = parse_args()
    output = sys.stdin.read()
    try:
        return 0 if has_dag(output, args.expected_dag) else 1
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
