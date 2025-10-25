import os
import json
import boto3
from decimal import Decimal

s3 = boto3.client('s3')
ddb = boto3.client('dynamodb')

PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET")
JOBS_TABLE = os.environ.get("JOBS_TABLE")


def _decimalize(obj):
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _decimalize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimalize(x) for x in obj]
    return obj


def handler(event, context):
    job_id = event.get("jobId")

    transcribe = event.get("transcribe", {}).get("result", {})
    rekognition = event.get("rekognition", {})
    lips = event.get("lipreading", {})

    # Very simple fusion stub: prefer Transcribe text, attach lip segments
    transcript_uri = transcribe.get("Transcript", {}).get("TranscriptFileUri")

    fusion = {
        "jobId": job_id,
        "transcribe": transcribe,
        "rekognition": rekognition,
        "lipreading": lips,
        "notes": "Fusion logic is a placeholder; implement alignment and confidence-based merging"
    }

    key = f"results/{job_id}/overlay.json"
    s3.put_object(Bucket=PROCESSED_BUCKET, Key=key, Body=json.dumps(fusion).encode('utf-8'), ContentType='application/json')

    ddb.put_item(
        TableName=JOBS_TABLE,
        Item={
            'jobId': {'S': job_id},
            'resultKey': {'S': key},
            'status': {'S': 'COMPLETED'}
        }
    )

    return {"processed": {"bucket": PROCESSED_BUCKET, "key": key}}
