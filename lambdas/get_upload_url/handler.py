import json
import os
import re
import boto3
import time

s3 = boto3.client('s3')

UPLOADS_BUCKET = os.environ.get('UPLOADS_BUCKET')

SAFE_JOBID = re.compile(r'^[a-zA-Z0-9\-_.]{3,128}$')


def _response(body: dict, status: int = 200):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        },
        "body": json.dumps(body)
    }


def handler(event, context):
    # Handle CORS preflight for HTTP API v2
    if event.get('requestContext', {}).get('http', {}).get('method') == 'OPTIONS':
        return _response({"ok": True}, 200)

    try:
        body = event.get('body') or '{}'
        if event.get('isBase64Encoded'):
            import base64
            body = base64.b64decode(body).decode('utf-8')
        data = json.loads(body)
    except Exception:
        data = {}

    job_id = data.get('jobId')
    content_type = data.get('contentType', 'video/mp4')

    # Generate job id if not provided
    if not job_id:
        job_id = f"job-{int(time.time()*1000)}"

    if not SAFE_JOBID.match(job_id):
        return _response({"error": "Invalid jobId"}, 400)

    key = f"uploads/{job_id}.mp4"

    # Generate a short-lived pre-signed URL (10 minutes)
    url = s3.generate_presigned_url(
        ClientMethod='put_object',
        Params={
            'Bucket': UPLOADS_BUCKET,
            'Key': key,
            'ContentType': content_type
        },
        ExpiresIn=600,
        HttpMethod='PUT'
    )

    return _response({
        "uploadUrl": url,
        "bucket": UPLOADS_BUCKET,
        "key": key,
        "jobId": job_id
    }, 200)
