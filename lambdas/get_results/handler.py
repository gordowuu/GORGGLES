import os
import json
import boto3

def response(body: dict, status: int = 200):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body)
    }

s3 = boto3.client('s3')
ddb = boto3.client('dynamodb')

PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET")
JOBS_TABLE = os.environ.get("JOBS_TABLE")


def handler(event, context):
    # HTTP API (payload v2). Path param: jobId
    job_id = event.get('pathParameters', {}).get('jobId') if isinstance(event, dict) else None
    if not job_id:
        return response({"error": "Missing jobId"}, 400)

    db = ddb.get_item(TableName=JOBS_TABLE, Key={'jobId': {'S': job_id}})
    if 'Item' not in db:
        return response({"error": "Not found"}, 404)
    item = db['Item']
    key = item['resultKey']['S']

    obj = s3.get_object(Bucket=PROCESSED_BUCKET, Key=key)
    body = obj['Body'].read().decode('utf-8')
    data = json.loads(body)

    return response(data, 200)
