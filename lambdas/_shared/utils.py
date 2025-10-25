import os
import json

def response(body: dict, status: int = 200):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body)
    }

PROCESSED_PREFIX = os.getenv("PROCESSED_PREFIX", "results/")
