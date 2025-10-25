import json
import os
import urllib.parse
import boto3

SFN_ARN = os.environ.get("STATE_MACHINE_ARN")
sfn = boto3.client("stepfunctions")

def handler(event, context):
    # S3 put event for uploads/uploads/<key>.mp4
    # Start a Step Functions execution with job metadata
    records = event.get("Records", [])
    started = []
    for r in records:
        s3 = r.get("s3", {})
        bucket = s3.get("bucket", {}).get("name")
        key = urllib.parse.unquote_plus(s3.get("object", {}).get("key"))
        if not key.lower().endswith(".mp4"):
            continue
        job_id = key.split("/")[-1].rsplit(".", 1)[0]
        input_obj = {
            "jobId": job_id,
            "input": {
                "bucket": bucket,
                "key": key
            }
        }
        sfn.start_execution(stateMachineArn=SFN_ARN, input=json.dumps(input_obj))
        started.append(job_id)
    return {"started": started}
