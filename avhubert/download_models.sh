#!/bin/bash
# Download all required model files for AV-HuBERT
# Run as: bash download_models.sh

set -e  # Exit on error

INSTALL_DIR="/opt/avhubert"
mkdir -p $INSTALL_DIR

echo "======================================"
echo "Downloading AV-HuBERT Model Files"
echo "======================================"

# Download face detection model (~10MB)
echo "[1/4] Downloading dlib face detector..."
cd $INSTALL_DIR
wget -c http://dlib.net/files/mmod_human_face_detector.dat.bz2
bunzip2 -f mmod_human_face_detector.dat.bz2
echo "✓ Face detector downloaded: $INSTALL_DIR/mmod_human_face_detector.dat"

# Download facial landmark predictor (~100MB)
echo "[2/4] Downloading dlib facial landmark predictor..."
wget -c http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2
bunzip2 -f shape_predictor_68_face_landmarks.dat.bz2
echo "✓ Landmark predictor downloaded: $INSTALL_DIR/shape_predictor_68_face_landmarks.dat"

# Download mean face for mouth ROI alignment
echo "[3/4] Downloading mean face landmarks..."
wget -c https://raw.githubusercontent.com/facebookresearch/av_hubert/main/avhubert/preparation/mean_face.npy
echo "✓ Mean face downloaded: $INSTALL_DIR/mean_face.npy"

# Download pre-trained AV-HuBERT model checkpoint
echo "[4/4] Downloading AV-HuBERT Base model checkpoint..."
echo ""
echo "Please choose a model to download:"
echo "1. AV-HuBERT Base (Audio-Visual, ~400MB) - RECOMMENDED"
echo "2. AV-HuBERT Large (Audio-Visual, ~1GB) - Better accuracy"
echo "3. V-HuBERT (Visual-only, ~400MB) - For silent/noisy environments"
echo ""
read -p "Enter choice [1-3]: " choice

case $choice in
    1)
        echo "Downloading AV-HuBERT Base..."
        # Visit http://facebookresearch.github.io/av_hubert to get the actual download link
        echo ""
        echo "Please manually download the AV-HuBERT Base checkpoint from:"
        echo "http://facebookresearch.github.io/av_hubert"
        echo ""
        echo "Look for: 'large_vox_iter5.pt' or similar"
        echo "Save it to: $INSTALL_DIR/model.pt"
        ;;
    2)
        echo "Downloading AV-HuBERT Large..."
        echo ""
        echo "Please manually download the AV-HuBERT Large checkpoint from:"
        echo "http://facebookresearch.github.io/av_hubert"
        echo "Save it to: $INSTALL_DIR/model.pt"
        ;;
    3)
        echo "Downloading V-HuBERT..."
        echo ""
        echo "Please manually download the V-HuBERT checkpoint from:"
        echo "http://facebookresearch.github.io/av_hubert"
        echo "Save it to: $INSTALL_DIR/model.pt"
        ;;
    *)
        echo "Invalid choice. Please run the script again."
        exit 1
        ;;
esac

echo ""
echo "======================================"
echo "Model Files Status"
echo "======================================"
ls -lh $INSTALL_DIR/*.dat $INSTALL_DIR/*.npy 2>/dev/null || echo "Some files not found"
echo ""
echo "IMPORTANT: Make sure to download the model checkpoint manually"
echo "from: http://facebookresearch.github.io/av_hubert"
echo "and save it as: $INSTALL_DIR/model.pt"
echo ""
echo "After downloading, verify with:"
echo "  ls -lh $INSTALL_DIR/model.pt"
echo ""
