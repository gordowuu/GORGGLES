# Gorggle Architecture Deep Dive

## Pipeline Flow

### 1. Upload (S3 Event Trigger)
- User uploads MP4 to `s3://gorggle-dev-uploads/uploads/<filename>.mp4`
- S3 event notification triggers `s3_trigger` Lambda
- Lambda starts Step Functions execution with jobId

### 2. Extract Media (`extract_media` Lambda)
**Purpose**: Extract audio and video frames for processing

**Current Implementation**: 
- Uses FFmpeg (needs Lambda Layer or Container Image)
- Extracts audio as WAV (16kHz, mono) → `s3://bucket/audio/<jobId>.wav`
- Extracts frames at 25 FPS → `s3://bucket/frames/<jobId>/frame_NNNNNN.jpg`

**Why FFmpeg instead of MediaConvert?**
- MediaConvert is overkill for simple extraction (designed for transcoding)
- FFmpeg in Lambda is cheaper (~$0.0001/sec vs MediaConvert ~$0.0075/min)
- Lower latency (synchronous vs asynchronous job submission)
- Sufficient for our use case (just need raw frames + audio)

**Requirements**:
- FFmpeg Lambda Layer ARN or use Container Image with FFmpeg pre-installed
- Timeout: 900s (15 min) for large videos
- Memory: 1024MB+ for frame extraction
- Ephemeral storage: 10GB (default 512MB may not be enough)

### 3. Start Transcribe (`start_transcribe` Lambda)
**Purpose**: Convert audio to text with speaker diarization

**Implementation**:
- Calls AWS Transcribe with MP4 directly (no extraction needed!)
- Enables speaker labels (up to 5 speakers)
- Polls for completion (blocks Lambda execution)

**Output**:
- TranscriptFileUri: JSON with full transcript and speaker segments
- Speaker-labeled segments with timestamps

**Alternative**: Use Step Functions wait state + EventBridge instead of polling

### 4. Start Rekognition (`start_rekognition` Lambda)
**Purpose**: Detect and track faces across video frames

**Implementation**:
- Calls AWS Rekognition video face detection on MP4 directly
- Polls for completion (blocks Lambda execution)

**Output**:
- List of face detections with:
  - Timestamp (milliseconds)
  - Bounding box coordinates
  - Face attributes (age range, emotions, etc.)
  - Confidence score

**Note**: Rekognition face detection works on video files directly; frame extraction is NOT needed for this step.

### 5. Invoke Lip Reading (`invoke_lipreading` Lambda)
**Purpose**: Use LipCoordNet for visual speech recognition

**Implementation**:
- Invokes AWS SageMaker endpoint with video S3 location
- SageMaker endpoint handles:
  - Video download from S3
  - Face detection and mouth ROI extraction (128×64)
  - Frame preprocessing at 25 FPS
  - LipCoordNet inference
- Returns transcription text + confidence score

**Why LipCoordNet?**
- Lightweight visual speech recognition model
- Pre-trained on GRID corpus for command word recognition
- Optimized for production deployment
- Works well with frontal face videos
- Available on HuggingFace (SilentSpeak/LipCoordNet)

**LipCoordNet vs Alternatives**:
| Model | Pros | Cons |
|-------|------|------|
| **LipCoordNet** | Fast, lightweight, HuggingFace hosted | Limited to GRID vocabulary |
| AV-HuBERT | SOTA accuracy, audio+visual fusion | Complex setup, larger model |
| LipNet | Visual-only, simple architecture | Lower accuracy |
| Whisper | Great audio transcription | Audio-only (no lip reading) |

**Deployment Options**:

**Option A: Serverless Inference (Current)**
- Auto-scales from 0 to thousands of requests
- Pay only for inference time (~$0.05 per video)
- 30-60s cold start on first request
- Ideal for sporadic workloads
- No infrastructure management

**Option B: Real-time Endpoint**
- Always-on endpoint, no cold starts
- ml.g5.xlarge (NVIDIA A10G GPU)
- ~$1.41/hour (~$1,014/month if running 24/7)
- Use for high-throughput production workloads
- Sub-second latency

### 6. Fuse Results (`fuse_results` Lambda)
**Purpose**: Combine audio transcript, face tracks, and lip reading into unified overlay

**Fusion Logic**:
1. Download full Transcribe JSON transcript
2. Parse speaker-labeled segments with timestamps
3. Match each segment to nearby face detection (timestamp alignment)
4. Compare audio transcript with lip reading:
   - If audio confidence is high: use audio text
   - If visual confidence is higher: use lip reading or flag for review
