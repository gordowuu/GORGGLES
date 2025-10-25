// Gorggle Frontend Application
// Configuration - Update these after deployment
const CONFIG = {
    // AWS S3 Upload Bucket
    uploadBucket: 'gorggle-dev-uploads',
    region: 'us-east-1',
    
    // API Gateway endpoint for results
    apiUrl: 'https://y9m2193c2i.execute-api.us-east-1.amazonaws.com',
    
    // Maximum file size (500MB)
    maxFileSize: 500 * 1024 * 1024
};

// DOM Elements
const uploadArea = document.getElementById('uploadArea');
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const fileSize = document.getElementById('fileSize');
const uploadBtn = document.getElementById('uploadBtn');
const clearBtn = document.getElementById('clearBtn');
const progress = document.getElementById('progress');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const status = document.getElementById('status');

let selectedFile = null;
let currentJobId = null;

// Initialize AWS SDK (loaded from CDN in production)
// For local development, you'll need AWS credentials configured
let s3Client = null;

// Format bytes to human readable
function formatBytes(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

// Generate unique job ID
function generateJobId() {
    return 'job-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
}

// Show status message
function showStatus(message, type = 'info') {
    status.textContent = message;
    status.className = 'status show ' + type;
}

// Hide status message
function hideStatus() {
    status.className = 'status';
}

// Update progress
function updateProgress(percent, text) {
    progressFill.style.width = percent + '%';
    progressText.textContent = text;
}

// Handle file selection
function handleFileSelect(file) {
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('video/')) {
        showStatus('Please select a valid video file', 'error');
        return;
    }

    // Validate file size
    if (file.size > CONFIG.maxFileSize) {
        showStatus(`File too large. Maximum size is ${formatBytes(CONFIG.maxFileSize)}`, 'error');
        return;
    }

    selectedFile = file;
    
    // Update UI
    fileName.textContent = file.name;
    fileSize.textContent = formatBytes(file.size);
    fileInfo.classList.add('show');
    uploadBtn.disabled = false;
    clearBtn.style.display = 'block';
    hideStatus();
}

// Clear file selection
function clearFile() {
    selectedFile = null;
    fileInput.value = '';
    fileInfo.classList.remove('show');
    uploadBtn.disabled = true;
    clearBtn.style.display = 'none';
    progress.classList.remove('show');
    hideStatus();
}

// Upload file to S3
async function uploadToS3(file, jobId) {
    const key = `uploads/${jobId}.mp4`;
    
    // Using fetch with pre-signed URL (more secure)
    // In production, get pre-signed URL from your API
    // For now, we'll use direct S3 upload (requires CORS configuration)
    
    try {
        // Generate pre-signed URL request
        const uploadUrl = `https://${CONFIG.uploadBucket}.s3.${CONFIG.region}.amazonaws.com/${key}`;
        
        // Create form data
        const formData = new FormData();
        formData.append('file', file);
        
        // Upload with progress tracking
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            
            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percent = Math.round((e.loaded / e.total) * 100);
                    updateProgress(percent, `Uploading... ${percent}%`);
                }
            });
            
            xhr.addEventListener('load', () => {
                if (xhr.status === 200 || xhr.status === 204) {
                    resolve();
                } else {
                    reject(new Error('Upload failed'));
                }
            });
            
            xhr.addEventListener('error', () => {
                reject(new Error('Upload failed'));
            });
            
            xhr.open('PUT', uploadUrl);
            xhr.setRequestHeader('Content-Type', file.type);
            xhr.send(file);
        });
    } catch (error) {
        throw new Error('Failed to upload: ' + error.message);
    }
}

