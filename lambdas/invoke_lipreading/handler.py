import os
import json
import requests

# Call AV-HuBERT server on EC2 GPU instance via HTTP
AVHUBERT_ENDPOINT = os.environ.get("AVHUBERT_ENDPOINT", "")  # e.g., http://ec2-xx-xx-xx-xx.compute.amazonaws.com:8000
TIMEOUT = int(os.environ.get("TIMEOUT", "300"))  # 5 minutes for video processing


def handler(event, context):
    """
    Invoke AV-HuBERT lip reading model hosted on EC2 GPU instance.
    Sends frames S3 location to the server which downloads, processes, and returns predictions.
    """
    if not AVHUBERT_ENDPOINT:
        print("Warning: AVHUBERT_ENDPOINT not configured, skipping lip reading")
        return {**event, "lipreading": {"segments": [], "text": "", "note": "Endpoint not configured"}}
    
    media = event.get("media", {})
    input_obj = event.get("input", {})
    frames_prefix = media.get("frames_prefix")
    fps = media.get("fps", 25)
    bucket = input_obj.get("bucket")
    
    if not frames_prefix:
        print("Warning: No frames_prefix in media, skipping lip reading")
        return {**event, "lipreading": {"segments": [], "text": "", "note": "No frames extracted"}}
    
    payload = {
        "s3_bucket": bucket,
        "frames_prefix": frames_prefix,
        "fps": fps
    }
    
    try:
        print(f"Calling AV-HuBERT endpoint: {AVHUBERT_ENDPOINT}/predict")
        response = requests.post(
            f"{AVHUBERT_ENDPOINT}/predict",
            json=payload,
            timeout=TIMEOUT
        )
        response.raise_for_status()
        result = response.json()
        
        print(f"Lip reading result: {result.get('text', '')[:100]}...")
        
        return {**event, "lipreading": result}
    
    except requests.exceptions.Timeout:
        print(f"Timeout calling AV-HuBERT endpoint after {TIMEOUT}s")
        return {**event, "lipreading": {"segments": [], "text": "", "error": "Timeout"}}
    
    except Exception as e:
        print(f"Error calling AV-HuBERT endpoint: {e}")
        return {**event, "lipreading": {"segments": [], "text": "", "error": str(e)}}
