"""
SageMaker PyTorch inference script for AV-HuBERT lip reading.

Accepts JSON with either:
    { "s3_bucket": ..., "frames_prefix": ... }
    or { "s3_bucket": ..., "s3_video_key": ... }

Returns a JSON like:
    { "text": str, "segments": [ { "start": float, "end": float, "text": str } ], "note"?: str }

Design notes:
- Loads a fairseq AV-HuBERT checkpoint when available (placed as /opt/ml/model/avhubert.pt).
- Installs extra deps from code/requirements.txt (opencv, fairseq, sentencepiece).
- Gracefully degrades to placeholders if heavy deps are missing, so endpoint stays responsive.
"""

import os
import sys
import io
import json
import time
import logging
import boto3
import numpy as np

# Optional heavy deps
try:
    import dlib  # type: ignore
    DLIB_OK = True
except Exception:
    DLIB_OK = False

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

s3 = boto3.client('s3')

# Environment passed from model deployment (optional)
MODEL_S3_BUCKET = os.environ.get('MODEL_S3_BUCKET', '')
MODEL_S3_KEY = os.environ.get('MODEL_S3_KEY', '')
SHAPE_PREDICTOR_URL = os.environ.get('SHAPE_PREDICTOR_URL', 'http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2')

PREDICTOR_PATH = '/opt/ml/model/shape_predictor_68_face_landmarks.dat'
CHECKPOINT_PATH = '/opt/ml/model/avhubert.pt'

class PlaceholderModel:
    """Placeholder until AV-HuBERT checkpoint is loaded in model_fn."""
    def __call__(self, *args, **kwargs):
        logger.warning("Model not loaded; returning placeholder transcript")
        return None

MODEL = PlaceholderModel()


def download_if_missing(bucket, key, local_path):
    if os.path.exists(local_path):
        return local_path
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    s3.download_file(bucket, key, local_path)
    return local_path


def _maybe_download_shape_predictor():
    if os.path.exists(PREDICTOR_PATH):
        return True
    try:
        import bz2
        import urllib.request
        os.makedirs(os.path.dirname(PREDICTOR_PATH), exist_ok=True)
        tmp_bz2 = PREDICTOR_PATH + '.bz2'
        logger.info('Downloading dlib shape predictor...')
        urllib.request.urlretrieve(SHAPE_PREDICTOR_URL, tmp_bz2)
        with bz2.BZ2File(tmp_bz2) as fr, open(PREDICTOR_PATH, 'wb') as fw:
            fw.write(fr.read())
        os.remove(tmp_bz2)
        return True
    except Exception as e:
        logger.warning(f"Failed to download shape predictor: {e}")
        return False


