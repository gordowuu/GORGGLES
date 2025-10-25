import os
import json

# Placeholder for media extraction step.
# Replace with MediaConvert submission or FFmpeg-based extraction.

PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "")


def handler(event, context):
    # pass through input info, and pretend we extracted audio + frames
    # outputs point to where future steps will expect them
    job_id = event.get("jobId")
    input_obj = event.get("input", {})
    bucket = input_obj.get("bucket")
    key = input_obj.get("key")

    # Derive paths for where frames/audio would go
    frames_prefix = f"frames/{job_id}/"
    audio_key = f"audio/{job_id}.wav"

    return {
        "jobId": job_id,
        "input": {"bucket": bucket, "key": key},
        "media": {
            "frames_prefix": frames_prefix,
            "audio_s3": {"bucket": bucket, "key": audio_key}
        }
    }
