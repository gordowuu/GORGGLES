# Gorggle Web Frontend

Simple, beautiful web interface for uploading videos and viewing AI-powered transcription results.

## Features

- 📤 **Drag & Drop Upload**: Easy video file selection
- 🎥 **Results Viewer**: Watch videos with AI-generated captions overlay
- 🎨 **Modern UI**: Clean, gradient design with responsive layout
- 📊 **Status Tracking**: Real-time upload and processing status

## Quick Start

### Option 1: Open Locally (Simplest)

1. Open `index.html` in your web browser:
   ```powershell
   start web/index.html
   ```

2. Switch between Upload and Viewer tabs

### Option 2: Serve with Python

```powershell
cd web
python -m http.server 8080
```

Then visit: http://localhost:8080

### Option 3: Serve with Node.js

```powershell
cd web
npx http-server -p 8080
```

## Usage

### Uploading Videos

1. Click "📤 Upload Video" tab
2. Drag & drop a video file or click to browse
3. Copy the AWS CLI command shown
4. Run the command in your terminal to upload to S3
5. The upload will automatically trigger the processing pipeline

**Example:**
```powershell
aws s3 cp "my-video.mp4" s3://gorggle-dev-uploads/uploads/job-1234567890.mp4
```

### Viewing Results

1. Click "🎥 View Results" tab
2. Enter your Job ID (from the upload step)
3. Enter the video URL (S3 URL of processed video)
4. Click "Load Results"
5. Watch the video with AI-generated captions

**Note:** API URL is pre-filled with your deployed endpoint: `https://y9m2193c2i.execute-api.us-east-1.amazonaws.com`

## Configuration

Update the API URL in `index.html` if you redeploy:

```javascript
value="https://y9m2193c2i.execute-api.us-east-1.amazonaws.com"
```

## Future Enhancements

- [ ] Direct S3 upload via pre-signed URLs
- [ ] AWS Cognito authentication for browser-based uploads
- [ ] Real-time progress tracking via WebSocket
- [ ] Download transcription as SRT/VTT files
- [ ] Speaker-specific caption filtering
- [ ] Timeline scrubbing with caption preview

## Architecture

```
┌─────────────────┐
│   Browser UI    │
│  (index.html)   │
└────────┬────────┘
         │
         │ 1. Generate Job ID
         │ 2. Show AWS CLI command
         │
         ▼
┌─────────────────┐
│  User runs CLI  │
│  aws s3 cp ...  │
└────────┬────────┘
         │
         │ 3. Upload triggers Lambda
         │
         ▼
┌─────────────────┐
│  S3 + Lambda    │
│  (Processing)   │
└────────┬────────┘
         │
         │ 4. Results ready
         │
         ▼
┌─────────────────┐
│  API Gateway    │
│  GET /results   │
└────────┬────────┘
         │
         │ 5. Fetch & display
         │
         ▼
┌─────────────────┐
│   Browser UI    │
│  (Viewer tab)   │
└─────────────────┘
```

## Troubleshooting

**Q: Upload button doesn't work?**  
A: This is expected. Use the AWS CLI command shown. Browser-based S3 uploads require additional CORS configuration and authentication.

**Q: Video won't load in viewer?**  
A: Ensure the S3 bucket has CORS configured to allow video streaming. Add to your processed bucket:

```json
[
  {
    "AllowedHeaders": ["*"],
    "AllowedMethods": ["GET", "HEAD"],
    "AllowedOrigins": ["*"],
    "ExposeHeaders": ["ETag"]
  }
]
```

**Q: Results not showing?**  
A: Check:
1. Job ID matches the one from upload
2. Processing is complete (check Step Functions console)
3. API URL is correct
4. Video URL is publicly accessible or CORS-enabled

## Development

To enable direct browser uploads (optional):

1. **Create Cognito Identity Pool** for unauthenticated access:
   ```powershell
   aws cognito-identity create-identity-pool `
     --identity-pool-name gorggle-uploads `
     --allow-unauthenticated-identities
   ```

2. **Update app.js** with Identity Pool ID

3. **Configure S3 CORS** on uploads bucket:
   ```json
   [
     {
       "AllowedHeaders": ["*"],
       "AllowedMethods": ["PUT", "POST"],
       "AllowedOrigins": ["*"],
       "ExposeHeaders": []
     }
   ]
   ```

4. **Add IAM policy** to allow Cognito users to upload to `uploads/` prefix

---

Built with ❤️ for Gorggle AI Video Transcription
