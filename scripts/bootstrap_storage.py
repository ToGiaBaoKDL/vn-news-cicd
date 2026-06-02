from __future__ import annotations

import argparse

import boto3
from botocore.exceptions import ClientError
from news_platform.config import load_settings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap configured object-storage buckets.")
    parser.add_argument("--endpoint-url")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def is_missing_bucket(error: ClientError) -> bool:
    return error.response.get("Error", {}).get("Code") in {"404", "NoSuchBucket", "NotFound"}


def main() -> None:
    args = parse_args()
    config = load_settings()
    client = boto3.client(
        "s3",
        endpoint_url=args.endpoint_url or config["storage"]["endpoint_url"],
    )

    for layer, bucket in config["storage"]["buckets"].items():
        if args.dry_run:
            print(f"would ensure {layer} bucket: {bucket}")
            continue
        try:
            client.head_bucket(Bucket=bucket)
        except ClientError as error:
            if not is_missing_bucket(error):
                raise
            client.create_bucket(Bucket=bucket)
            print(f"created {layer} bucket: {bucket}")
        else:
            print(f"exists {layer} bucket: {bucket}")


if __name__ == "__main__":
    main()