def model_fn(model_dir):
    """Load the AV-HuBERT model and return an inference context."""
    global MODEL

    # If env variables provided, pull model from S3 into model_dir
    if MODEL_S3_BUCKET and MODEL_S3_KEY:
        try:
            download_if_missing(MODEL_S3_BUCKET, MODEL_S3_KEY, CHECKPOINT_PATH)
            logger.info(f"Model checkpoint downloaded to {CHECKPOINT_PATH}")
        except Exception as e:
            logger.warning(f"Failed to download checkpoint: {e}")

    # Attempt to prepare dlib predictor if available (optional ROI boost)
    if DLIB_OK:
        _maybe_download_shape_predictor()

    # Try to load fairseq AV-HuBERT if checkpoint is present and fairseq is installed
    if os.path.exists(CHECKPOINT_PATH):
        try:
            import torch
            # Make vendored av_hubert package importable if present under code/av_hubert
            # The structure is: code/av_hubert/avhubert/__init__.py
            # So we add code/av_hubert to sys.path and then import avhubert
            code_dir = os.path.join(model_dir, 'code')
            vendor_root = os.path.join(code_dir, 'av_hubert')
            avhubert_pkg = os.path.join(vendor_root, 'avhubert')
            
            if os.path.isdir(avhubert_pkg):
                # Add the parent directory so 'import avhubert' works
                if vendor_root not in sys.path:
                    sys.path.insert(0, vendor_root)
                    logger.info(f"Added vendored av_hubert root to sys.path: {vendor_root}")
                
                # Import avhubert to register the custom task BEFORE loading checkpoint
                try:
                    import avhubert  # type: ignore # noqa: F401
                    logger.info("avhubert module imported successfully; custom Fairseq task should now be registered")
                except Exception as e:
                    logger.warning(f"Failed to import avhubert module: {e}; checkpoint loading will likely fail")
            else:
                logger.warning(f"Vendored avhubert package not found at {avhubert_pkg}; checkpoint loading may fail")
            from fairseq import checkpoint_utils
            from fairseq.dataclass.utils import convert_namespace_to_omegaconf
            from omegaconf import open_dict

            logger.info(f"Loading AV-HuBERT from {CHECKPOINT_PATH} ...")
            
            # Use arg_overrides to set missing config keys
            arg_overrides = {
                'task.input_modality': 'video',  # Override missing key for video-only lip reading
            }
            
            models, saved_cfg, task = checkpoint_utils.load_model_ensemble_and_task(
                [CHECKPOINT_PATH],
                arg_overrides=arg_overrides
            )
            logger.info("Model loaded with arg_overrides: task.input_modality='video'")
            
            model = models[0]
            model.eval()
            device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
            model.to(device)

            # Patch task.cfg for build_generator if needed
            if hasattr(task, 'cfg') and not hasattr(task.cfg, 'input_modality'):
                with open_dict(task.cfg):
                    task.cfg.input_modality = 'video'
                    logger.info("Patched task.cfg.input_modality='video'")

            # Build generator
            cfg = convert_namespace_to_omegaconf(saved_cfg)
            generator = task.build_generator(models, cfg)

            # Keep a lightweight context object instead of global mutable state
            context = {
                'model': model,
                'task': task,
                'generator': generator,
                'device': device,
            }
            logger.info("AV-HuBERT model loaded successfully")
            return context
        except Exception as e:
            logger.exception(f"Failed to load AV-HuBERT model, falling back to placeholder: {e}")

    # Fallback: placeholder context so endpoint remains responsive
    logger.info("Using placeholder model; provide avhubert.pt in model.tar.gz or via S3 to enable real inference")
    return {
        'model': PlaceholderModel(),
        'task': None,
        'generator': None,
        'device': 'cpu',
    }


def _extract_mouth_roi(frame_bgr):
    # Best-effort mouth ROI using dlib if available; else return center crop
    h, w = frame_bgr.shape[:2]
    # Lazy import cv2 to avoid import-time failures if not installed
    try:
        import cv2  # type: ignore
    except Exception:
        cv2 = None  # type: ignore

    if DLIB_OK and os.path.exists(PREDICTOR_PATH) and 'cv2' in globals() and cv2 is not None:
        try:
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            detector = dlib.get_frontal_face_detector()
            shapes = dlib.shape_predictor(PREDICTOR_PATH)
            dets = detector(gray, 1)
            if len(dets) > 0:
                shape = shapes(gray, dets[0])
                points = np.array([(shape.part(i).x, shape.part(i).y) for i in range(48, 68)])
                x, y, w0, h0 = cv2.boundingRect(points)
                pad = int(0.2 * max(w0, h0))
                x0 = max(0, x - pad)
                y0 = max(0, y - pad)
                x1 = min(w, x + w0 + pad)
                y1 = min(h, y + h0 + pad)
                roi = frame_bgr[y0:y1, x0:x1]
                return cv2.resize(roi, (96, 96))
        except Exception as e:
            logger.warning(f"dlib ROI extraction failed: {e}")
    # fallback: center crop
    side = min(h, w)
    cx, cy = w // 2, h // 2
    half = side // 2
    roi = frame_bgr[cy - half:cy + half, cx - half:cx + half]
    try:
        import cv2  # type: ignore
        return cv2.resize(roi, (96, 96))
    except Exception:
        # If cv2 is not available, return raw roi (96x96 expected by downstream, but we can't resize)
        return roi


def _extract_frames_from_video(bucket, key, fps=25):
    # Lazy import cv2
    try:
        import cv2  # type: ignore
    except Exception as e:
        logger.warning("OpenCV (cv2) not available; returning empty frames list for graceful fallback.")
        return [], 0  # return empty frames, 0 fps

    local_mp4 = f"/tmp/input.mp4"
    s3.download_file(bucket, key, local_mp4)
    cap = cv2.VideoCapture(local_mp4)
    orig_fps = cap.get(cv2.CAP_PROP_FPS) or 25
    interval = max(1, int(round(orig_fps / max(1, fps))))
    frames = []
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % interval == 0:
            frames.append(_extract_mouth_roi(frame))
        i += 1
        if len(frames) > 2000:  # safety cap (~80s at 25fps interval)
            break
    cap.release()
    return frames, int(orig_fps)


