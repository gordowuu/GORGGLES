"""
SageMaker inference handler for LipCoordNet model from HuggingFace Hub.
This uses the HuggingFace Inference Toolkit with custom inference logic.
"""
import json
import logging
import os
import sys
import tempfile
import numpy as np
import torch
import cv2
import boto3
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Model will be loaded from HuggingFace Hub: SilentSpeak/LipCoordNet
# Input: Video frames (128x64 grayscale) + lip landmark coordinates
# Output: Transcribed text

def model_fn(model_dir):
    """
    Load the LipCoordNet model from the model directory.
    For HuggingFace models, this typically loads from the Hub.
    """
    try:
        logger.info(f"Loading LipCoordNet model from {model_dir}")
        
        # Import after model directory is available
        from transformers import AutoModel, AutoConfig
        
        # Load model configuration
        config = AutoConfig.from_pretrained(model_dir, trust_remote_code=True)
        
        # Load the model
        model = AutoModel.from_pretrained(
            model_dir,
            config=config,
            trust_remote_code=True
        )
        
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        model.to(device)
        model.eval()
        
        logger.info(f"Model loaded successfully on {device}")
        return {'model': model, 'device': device}
        
    except Exception as e:
        logger.error(f"Error loading model: {e}", exc_info=True)
        # Return a placeholder to keep endpoint running
        return {'model': None, 'device': 'cpu', 'error': str(e)}


def input_fn(request_body, content_type='application/json'):
    """
    Deserialize and prepare the prediction input.
    
    Expected input format:
    {
        "s3_bucket": "bucket-name",
        "s3_video_key": "path/to/video.mp4",
        "fps": 25  # optional, defaults to 25
    }
    """
    logger.info(f"Processing input with content_type: {content_type}")
    
    if content_type == 'application/json':
        data = json.loads(request_body)
        return data
    else:
        raise ValueError(f"Unsupported content type: {content_type}")


def predict_fn(data, model_context):
    """
    Perform prediction on the deserialized data.
    """
    try:
        model = model_context.get('model')
        device = model_context.get('device', 'cpu')
        
        if model is None:
            error_msg = model_context.get('error', 'Model not loaded')
            return {
                'text': '',
                'error': f'Model loading failed: {error_msg}',
                'status': 'error'
            }
        
        # Extract S3 video location
        s3_bucket = data.get('s3_bucket')
        s3_video_key = data.get('s3_video_key')
        fps = data.get('fps', 25)
        
        if not s3_bucket or not s3_video_key:
            return {
                'text': '',
                'error': 'Missing s3_bucket or s3_video_key in request',
                'status': 'error'
            }
        
        logger.info(f"Processing video: s3://{s3_bucket}/{s3_video_key}")
        
        # Download video from S3
        s3 = boto3.client('s3')
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_video:
            video_path = tmp_video.name
            s3.download_file(s3_bucket, s3_video_key, video_path)
        
        try:
            # Extract frames and landmarks
            frames, landmarks = extract_frames_and_landmarks(video_path, target_fps=fps)
            
            if frames is None or len(frames) == 0:
                return {
                    'text': '',
                    'error': 'Failed to extract frames from video',
                    'status': 'error'
                }
            
            # Prepare inputs for model
            # LipCoordNet expects:
            # - frames: (batch, channels, time, height, width) - grayscale 128x64
            # - landmarks: (batch, time, num_landmarks * 2) - x,y coordinates
            
            frames_tensor = torch.FloatTensor(frames).unsqueeze(0).to(device)  # Add batch dim
            landmarks_tensor = torch.FloatTensor(landmarks).unsqueeze(0).to(device)  # Add batch dim
            
            logger.info(f"Input shapes - frames: {frames_tensor.shape}, landmarks: {landmarks_tensor.shape}")
            
            # Run inference
            with torch.no_grad():
                outputs = model(frames=frames_tensor, landmarks=landmarks_tensor)
            
            # Decode output to text
            # This depends on the model's output format
            # For now, assume it returns logits that need to be decoded
            predicted_text = decode_prediction(outputs)
            
            return {
                'text': predicted_text,
                'status': 'success',
                'num_frames': len(frames)
            }
            
        finally:
            # Clean up temporary file
            if os.path.exists(video_path):
                os.remove(video_path)
        
    except Exception as e:
        logger.error(f"Prediction error: {e}", exc_info=True)
        return {
            'text': '',
            'error': str(e),
            'status': 'error'
        }


def output_fn(prediction, accept='application/json'):
    """
    Serialize the prediction output.
    """
    if accept == 'application/json':
        return json.dumps(prediction), accept
    else:
        raise ValueError(f"Unsupported accept type: {accept}")