5. Generate overlay JSON with:
   - Time-aligned segments
   - Speaker labels
   - Text (fused from audio + visual)
   - Face bounding boxes for spatial overlay
   - Confidence scores

**Output**: `s3://gorggle-dev-processed/results/<jobId>/overlay.json`

### 7. Get Results (API Gateway + Lambda)
**Purpose**: Serve overlay JSON via REST API

**Endpoint**: `GET https://<api-id>.execute-api.us-east-1.amazonaws.com/results/<jobId>`

**Returns**:
```json
{
  "jobId": "my-video",
  "segments": [
    {
      "start_time": 0.5,
      "end_time": 3.2,
      "speaker": "spk_0",
      "text": "Hello, how are you?",
      "face": {"Left": 0.3, "Top": 0.2, "Width": 0.15, "Height": 0.25},
      "face_confidence": 99.5,
      "source": "audio",
      "audio_text": "Hello, how are you?",
      "lipreading_text": "Hello, how are you?"
    }
  ],
  "metadata": {
    "total_segments": 15,
    "speakers_detected": 2,
    "faces_tracked": 47
  }
}
```

## Data Flow Diagram

```
┌─────────────┐
│   Upload    │
│  MP4 to S3  │
└──────┬──────┘
       │
       v
┌──────────────────┐
│   S3 Trigger     │ ───> Start Step Functions
└──────────────────┘
       │
       v
┌──────────────────┐
│ Extract Media    │ ───> FFmpeg: audio.wav + frames/*.jpg to S3
└──────────────────┘
       │
       ├─────────────────┬─────────────────┐
       v                 v                 v
┌─────────────┐  ┌──────────────┐  ┌─────────────────┐
│ Transcribe  │  │ Rekognition  │  │  Lip Reading    │
│ (on MP4)    │  │ (on MP4)     │  │ (on frames)     │
│             │  │              │  │                 │
│ Audio->Text │  │ Face Tracks  │  │ Visual->Text    │
└─────────────┘  └──────────────┘  └─────────────────┘
       │                 │                 │
       └─────────────────┴─────────────────┘
                         │
                         v
              ┌──────────────────┐
              │   Fuse Results   │
              │                  │
              │ Align + Combine  │
              └──────────────────┘
                         │
                         v
              ┌──────────────────┐
              │  Overlay JSON    │
              │    to S3 +       │
              │   DynamoDB       │
              └──────────────────┘
                         │
                         v
              ┌──────────────────┐
              │   API Gateway    │
              │  GET /results    │
              └──────────────────┘
                         │
                         v
              ┌──────────────────┐
              │   Web Viewer     │
              │  (index.html)    │
              └──────────────────┘
```

## Cost Estimate (per 10-minute video)

| Service | Usage | Cost |
|---------|-------|------|
| S3 Storage | 500MB upload + 200MB frames | ~$0.01/month |
| Lambda (extract) | 15 min @ 1GB | ~$0.0025 |
| Lambda (others) | ~5 min total | ~$0.001 |
| Transcribe | 10 min audio | ~$0.24 |
| Rekognition | 10 min video face detection | ~$0.10 |
| **SageMaker Serverless** | 5s inference @ 4GB | ~$0.05 |
| API Gateway | 10 requests | <$0.001 |
| DynamoDB | 2 writes, 10 reads | <$0.001 |
| **Total per video** | | **~$0.40** |

**Monthly at scale** (1000 videos/month):
- Processing: ~$400
- No idle infrastructure costs (serverless)
- **Total**: ~$400/month

**Cost Comparison**:
- **Serverless (current)**: $400/month for 1000 videos
- **EC2 24/7 (old)**: $820/month + processing costs
- **Savings**: ~51% reduction

**Optimization Tips**:
- Use S3 lifecycle policies to delete old frames after 30 days
- Batch videos to reduce cold starts
- Use Step Functions Express for cheaper workflow execution
- Enable S3 Intelligent-Tiering for automatic cost optimization

## Limitations & Next Steps

### Current Limitations
1. **FFmpeg not packaged**: Need Lambda Layer or Container Image for extract_media
2. **Polling in Lambda**: Should use Step Functions callbacks for long-running jobs
3. **No error handling**: Transcribe/Rekognition failures don't retry automatically
4. **Simple fusion**: Doesn't handle multi-speaker overlap or complex alignment
5. **Cold starts**: First SageMaker request takes 30-60s (serverless endpoint)
6. **GRID vocabulary**: LipCoordNet trained on command words, may not work well for conversational speech