def predict_fn(input_data, context):
    """Run preprocessing and model inference.

    context is the object returned by model_fn (contains model/task/generator/device).
    """
    # input_data: JSON dict
    bucket = input_data.get('s3_bucket')
    frames_prefix = input_data.get('frames_prefix')
    s3_video_key = input_data.get('s3_video_key')
    fps = int(input_data.get('fps', 25))

    if not bucket:
        return {"text": "", "segments": [], "error": "Missing s3_bucket"}

    frames = []
    duration_s = 0.0

    if s3_video_key:
        t0 = time.time()
        frames, orig_fps = _extract_frames_from_video(bucket, s3_video_key, fps=fps)
        if len(frames) == 0:
            logger.warning("No frames extracted (likely OpenCV missing); returning placeholder transcript.")
            return {
                "text": "[placeholder: OpenCV not available in container; install opencv-python-headless and redeploy]",
                "segments": [],
                "note": "SageMaker endpoint returned placeholder due to missing OpenCV dependency"
            }
        duration_s = max(1.0, len(frames) / float(max(1, fps)))
        logger.info(f"Extracted {len(frames)} frames in {time.time()-t0:.2f}s (fps={fps})")
    else:
        # Pre-extracted frames support not yet implemented
        logger.info("No video key provided; expecting frames_prefix path (not yet implemented)")
        return {
            "text": "",
            "segments": [],
            "note": "frames_prefix support not yet implemented; provide s3_video_key instead"
        }

    # If we don't have a real model, return a clear placeholder
    model = context.get('model')
    task = context.get('task')
    generator = context.get('generator')
    device = context.get('device', 'cpu')

    if task is None or generator is None or not hasattr(model, 'eval'):
        decoded_text = "[AV-HuBERT model not loaded; provide avhubert.pt in model.tar.gz or via S3 env vars]"
        return {
            "text": decoded_text,
            "segments": [{"start": 0.0, "end": duration_s, "text": decoded_text}],
            "note": "Endpoint operational; awaiting AV-HuBERT checkpoint to enable real inference"
        }

    # Prepare frames to tensor
    try:
        import torch
        frames_tensor = []
        for f in frames:
            roi = _extract_mouth_roi(f)
            if roi is None:
                # fallback to center crop used earlier
                roi = f
            roi = roi.astype(np.float32) / 255.0
            frames_tensor.append(roi)
        if not frames_tensor:
            raise RuntimeError("No frames prepared for model")
        arr = np.stack(frames_tensor, axis=0)  # (T, H, W, C)
        x = torch.from_numpy(arr).permute(0, 3, 1, 2).float()  # (T, C, H, W)

        sample = {
            'net_input': {
                'video': x.unsqueeze(0).to(device),  # (B=1, T, C, H, W)
                'video_mask': torch.ones(1, x.size(0), dtype=torch.bool, device=device)
            }
        }

        with torch.no_grad():
            hypos = generator.generate([model], sample)
        hypo = hypos[0][0]
        text = task.target_dictionary.string(hypo['tokens'].int().cpu())
        text = text.strip()

        result = {
            "text": text,
            "segments": [{"start": 0.0, "end": duration_s, "text": text}],
        }
        return result
    except Exception as e:
        logger.exception(f"Inference failed; returning placeholder: {e}")
        decoded_text = "[inference failed; see logs]"
        return {
            "text": decoded_text,
            "segments": [{"start": 0.0, "end": duration_s, "text": decoded_text}],
            "error": str(e)
        }


def input_fn(serialized_input, content_type='application/json'):
    if content_type == 'application/json':
        # Allow dicts to pass through (unit tests etc.)
        if isinstance(serialized_input, dict):
            return serialized_input
        # Decode bytes, tolerate UTF-8 BOM
        if isinstance(serialized_input, (bytes, bytearray)):
            try:
                serialized_input = serialized_input.decode('utf-8')
            except UnicodeDecodeError:
                serialized_input = serialized_input.decode('utf-8-sig')
        # Strip BOM if present
        if isinstance(serialized_input, str) and serialized_input.startswith('\ufeff'):
            serialized_input = serialized_input.lstrip('\ufeff')
        return json.loads(serialized_input or '{}')
    raise ValueError(f'Unsupported content_type: {content_type}')


def output_fn(prediction, accept='application/json'):
    return json.dumps(prediction), 'application/json'
