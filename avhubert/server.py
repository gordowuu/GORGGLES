"""
AV-HuBERT Inference Server for Gorggle
Serves lip reading predictions via REST API on EC2 GPU instance
"""
import os
import json
import torch
import boto3
import dlib
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path
import tempfile
import cv2
import numpy as np
from typing import List, Dict, Tuple, Union
import uvicorn

# Import AV-HuBERT components (assumes fairseq and av_hubert are installed)
try:
    from fairseq import checkpoint_utils, options, tasks, utils
    from fairseq.dataclass.utils import convert_namespace_to_omegaconf
except ImportError:
    print("Warning: fairseq not installed. Install with: pip install fairseq")

app = FastAPI(title="AV-HuBERT Lip Reading API", version="1.0.0")

# Global model holders
class PlaceholderModel:
    """Placeholder until AV-HuBERT checkpoint is loaded."""
    def __call__(self, *args, **kwargs):
        print("Warning: AV-HuBERT model not loaded; configure checkpoint path in startup")
        return None

MODEL = PlaceholderModel()
TASK = None
GENERATOR = None
FACE_DETECTOR = None
LANDMARK_PREDICTOR = None
MEAN_FACE = None

# Model and preprocessing file paths
MODEL_PATH = os.environ.get("AVHUBERT_MODEL_PATH", "/opt/avhubert/model.pt")
FACE_DETECTOR_PATH = os.environ.get("FACE_DETECTOR_PATH", "/opt/avhubert/mmod_human_face_detector.dat")
LANDMARK_PREDICTOR_PATH = os.environ.get("LANDMARK_PREDICTOR_PATH", "/opt/avhubert/shape_predictor_68_face_landmarks.dat")
MEAN_FACE_PATH = os.environ.get("MEAN_FACE_PATH", "/opt/avhubert/mean_face.npy")
s3_client = boto3.client('s3')

# Model configuration
MODEL_PATH = os.getenv("MODEL_PATH", "/home/ubuntu/av_hubert/models/large_vox_iter5.pt")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class PredictionRequest(BaseModel):
    s3_bucket: str
    frames_prefix: str = None
    s3_video_key: str = None  # Optional raw video path in S3 if frames are not provided
    fps: int = 25
    audio_s3_key: str = None  # Optional: for audio-visual mode


class PredictionResponse(BaseModel):
    text: str
    confidence: float
    segments: List[Dict]  # time-aligned segments


def load_model():
    """Load AV-HuBERT model and preprocessing models on startup"""
    global MODEL, TASK, GENERATOR, FACE_DETECTOR, LANDMARK_PREDICTOR, MEAN_FACE
    
    # Load AV-HuBERT model
    if not Path(MODEL_PATH).exists():
        raise FileNotFoundError(f"Model not found at {MODEL_PATH}")
    
    print(f"Loading AV-HuBERT model from {MODEL_PATH}...")
    models, saved_cfg, task = checkpoint_utils.load_model_ensemble_and_task([MODEL_PATH])
    MODEL = models[0].to(DEVICE)
    MODEL.eval()
    TASK = task
    
    # Setup generator for inference
    cfg = convert_namespace_to_omegaconf(saved_cfg)
    GENERATOR = task.build_generator(models, cfg)
    print(f"AV-HuBERT model loaded successfully on {DEVICE}")
    
    # Load face detection models
    if not Path(FACE_DETECTOR_PATH).exists():
        raise FileNotFoundError(f"Face detector not found at {FACE_DETECTOR_PATH}")
    if not Path(LANDMARK_PREDICTOR_PATH).exists():
        raise FileNotFoundError(f"Landmark predictor not found at {LANDMARK_PREDICTOR_PATH}")
    
    print("Loading dlib face detection models...")
    FACE_DETECTOR = dlib.cnn_face_detection_model_v1(FACE_DETECTOR_PATH)
    LANDMARK_PREDICTOR = dlib.shape_predictor(LANDMARK_PREDICTOR_PATH)
    print("Face detection models loaded successfully")
    
    # Load mean face for mouth ROI alignment
    if not Path(MEAN_FACE_PATH).exists():
        raise FileNotFoundError(f"Mean face not found at {MEAN_FACE_PATH}")
    
    MEAN_FACE = np.load(MEAN_FACE_PATH)
    print(f"Mean face loaded: shape {MEAN_FACE.shape}")


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


def download_video_from_s3(bucket: str, key: str, tmp_dir: Path) -> Path:
    """Download a video file from S3 to a temporary directory"""
    local_path = tmp_dir / "input.mp4"
    s3_client.download_file(bucket, key, str(local_path))
    return local_path


def extract_frames_from_video(video_path: Path, target_fps: int) -> List[np.ndarray]:
    """Extract frames from a video using OpenCV at approximately target_fps"""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError("Failed to open video with OpenCV")

    orig_fps = cap.get(cv2.CAP_PROP_FPS)
    if not orig_fps or orig_fps <= 0 or np.isnan(orig_fps):
        orig_fps = float(target_fps)

    frame_interval = max(1, int(round(orig_fps / float(target_fps))))
    frames: List[np.ndarray] = []
    idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if idx % frame_interval == 0:
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        idx += 1
    cap.release()

    if not frames:
        raise ValueError("No frames extracted from video")
    return frames


def warp_img(src: np.ndarray, dst: np.ndarray, img: np.ndarray, std_size: int) -> Tuple[np.ndarray, np.ndarray]:
    """Warp image based on facial landmarks for mouth ROI alignment"""
    tform = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=100)[0]
    warped = cv2.warpAffine(img, tform, (std_size, std_size))
    return warped, tform


