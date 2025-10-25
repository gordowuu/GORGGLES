"""
AV-HuBERT Inference Server for Gorggle
Serves lip reading predictions via REST API on EC2 GPU instance
"""
import os
import json
import torch
import boto3
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path
import tempfile
import cv2
import numpy as np
from typing import List, Dict
import uvicorn

# Import AV-HuBERT components (assumes fairseq and av_hubert are installed)
try:
    from fairseq import checkpoint_utils, options, tasks, utils
    from fairseq.dataclass.utils import convert_namespace_to_omegaconf
except ImportError:
    print("Warning: fairseq not installed. Install with: pip install fairseq")

app = FastAPI(title="AV-HuBERT Lip Reading API", version="1.0.0")

# Global model holder
MODEL = None
TASK = None
GENERATOR = None
s3_client = boto3.client('s3')

# Model configuration
MODEL_PATH = os.getenv("MODEL_PATH", "/home/ubuntu/av_hubert/models/large_vox_iter5.pt")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class PredictionRequest(BaseModel):
    s3_bucket: str
    frames_prefix: str
    fps: int = 25
    audio_s3_key: str = None  # Optional: for audio-visual mode


class PredictionResponse(BaseModel):
    text: str
    confidence: float
    segments: List[Dict]  # time-aligned segments


def load_model():
    """Load AV-HuBERT model on startup"""
    global MODEL, TASK, GENERATOR
    
    if not Path(MODEL_PATH).exists():
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}")
    
    print(f"Loading AV-HuBERT model from {MODEL_PATH}...")
    
    # Load model checkpoint
    models, saved_cfg, task = checkpoint_utils.load_model_ensemble_and_task([MODEL_PATH])
    MODEL = models[0].to(DEVICE)
    MODEL.eval()
    TASK = task
    
    # Setup generator for inference
    cfg = convert_namespace_to_omegaconf(saved_cfg)
    GENERATOR = task.build_generator(models, cfg)
    
    print(f"Model loaded successfully on {DEVICE}")


def download_frames_from_s3(bucket: str, prefix: str, tmp_dir: Path) -> List[Path]:
    """Download video frames from S3"""
    frames_dir = tmp_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    
    # List objects with prefix
    response = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
    
    if 'Contents' not in response:
        return []
    
    frame_paths = []
    for obj in sorted(response['Contents'], key=lambda x: x['Key']):
        key = obj['Key']
        if key.endswith(('.jpg', '.jpeg', '.png')):
            local_path = frames_dir / Path(key).name
            s3_client.download_file(bucket, key, str(local_path))
            frame_paths.append(local_path)
    
    return frame_paths


def preprocess_frames(frame_paths: List[Path], target_size=(224, 224)) -> torch.Tensor:
    """
    Preprocess video frames for AV-HuBERT
    Returns: tensor of shape (T, C, H, W) where T is number of frames
    """
    frames = []
    for frame_path in frame_paths:
        img = cv2.imread(str(frame_path))
        if img is None:
            continue
        # Resize and normalize
        img = cv2.resize(img, target_size)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        # Normalize with ImageNet stats
        mean = np.array([0.485, 0.456, 0.406])
        std = np.array([0.229, 0.224, 0.225])
        img = (img - mean) / std
        frames.append(img)
    
    if not frames:
        raise ValueError("No valid frames found")
    
    # Stack and convert to tensor (T, H, W, C) -> (T, C, H, W)
    frames_array = np.stack(frames, axis=0)
    frames_tensor = torch.from_numpy(frames_array).permute(0, 3, 1, 2).float()
    
    return frames_tensor


def run_inference(frames_tensor: torch.Tensor) -> Dict:
    """
    Run AV-HuBERT inference on preprocessed frames
    Returns dictionary with text and confidence
    """
    with torch.no_grad():
        frames_tensor = frames_tensor.to(DEVICE)
        
        # Prepare sample for model (simplified - adjust based on actual AV-HuBERT API)
        sample = {
            'net_input': {
                'video': frames_tensor.unsqueeze(0),  # Add batch dimension
                'video_mask': torch.ones(1, frames_tensor.size(0), dtype=torch.bool).to(DEVICE)
            }
        }
        
        # Generate predictions
        hypos = GENERATOR.generate([MODEL], sample)
        
        # Decode hypothesis
        hypo = hypos[0][0]  # Best hypothesis for first sample
        text = TASK.target_dictionary.string(hypo['tokens'].int().cpu())
        confidence = hypo['score'].exp().item() if 'score' in hypo else 1.0
        
        return {
            'text': text.strip(),
            'confidence': confidence,
            'segments': []  # TODO: Add time-aligned segments
        }


@app.on_event("startup")
async def startup_event():
    """Load model on server startup"""
    load_model()


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "device": DEVICE,
        "model_loaded": MODEL is not None
    }


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    """
    Predict text from video frames using lip reading
    """
    if MODEL is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # Download frames from S3
            print(f"Downloading frames from s3://{request.s3_bucket}/{request.frames_prefix}")
            frame_paths = download_frames_from_s3(request.s3_bucket, request.frames_prefix, tmp_path)
            
            if not frame_paths:
                raise HTTPException(status_code=400, detail="No frames found at specified S3 location")
            
            print(f"Processing {len(frame_paths)} frames")
            
            # Preprocess frames
            frames_tensor = preprocess_frames(frame_paths)
            
            # Run inference
            result = run_inference(frames_tensor)
            
            return PredictionResponse(**result)
    
    except Exception as e:
        print(f"Error during prediction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # Start server
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