// Alternative: Use AWS SDK for upload
async function uploadWithSDK(file, jobId) {
    if (!window.AWS) {
        throw new Error('AWS SDK not loaded. Please include the SDK script.');
    }
    
    const key = `uploads/${jobId}.mp4`;
    
    // Configure AWS (in production, use Cognito Identity Pool)
    // AWS.config.update({
    //     region: CONFIG.region,
    //     credentials: new AWS.CognitoIdentityCredentials({
    //         IdentityPoolId: 'YOUR_IDENTITY_POOL_ID'
    //     })
    // });
    
    const s3 = new AWS.S3({
        apiVersion: '2006-03-01',
        region: CONFIG.region
    });
    
    const params = {
        Bucket: CONFIG.uploadBucket,
        Key: key,
        Body: file,
        ContentType: file.type
    };
    
    return new Promise((resolve, reject) => {
        s3.upload(params)
            .on('httpUploadProgress', (evt) => {
                const percent = Math.round((evt.loaded / evt.total) * 100);
                updateProgress(percent, `Uploading... ${percent}%`);
            })
            .send((err, data) => {
                if (err) {
                    reject(err);
                } else {
                    resolve(data);
                }
            });
    });
}

// Check job status
async function checkJobStatus(jobId) {
    try {
        const response = await fetch(`${CONFIG.apiUrl}/results/${jobId}`);
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error checking status:', error);
        return null;
    }
}

// Poll for results
function pollResults(jobId, maxAttempts = 60) {
    let attempts = 0;
    
    const poll = setInterval(async () => {
        attempts++;
        
        const result = await checkJobStatus(jobId);
        
        if (result && result.status === 'COMPLETED') {
            clearInterval(poll);
            updateProgress(100, 'Processing complete!');
            showStatus(
                `✅ Transcription complete! Job ID: ${jobId}`,
                'success'
            );
            
            // Add view results button
            const link = document.createElement('a');
            link.href = `${CONFIG.apiUrl}/results/${jobId}`;
            link.className = 'results-link';
            link.target = '_blank';
            link.textContent = 'View Results →';
            status.appendChild(document.createElement('br'));
            status.appendChild(link);
            
        } else if (result && result.status === 'FAILED') {
            clearInterval(poll);
            showStatus(`❌ Processing failed: ${result.error || 'Unknown error'}`, 'error');
            
        } else if (attempts >= maxAttempts) {
            clearInterval(poll);
            showStatus(
                `⏱️ Processing is taking longer than expected. Job ID: ${jobId}. Check back later.`,
                'info'
            );
        } else {
            updateProgress(
                Math.min(90, 20 + (attempts * 2)),
                `Processing video... (${attempts}/${maxAttempts})`
            );
        }
    }, 5000); // Check every 5 seconds
}

// Main upload handler
async function handleUpload() {
    if (!selectedFile) return;
    
    currentJobId = generateJobId();
    
    // Disable buttons during upload
    uploadBtn.disabled = true;
    clearBtn.disabled = true;
    
    // Show progress
    progress.classList.add('show');
    updateProgress(0, 'Preparing upload...');
    
    try {
        // Note: This is a simplified version
        // In production, you'd either:
        // 1. Get a pre-signed URL from your API
        // 2. Use AWS SDK with Cognito Identity Pool
        // 3. Use a backend proxy
        
        showStatus(
            `📤 To complete the upload, run this command:\n\n` +
            `aws s3 cp "${selectedFile.name}" s3://${CONFIG.uploadBucket}/uploads/${currentJobId}.mp4`,
            'info'
        );
        
        // For demo purposes, show manual upload instructions
        // In production, implement actual S3 upload
        
        // Uncomment this when AWS SDK is configured:
        // await uploadWithSDK(selectedFile, currentJobId);
        // updateProgress(100, 'Upload complete!');
        // showStatus('✅ Upload complete! Processing video...', 'success');
        // pollResults(currentJobId);
        
    } catch (error) {
        console.error('Upload error:', error);
        showStatus('❌ Upload failed: ' + error.message, 'error');
        clearBtn.disabled = false;
    }
}

// Event Listeners
uploadArea.addEventListener('click', () => {
    fileInput.click();
});

fileInput.addEventListener('change', (e) => {
    handleFileSelect(e.target.files[0]);
});

// Drag and drop
uploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    uploadArea.classList.add('dragover');
});

uploadArea.addEventListener('dragleave', () => {
    uploadArea.classList.remove('dragover');
});

uploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    uploadArea.classList.remove('dragover');
    handleFileSelect(e.dataTransfer.files[0]);
});

uploadBtn.addEventListener('click', handleUpload);
clearBtn.addEventListener('click', clearFile);

// Initialize
console.log('Gorggle initialized with config:', CONFIG);
