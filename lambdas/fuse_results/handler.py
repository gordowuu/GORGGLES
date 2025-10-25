import os
import json
import boto3
import requests
import logging
from decimal import Decimal
from typing import List, Dict, Any

logger = logging.getLogger()
logger.setLevel(logging.INFO)

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


def download_transcript(transcript_uri: str) -> Dict:
    """Download and parse Transcribe JSON transcript"""
    try:
        response = requests.get(transcript_uri, timeout=30)
        return response.json()
    except Exception as e:
        print(f"Error downloading transcript: {e}")
        return {}


def align_speakers_with_faces(transcribe_data: Dict, rekognition_faces: List[Dict], fps: float = 25.0) -> List[Dict]:
    """
    Align speaker segments from Transcribe with face detections from Rekognition.
    
    Returns list of aligned segments with:
    - timestamp
    - speaker_label
    - text
    - face_bbox (if matched)
    - confidence
    """
    aligned_segments = []
    
    # Parse Transcribe results
    results = transcribe_data.get('results', {})
    items = results.get('items', [])
    speaker_labels = results.get('speaker_labels', {})
    segments = speaker_labels.get('segments', [])
    
    for segment in segments:
        start_time = float(segment.get('start_time', 0))
        end_time = float(segment.get('end_time', 0))
        speaker = segment.get('speaker_label', 'spk_UNKNOWN')
        
        # Get text for this segment
        segment_items = segment.get('items', [])
        words = []
        for item_idx in segment_items:
            # Find matching item
            for item in items:
                if item.get('type') == 'pronunciation' and \
                   abs(float(item.get('start_time', 0)) - start_time) < 0.1:
                    words.append(item.get('alternatives', [{}])[0].get('content', ''))
        
        text = ' '.join(words)
        
        # Find face at this timestamp (convert to milliseconds)
        mid_time_ms = (start_time + end_time) / 2 * 1000
        matched_face = None
        
        for face_detection in rekognition_faces:
            timestamp = face_detection.get('Timestamp', 0)
            if abs(timestamp - mid_time_ms) < 500:  # Within 500ms
                matched_face = face_detection.get('Face', {})
                break
        
        aligned_segments.append({
            'start_time': start_time,
            'end_time': end_time,
            'speaker': speaker,
            'text': text,
            'face': matched_face.get('BoundingBox') if matched_face else None,
            'face_confidence': matched_face.get('Confidence') if matched_face else None
        })
    
    return aligned_segments


def fuse_audio_and_visual(aligned_segments: List[Dict], lipreading_result: Dict) -> List[Dict]:
    """
    Fuse audio transcription with lip reading results.
    Use lip reading to fill gaps or correct low-confidence audio segments.
    """
    lipreading_text = lipreading_result.get('text', '')
    lipreading_confidence = lipreading_result.get('confidence', 0.0)
    
    fused_segments = []
    
    for segment in aligned_segments:
        # Start with audio transcript
        fused_segment = segment.copy()
        fused_segment['source'] = 'audio'
        fused_segment['audio_text'] = segment['text']
        
        # If we have high-confidence lip reading and low audio quality, use visual
        # This is a simplified heuristic - production would need proper alignment
        if lipreading_confidence > 0.8 and lipreading_text:
            fused_segment['lipreading_text'] = lipreading_text
            fused_segment['note'] = 'Audio transcript available, lip reading can provide correction if needed'
        
        fused_segments.append(fused_segment)
    
    return fused_segments


def handler(event, context):
    try:
        job_id = event.get("jobId")
        if not job_id:
            raise ValueError("Missing jobId in event")

        transcribe_result = event.get("transcribe", {}).get("result", {})
        rekognition = event.get("rekognition", {})
        lipreading = event.get("lipreading", {})
        media = event.get("media", {})

        # Download full transcript from Transcribe
        transcript_uri = transcribe_result.get('Transcript', {}).get('TranscriptFileUri')
        transcribe_data = {}
        if transcript_uri:
            transcribe_data = download_transcript(transcript_uri)

        # Get face detections
        faces = rekognition.get("faces", [])
        fps = media.get('fps', 25)

        # Align speakers with face positions
        aligned_segments = align_speakers_with_faces(transcribe_data, faces, fps)

        # Fuse audio and visual information
        fused_segments = fuse_audio_and_visual(aligned_segments, lipreading)

        # Build final overlay data
        fusion = {
            "jobId": job_id,
            "segments": fused_segments,
            "metadata": {
                "total_segments": len(fused_segments),
                "speakers_detected": len(set(s.get('speaker') for s in fused_segments if 'speaker' in s)),
                "faces_tracked": len(faces),
                "lipreading_available": bool(lipreading.get('text')),
                "lipreading_confidence": lipreading.get('confidence', 0.0)
            },
            "raw": {
                "transcribe_status": transcribe_result.get('TranscriptionJobStatus'),
                "rekognition_status": rekognition.get('status'),
                "lipreading_note": lipreading.get('note', '')
            }
        }

        key = f"results/{job_id}/overlay.json"
        s3.put_object(
            Bucket=PROCESSED_BUCKET,
            Key=key,
            Body=json.dumps(fusion, default=_decimalize).encode('utf-8'),
            ContentType='application/json'
        )

        ddb.put_item(
            TableName=JOBS_TABLE,
            Item={
                'jobId': {'S': job_id},
                'resultKey': {'S': key},
                'status': {'S': 'COMPLETED'}
            }
        )

        return {"processed": {"bucket": PROCESSED_BUCKET, "key": key}}
    except Exception as e:
        logger.error(f"Error fusing results: {e}", exc_info=True)
        # Don't raise to avoid failing the entire pipeline; return partial result
        return {"error": str(e)}