### Recommended Improvements
1. **Add FFmpeg Layer**: Package FFmpeg for extract_media Lambda
2. **Async processing**: Use Step Functions wait states instead of Lambda polling
3. **Error handling**: Add retry logic and error notifications (SNS/SES)
4. **Better fusion**: Implement confidence-based weighting and temporal alignment
5. **Reduce cold starts**: Keep endpoint warm with scheduled pings
6. **Upgrade model**: Consider AVSRCocktail or AV-HuBERT for conversational speech

### SageMaker Deployment Details

**Model Artifact Structure**:
```
model-lipcoordnet.tar.gz
├── code/
│   ├── inference.py          # Custom inference handler
│   └── requirements.txt      # Model dependencies
└── (model weights loaded from HuggingFace Hub)
```

**Inference Handler** (`sagemaker/inference_lipcoordnet.py`):
- Downloads video from S3
- Detects faces using dlib 68-point landmarks
- Extracts mouth ROI (landmarks 48-67)
- Resizes to 128×64 pixels
- Runs LipCoordNet inference
- Returns transcription + confidence

**Environment Variables**:
- `HF_MODEL_ID`: SilentSpeak/LipCoordNet
- `HF_TASK`: custom

**Instance Types**:
- Serverless: 4-6GB memory (recommended)
- Real-time: ml.g5.xlarge (NVIDIA A10G, 24GB VRAM)

---

## Tech Stack Summary

### Cloud Infrastructure
- **AWS Lambda**: Serverless compute (Python 3.11)
- **AWS SageMaker**: ML model hosting (serverless + real-time)
- **AWS S3**: Object storage (videos, frames, results)
- **AWS DynamoDB**: NoSQL database (job metadata)
- **AWS Step Functions**: Workflow orchestration
- **AWS API Gateway**: REST API
- **AWS Transcribe**: Speech-to-text with diarization
- **AWS Rekognition**: Face detection and tracking

### ML/AI Models
- **LipCoordNet**: Visual speech recognition (HuggingFace)
- **PyTorch**: Deep learning framework
- **Transformers**: HuggingFace library
- **dlib**: Facial landmark detection (68 points)
- **OpenCV**: Video processing and frame extraction

### Development Tools
- **Terraform**: Infrastructure as Code
- **Python 3.11**: Primary language
- **boto3**: AWS SDK for Python
- **FFmpeg**: Video/audio processing

### Frontend
- **HTML5/CSS3**: Modern web standards
- **Vanilla JavaScript**: No framework dependencies
- **Fetch API**: HTTP requests

---

## Migration Notes

**Previous Architecture** (v1.0):
- Used EC2 g6.xlarge with AV-HuBERT
- Required manual infrastructure management
- Cost: ~$820/month for 1000 videos

**Current Architecture** (v2.0):
- Uses SageMaker Serverless with LipCoordNet
- Fully managed, auto-scaling
- Cost: ~$400/month for 1000 videos
- **51% cost reduction**

**Key Changes**:
- ✅ Eliminated EC2 GPU instance
- ✅ Switched to serverless model hosting
- ✅ Simplified deployment (no SSH, systemd, etc.)
- ✅ Faster iteration (2-3 min deploy vs 15+ min)
- ⚠️ Trade-off: 30-60s cold starts (acceptable for async processing)

---

## Performance Characteristics

### Latency Breakdown (5-minute video)
1. **Upload to S3**: ~10-30s (depends on bandwidth)
2. **Lambda (extract_media)**: ~60s (FFmpeg extraction)
3. **Transcribe**: ~150s (audio transcription)
4. **Rekognition**: ~90s (face detection)
5. **SageMaker (lip reading)**: ~5-60s (5s inference + up to 55s cold start)
6. **Lambda (fuse_results)**: ~5s (data merging)
7. **Total**: ~2-6 minutes end-to-end

### Throughput
- **Concurrent videos**: Unlimited (serverless auto-scales)
- **Single endpoint limit**: ~10 requests/second (SageMaker serverless)
- **Recommended**: Use multiple endpoints for >1000 videos/hour

### Accuracy
- **Audio transcription**: 90-95% (AWS Transcribe)
- **Face detection**: 98-99% (AWS Rekognition)
- **Lip reading**: ~40% WER on GRID commands (LipCoordNet)
- **Speaker diarization**: 85-90% accuracy (AWS Transcribe)

**Note**: Lip reading accuracy varies significantly based on:
- Video quality (resolution, lighting, focus)
- Face angle (frontal works best)
- Speaker clarity (mouth visibility)
- Vocabulary match (GRID commands vs conversational speech)
