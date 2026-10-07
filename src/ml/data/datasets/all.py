import os

import boto3


if __name__ == "__main__":
    bucket = os.environ.get("DECKSAGE_S3_BUCKET")
    if not bucket:
        raise SystemExit("Set DECKSAGE_S3_BUCKET to your bucket name")
    s3 = boto3.resource("s3")
    s3.Bucket(bucket)
