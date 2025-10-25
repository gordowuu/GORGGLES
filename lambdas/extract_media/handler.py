import os
import json
import boto3
import logging
import subprocess
import tempfile
import shutil
from pathlib import Path

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3 = boto3.client('s3')

PROCESSED_BUCKET = os.environ.get("PROCESSED_BUCKET", "")
FRAMES_FPS = int(os.environ.get("FRAMES_FPS", "25"))
FFMPEG_PATH = os.environ.get("FFMPEG_PATH", "ffmpeg")  # Use /opt/bin/ffmpeg in Lambda layer

def handler(event, context):
    """
    Extract audio and frames from uploaded MP4 using FFmpeg when available.
    If FFmpeg is not present, skip extraction (workaround) and let EC2 handle it.
    """
    try:
        logger.info(f"Starting media extraction. Event: {json.dumps(event)}")

        job_id = event.get("jobId")
        input_obj = event.get("input", {})
        bucket = input_obj.get("bucket")
        key = input_obj.get("key")

        if not all([job_id, bucket, key]):
            raise ValueError(f"Missing required parameters: jobId={job_id}, bucket={bucket}, key={key}")

        logger.info(f"Processing job {job_id}: s3://{bucket}/{key}")

        # Defaults if extraction is skipped (FFmpeg unavailable)
        frames_prefix = ""
        frame_files: list = []
        audio_key = ""

        target_bucket = PROCESSED_BUCKET if PROCESSED_BUCKET else bucket

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            video_path = tmp_path / "input.mp4"
            audio_path = tmp_path / "audio.wav"
            frames_dir = tmp_path / "frames"
            frames_dir.mkdir(exist_ok=True)

            # Download video from S3
            logger.info("Downloading video from S3...")
            s3.download_file(bucket, key, str(video_path))
            logger.info(f"Downloaded video: {video_path.stat().st_size / (1024 * 1024):.2f} MB")

            try:
                # Extract audio
                logger.info("Extracting audio with FFmpeg...")
                subprocess.run([
                    FFMPEG_PATH, '-y', '-i', str(video_path),
                    '-vn',
                    '-acodec', 'pcm_s16le',
                    '-ar', '16000',
                    '-ac', '1',
                    str(audio_path)
                ], check=True, capture_output=True, text=True)

                if audio_path.exists():
                    audio_key = f"audio/{job_id}.wav"
                    s3.upload_file(str(audio_path), target_bucket, audio_key)
                    logger.info(f"Audio uploaded to s3://{target_bucket}/{audio_key}")
                else:
                    logger.warning("Audio extraction reported success but file missing.")

                # Extract frames
                logger.info(f"Extracting frames at {FRAMES_FPS} FPS with FFmpeg...")
                subprocess.run([
                    FFMPEG_PATH, '-y', '-i', str(video_path),
                    '-vf', f'fps={FRAMES_FPS}',
                    '-q:v', '2',
                    str(frames_dir / 'frame_%06d.jpg')
                ], check=True, capture_output=True, text=True)

                frame_files = sorted(frames_dir.glob("*.jpg"))
                if frame_files:
                    frames_prefix = f"frames/{job_id}/"
                    for frame_file in frame_files:
                        frame_key = frames_prefix + frame_file.name
                        s3.upload_file(str(frame_file), target_bucket, frame_key)
                    logger.info(f"Uploaded {len(frame_files)} frames to s3://{target_bucket}/{frames_prefix}")
                else:
                    logger.warning("No frames extracted by FFmpeg.")

            except (FileNotFoundError, subprocess.CalledProcessError) as e:
                logger.warning(f"FFmpeg unavailable or failed, skipping extraction (workaround). Reason: {e}")

        result = {
            "jobId": job_id,
            "input": {"bucket": bucket, "key": key},
            "media": {
                "frames_prefix": frames_prefix,
                "frames_count": len(frame_files),
                "audio_s3": {"bucket": target_bucket, "key": audio_key} if audio_key else None,
                "fps": FRAMES_FPS
            }
        }

        logger.info(f"Media extraction complete for job {job_id}")
        return result

    except Exception as e:
        logger.error("Unexpected error in extract_media", exc_info=True)
        raise RuntimeError(str(e)) from e
