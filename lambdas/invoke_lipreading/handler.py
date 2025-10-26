import os
import json
import requests
import boto3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Call AV-HuBERT server on EC2 GPU instance via HTTP
AVHUBERT_ENDPOINT = os.environ.get("AVHUBERT_ENDPOINT", "")  # e.g., http://ec2-xx-xx-xx-xx.compute.amazonaws.com:8000
SAGEMAKER_ENDPOINT = os.environ.get("SAGEMAKER_ENDPOINT", "")  # e.g., gorggle-avhubert-ep
TIMEOUT = int(os.environ.get("TIMEOUT", "300"))  # 5 minutes for video processing

smrt = boto3.client("sagemaker-runtime") if SAGEMAKER_ENDPOINT else None


def handler(event, context):
    """
    Invoke AV-HuBERT lip reading model hosted on EC2 GPU instance.
    Sends frames S3 location to the server which downloads, processes, and returns predictions.
    """
    if not (SAGEMAKER_ENDPOINT or AVHUBERT_ENDPOINT):
        logger.warning("No AV-HuBERT endpoint configured (SageMaker or EC2). Skipping lip reading.")
        return {**event, "lipreading": {"segments": [], "text": "", "note": "Endpoint not configured"}}
    
    media = event.get("media", {})
    input_obj = event.get("input", {})
    frames_prefix = media.get("frames_prefix")
    fps = media.get("fps", 25)
    bucket = input_obj.get("bucket")
    key = input_obj.get("key")

    payload = {"fps": fps}

    if frames_prefix:
        payload.update({
            "s3_bucket": bucket,
            "frames_prefix": frames_prefix
        })
        logger.info(f"Using pre-extracted frames at s3://{bucket}/{frames_prefix}")
    else:
        # Fallback: send raw video S3 key for EC2-side extraction (workaround to avoid FFmpeg in Lambda)
        if not all([bucket, key]):
            logger.warning("No frames and no input S3 provided. Skipping lip reading.")
            return {**event, "lipreading": {"segments": [], "text": "", "note": "No frames or input video"}}
        payload.update({
            "s3_bucket": bucket,
            "s3_video_key": key
        })
        logger.info(f"Using fallback: server will extract from s3://{bucket}/{key}")
    
    try:
        if SAGEMAKER_ENDPOINT:
            logger.info(f"Invoking SageMaker endpoint: {SAGEMAKER_ENDPOINT}")
            sm_resp = smrt.invoke_endpoint(
                EndpointName=SAGEMAKER_ENDPOINT,
                ContentType="application/json",
                Accept="application/json",
                Body=json.dumps(payload).encode("utf-8")
            )
            body = sm_resp["Body"].read().decode("utf-8")
            result = json.loads(body)
        else:
            logger.info(f"Calling AV-HuBERT EC2 endpoint: {AVHUBERT_ENDPOINT}/predict")
            response = requests.post(
                f"{AVHUBERT_ENDPOINT}/predict",
                json=payload,
                timeout=TIMEOUT
            )
            response.raise_for_status()
            result = response.json()

        logger.info(f"Lip reading result: {result.get('text', '')[:100]}...")
        return {**event, "lipreading": result}

    except requests.exceptions.Timeout:
        logger.error(f"Timeout calling AV-HuBERT EC2 endpoint after {TIMEOUT}s")
        return {**event, "lipreading": {"segments": [], "text": "", "error": "Timeout"}}
    except Exception as e:
        logger.error(f"Error invoking AV-HuBERT: {e}")
        return {**event, "lipreading": {"segments": [], "text": "", "error": str(e)}}
