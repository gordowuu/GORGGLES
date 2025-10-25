import os
import time
import boto3

transcribe = boto3.client('transcribe')

LANGUAGE = os.environ.get("LANGUAGE_CODE", "en-US")


def handler(event, context):
    job_id = event.get("jobId")
    input_obj = event.get("input", {})
    bucket = input_obj.get("bucket")
    key = input_obj.get("key")

    media_uri = f"s3://{bucket}/{key}"
    t_job_name = f"gorggle-{job_id}-{int(time.time())}"

    transcribe.start_transcription_job(
        TranscriptionJobName=t_job_name,
        LanguageCode=LANGUAGE,
        MediaFormat='mp4',
        Media={'MediaFileUri': media_uri},
        Settings={'ShowSpeakerLabels': True, 'MaxSpeakerLabels': 5}
    )

    # For simplicity, poll until done (in production use Step Functions callbacks or EventBridge)
    while True:
        resp = transcribe.get_transcription_job(TranscriptionJobName=t_job_name)
        status = resp['TranscriptionJob']['TranscriptionJobStatus']
        if status in ('COMPLETED', 'FAILED'):
            break
        time.sleep(5)

    result = resp['TranscriptionJob']
    return {**event, "transcribe": {"job_name": t_job_name, "status": status, "result": result}}
