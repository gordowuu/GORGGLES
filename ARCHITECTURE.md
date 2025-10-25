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
**Purpose**: Use AV-HuBERT for visual speech recognition

**Implementation**:
- HTTP POST to AV-HuBERT server on EC2
- Passes S3 frames location
- Server downloads frames, runs inference, returns text + confidence

**Why AV-HuBERT?**
- State-of-the-art audio-visual speech recognition (AVSR)
- Pre-trained on LRS3 dataset (high accuracy for English)
- Handles noisy audio by combining visual (lip movements) + audio features
- Better than audio-only in:
  - Noisy environments (background noise, multiple speakers)
  - Low-quality audio
  - Accents and mumbling

**AV-HuBERT vs Alternatives**:
| Model | Pros | Cons |
|-------|------|------|
| **AV-HuBERT** | SOTA accuracy, audio+visual fusion | Requires GPU, ~2GB VRAM |
| LipNet | Fast, visual-only | Lower accuracy, limited vocab |
| Whisper | Great audio transcription | Audio-only (no lip reading) |
| Wav2Vec 2.0 | Fast audio-only ASR | No visual component |

**Deployment**:
- EC2 g4dn.xlarge (1x NVIDIA T4 GPU)
- ~$0.526/hour on-demand (~$190/month if running 24/7)
- Use Spot instances for 70% cost savings
- Or implement auto-start/stop based on SQS queue

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
| EC2 (g4dn.xlarge) | 10 min processing | ~$0.09 |
| API Gateway | 10 requests | <$0.001 |
| DynamoDB | 2 writes, 10 reads | <$0.001 |
| **Total per video** | | **~$0.44** |

**Monthly at scale** (1000 videos/month):
- Processing: ~$440
- EC2 (if running 24/7): ~$380
- **Total**: ~$820/month

**Optimization**:
- Use Spot instances for EC2: saves ~$260/month
- Auto-stop EC2 when idle: saves up to $380/month
- Use S3 lifecycle policies to archive old frames

## Limitations & Next Steps

### Current Limitations
1. **FFmpeg not packaged**: Need Lambda Layer or Container Image
2. **Polling in Lambda**: Should use Step Functions callbacks for long-running jobs
3. **No error handling**: Transcribe/Rekognition failures don't retry
4. **Simple fusion**: Doesn't handle multi-speaker overlap or complex alignment
5. **No authentication**: API is public (add API keys or Cognito)

### Production Enhancements
1. **MediaConvert Alternative**: If FFmpeg layer is too complex, use MediaConvert
2. **EventBridge Integration**: Replace polling with SNS → EventBridge → Step Functions
3. **Lambda Layers**: Package FFmpeg, requests, opencv for Lambdas
4. **Error Handling**: Add retry logic and error states in Step Functions
5. **Monitoring**: CloudWatch dashboards, alarms for failures
6. **Web UI Enhancement**: Real-time progress updates via WebSockets/polling
7. **Speaker Identification**: Train model to identify specific speakers by face + voice
8. **Focus Mode**: Allow user to select a specific speaker to track
