#!/usr/bin/env python3
"""Upload name mapping to S3."""

import boto3
import sys

s3 = boto3.client('s3')
bucket = 'games-collections'
key = 'processed/name_mapping.json'
local_file = '/tmp/name_mapping.json'

try:
    s3.upload_file(local_file, bucket, key)
    print(f'✅ Uploaded {local_file} to s3://{bucket}/{key}')
except Exception as e:
    print(f'❌ Upload failed: {e}', file=sys.stderr)
    sys.exit(1)

