import time
import boto3

rekog = boto3.client('rekognition')


def handler(event, context):
    input_obj = event.get("input", {})
    bucket = input_obj.get("bucket")
    key = input_obj.get("key")

    start = rekog.start_face_detection(
        Video={'S3Object': {'Bucket': bucket, 'Name': key}},
        FaceAttributes='DEFAULT'
    )
    job_id = start['JobId']

    # Poll until done (for production, use EventBridge with SNS role)
    status = 'IN_PROGRESS'
    faces = []
    while status in ('IN_PROGRESS', 'SUCCEEDED'):
        time.sleep(5)
        resp = rekog.get_face_detection(JobId=job_id)
        status = resp['JobStatus']
        if status == 'SUCCEEDED':
            faces = resp.get('Faces', [])
            break
        if status == 'FAILED':
            break

    return {**event, "rekognition": {"job_id": job_id, "status": status, "faces": faces}}
