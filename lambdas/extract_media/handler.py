import os
import json
import boto3
import subprocess
import tempfile
import shutil
from pathlib import Path

s3 = boto3.client('s3')

PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "")
FRAMES_FPS = int(os.environ.get("FRAMES_FPS", "25"))


def handler(event, context):
    """
    Extract audio and video frames from uploaded MP4.
    Uses FFmpeg to extract:
    - Audio as WAV for potential local processing
    - Video frames at 25 fps for AV-HuBERT lip reading
    
    Note: AWS Transcribe and Rekognition work directly on MP4,
    so we only extract what's needed for lip reading model.
    """
    job_id = event.get("jobId")
    input_obj = event.get("input", {})
    bucket = input_obj.get("bucket")
    key = input_obj.get("key")

    # Create temp working directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        video_path = tmp_path / "input.mp4"
        audio_path = tmp_path / "audio.wav"
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()

        # Download video from S3
        s3.download_file(bucket, key, str(video_path))

        # Extract audio using FFmpeg
        subprocess.run([
            'ffmpeg', '-i', str(video_path),
            '-vn',  # no video
            '-acodec', 'pcm_s16le',  # PCM 16-bit
            '-ar', '16000',  # 16kHz sample rate
            '-ac', '1',  # mono
            str(audio_path)
        ], check=True, capture_output=True)

        # Extract frames at specified FPS for lip reading
        subprocess.run([
            'ffmpeg', '-i', str(video_path),
            '-vf', f'fps={FRAMES_FPS}',
            '-q:v', '2',  # high quality JPEG
            str(frames_dir / 'frame_%06d.jpg')
        ], check=True, capture_output=True)

        # Upload audio to S3
        audio_key = f"audio/{job_id}.wav"
        s3.upload_file(str(audio_path), bucket, audio_key)

        # Upload frames to S3
        frames_prefix = f"frames/{job_id}/"
        frame_files = sorted(frames_dir.glob("*.jpg"))
        for frame_file in frame_files:
            frame_key = frames_prefix + frame_file.name
            s3.upload_file(str(frame_file), bucket, frame_key)

    return {
        "jobId": job_id,
        "input": {"bucket": bucket, "key": key},
        "media": {
            "frames_prefix": frames_prefix,
            "frames_count": len(frame_files),
            "audio_s3": {"bucket": bucket, "key": audio_key},
            "fps": FRAMES_FPS
        }
    }