def extract_frames_and_landmarks(video_path, target_fps=25):
    """
    Extract frames and lip landmarks from video.
    
    Returns:
        frames: numpy array of shape (time, channels, height, width)
        landmarks: numpy array of shape (time, num_landmarks * 2)
    """
    try:
        import dlib
        
        # Load face detector and landmark predictor
        detector = dlib.get_frontal_face_detector()
        predictor_path = "/opt/ml/model/shape_predictor_68_face_landmarks.dat"
        
        if not os.path.exists(predictor_path):
            logger.warning("dlib shape predictor not found, using basic frame extraction")
            return extract_frames_only(video_path, target_fps)
        
        predictor = dlib.shape_predictor(predictor_path)
        
        cap = cv2.VideoCapture(video_path)
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        frame_skip = max(1, int(video_fps / target_fps))
        
        frames = []
        landmarks_list = []
        frame_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            if frame_count % frame_skip == 0:
                # Convert to grayscale
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                
                # Detect face
                faces = detector(gray, 1)
                
                if len(faces) > 0:
                    # Get landmarks for first face
                    shape = predictor(gray, faces[0])
                    
                    # Extract lip landmarks (points 48-67 are mouth landmarks)
                    lip_landmarks = []
                    for i in range(48, 68):
                        lip_landmarks.append(shape.part(i).x)
                        lip_landmarks.append(shape.part(i).y)
                    
                    # Crop and resize mouth region
                    mouth_frame = extract_mouth_roi(frame, shape)
                    
                    # Resize to 128x64 (LipCoordNet input size)
                    mouth_frame = cv2.resize(mouth_frame, (128, 64))
                    mouth_gray = cv2.cvtColor(mouth_frame, cv2.COLOR_BGR2GRAY)
                    
                    # Normalize
                    mouth_gray = mouth_gray.astype(np.float32) / 255.0
                    
                    frames.append(mouth_gray)
                    landmarks_list.append(lip_landmarks)
            
            frame_count += 1
        
        cap.release()
        
        if len(frames) == 0:
            return None, None
        
        # Convert to numpy arrays with proper shapes
        # frames: (time, height, width) -> add channel dim
        frames_array = np.array(frames)  # (time, 64, 128)
        frames_array = np.expand_dims(frames_array, axis=1)  # (time, 1, 64, 128)
        frames_array = np.transpose(frames_array, (1, 0, 2, 3))  # (1, time, 64, 128)
        
        landmarks_array = np.array(landmarks_list)  # (time, 40) - 20 landmarks * 2 coords
        
        return frames_array, landmarks_array
        
    except ImportError:
        logger.warning("dlib not available, using basic frame extraction")
        return extract_frames_only(video_path, target_fps)
    except Exception as e:
        logger.error(f"Error extracting frames and landmarks: {e}")
        return None, None


def extract_frames_only(video_path, target_fps=25):
    """
    Fallback: Extract frames without landmarks.
    """
    try:
        cap = cv2.VideoCapture(video_path)
        video_fps = cap.get(cv2.CAP_PROP_FPS)
        frame_skip = max(1, int(video_fps / target_fps))
        
        frames = []
        frame_count = 0
        
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            
            if frame_count % frame_skip == 0:
                # Convert to grayscale and resize
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                resized = cv2.resize(gray, (128, 64))
                normalized = resized.astype(np.float32) / 255.0
                frames.append(normalized)
            
            frame_count += 1
        
        cap.release()
        
        if len(frames) == 0:
            return None, None
        
        frames_array = np.array(frames)
        frames_array = np.expand_dims(frames_array, axis=1)
        frames_array = np.transpose(frames_array, (1, 0, 2, 3))
        
        # Create dummy landmarks (zeros)
        landmarks_array = np.zeros((len(frames), 40))
        
        return frames_array, landmarks_array
        
    except Exception as e:
        logger.error(f"Error in basic frame extraction: {e}")
        return None, None


def extract_mouth_roi(frame, shape):
    """
    Extract mouth region of interest from frame using landmarks.
    """
    # Get mouth landmarks (points 48-67)
    mouth_points = []
    for i in range(48, 68):
        mouth_points.append((shape.part(i).x, shape.part(i).y))
    
    mouth_points = np.array(mouth_points)
    
    # Get bounding box
    x_min, y_min = mouth_points.min(axis=0)
    x_max, y_max = mouth_points.max(axis=0)
    
    # Add padding
    padding = 20
    x_min = max(0, x_min - padding)
    y_min = max(0, y_min - padding)
    x_max = min(frame.shape[1], x_max + padding)
    y_max = min(frame.shape[0], y_max + padding)
    
    # Crop
    mouth_roi = frame[y_min:y_max, x_min:x_max]
    
    return mouth_roi


def decode_prediction(outputs):
    """
    Decode model outputs to text.
    This is a placeholder - actual implementation depends on model output format.
    """
    # TODO: Implement proper CTC decoding or sequence decoding
    # For now, return a placeholder
    return "Transcription not yet implemented - model output received"