def cut_patch(img: np.ndarray, landmarks: np.ndarray, height: int, width: int, threshold: int = 5) -> np.ndarray:
    """
    Cut mouth ROI patch from image using facial landmarks
    Landmarks indices for mouth: 48-68 (outer and inner lip)
    """
    center_x, center_y = np.mean(landmarks[48:68], axis=0).astype(int)
    
    if center_y - height < 0:
        center_y = height
    if center_y - height < 0 - threshold:
        raise Exception('too much bias in height')
    if center_x - width < 0:
        center_x = width
    if center_x - width < 0 - threshold:
        raise Exception('too much bias in width')

    if center_y + height > img.shape[0]:
        center_y = img.shape[0] - height
    if center_y + height > img.shape[0] + threshold:
        raise Exception('too much bias in height')
    if center_x + width > img.shape[1]:
        center_x = img.shape[1] - width
    if center_x + width > img.shape[1] + threshold:
        raise Exception('too much bias in width')
        
    cutted_img = np.copy(img[center_y - height:center_y + height, center_x - width:center_x + width])
    return cutted_img


def detect_face_and_extract_mouth(frame: np.ndarray) -> np.ndarray:
    """
    Detect face in frame and extract mouth ROI (96x96)
    Returns: mouth ROI as numpy array or None if no face detected
    """
    # Detect faces
    dets = FACE_DETECTOR(frame, 1)
    
    if len(dets) == 0:
        return None
    
    # Use first detected face (highest confidence)
    rect = dets[0].rect
    
    # Get facial landmarks
    shape = LANDMARK_PREDICTOR(frame, rect)
    landmarks = np.array([[p.x, p.y] for p in shape.parts()])
    
    # Warp image to align face with mean face
    warped_frame, _ = warp_img(landmarks, MEAN_FACE, frame, 256)
    warped_landmarks = LANDMARK_PREDICTOR(warped_frame, dlib.rectangle(0, 0, 256, 256))
    warped_landmarks = np.array([[p.x, p.y] for p in warped_landmarks.parts()])
    
    # Extract mouth patch (96x96 centered on mouth)
    try:
        mouth_roi = cut_patch(warped_frame, warped_landmarks, 48, 48)  # 96x96 patch
        mouth_roi = cv2.resize(mouth_roi, (96, 96))
        return mouth_roi
    except Exception as e:
        print(f"Error extracting mouth ROI: {e}")
        return None


def preprocess_frames(frames: List[Union[Path, np.ndarray]]) -> torch.Tensor:
    """
    Preprocess video frames for AV-HuBERT:
    1. Detect face in each frame
    2. Extract mouth ROI (96x96)
    3. Normalize and convert to tensor
    Returns: tensor of shape (T, C, H, W) where T is number of frames
    """
    mouth_rois: List[np.ndarray] = []
    
    for item in frames:
        # Support either file paths or in-memory images
        if isinstance(item, (str, Path)):
            img_bgr = cv2.imread(str(item))
            if img_bgr is None:
                continue
            img = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        else:
            img = item  # assumed RGB numpy array
        
        # Extract mouth ROI
        mouth_roi = detect_face_and_extract_mouth(img)
        
        if mouth_roi is None:
            # If face detection fails, skip frame or use previous frame
            if mouth_rois:
                mouth_roi = mouth_rois[-1]  # Repeat last valid frame
            else:
                continue  # Skip if no valid frames yet
        
        # Normalize to [0, 1]
        mouth_roi = mouth_roi.astype(np.float32) / 255.0
        
        mouth_rois.append(mouth_roi)
    
    if not mouth_rois:
        raise ValueError("No valid mouth ROIs extracted from frames")
    
    # Stack and convert to tensor (T, H, W, C) -> (T, C, H, W)
    frames_array = np.stack(mouth_rois, axis=0)
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
            'segments': []  # Time-aligned segments pending (requires fairseq decode with timestamps)
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
            
            frames_tensor: torch.Tensor

            if request.frames_prefix:
                # Download frames from S3
                print(f"Downloading frames from s3://{request.s3_bucket}/{request.frames_prefix}")
                frame_paths = download_frames_from_s3(request.s3_bucket, request.frames_prefix, tmp_path)
                if not frame_paths:
                    raise HTTPException(status_code=400, detail="No frames found at specified S3 location")
                print(f"Processing {len(frame_paths)} frames")
                frames_tensor = preprocess_frames(frame_paths)
            elif request.s3_video_key:
                # Fallback: download video and extract frames with OpenCV (no FFmpeg required)
                print(f"Downloading video from s3://{request.s3_bucket}/{request.s3_video_key}")
                video_path = download_video_from_s3(request.s3_bucket, request.s3_video_key, tmp_path)
                frames = extract_frames_from_video(video_path, request.fps)
                print(f"Processing {len(frames)} frames extracted via OpenCV")
                frames_tensor = preprocess_frames(frames)
            else:
                raise HTTPException(status_code=400, detail="Must provide frames_prefix or s3_video_key")
            
            # Run inference
            result = run_inference(frames_tensor)
            
            # Add coarse time-aligned segment covering full duration as a quick implementation
            duration = frames_tensor.size(0) / float(request.fps)
            if 'segments' in result and not result['segments']:
                result['segments'] = [{
                    'start': 0.0,
                    'end': duration,
                    'text': result.get('text', '')
                }]
            
            return PredictionResponse(**result)
    
    except Exception as e:
        print(f"Error during prediction: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    # Start server
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
