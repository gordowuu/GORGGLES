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
echo "[4/4] Downloading AV-HuBERT model checkpoint..."
echo ""
echo "Available Models from http://facebookresearch.github.io/av_hubert"
echo ""
echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║                    RECOMMENDED FOR GORGGLE                            ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "1. Noise-Augmented AV-HuBERT Large (LRS3+Vox, 433h) - BEST"
echo "   • Audio-Visual (uses lip reading + audio)"
echo "   • Noise-robust (trained for real-world noisy environments)"
echo "   • Highest accuracy (~1GB)"
echo ""
echo "2. Noise-Augmented AV-HuBERT Base (LRS3+Vox, 433h) - FAST"
echo "   • Audio-Visual (uses lip reading + audio)"
echo "   • Noise-robust, faster inference (~500MB)"
echo ""
echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║                    VISUAL-ONLY (LIP READING)                          ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "3. AV-HuBERT Large (LRS3+Vox, 433h VSR) - Visual-only"
echo "   • Lip reading only (ignores audio)"
echo "   • Use if audio is completely unavailable (~1GB)"
echo ""
echo "4. AV-HuBERT Base (LRS3+Vox, 433h VSR) - Visual-only, faster"
echo "   • Lip reading only, faster inference (~500MB)"
echo ""
read -p "Enter choice [1-4]: " choice

case $choice in
    1)
        MODEL_NAME="Noise-Augmented AV-HuBERT Large (AVSR, 433h)"
        MODEL_FILE="noise_large_lrs3vox_433h_avsr.pt"
        echo ""
        echo "Selected: $MODEL_NAME"
        echo ""
        echo "This model provides the BEST accuracy for real-world accessibility."
        echo "It combines lip reading with audio and handles noisy environments."
        ;;
    2)
        MODEL_NAME="Noise-Augmented AV-HuBERT Base (AVSR, 433h)"
        MODEL_FILE="noise_base_lrs3vox_433h_avsr.pt"
        echo ""
        echo "Selected: $MODEL_NAME"
        echo ""
        echo "Good balance of speed and accuracy for noisy environments."
        ;;
    3)
        MODEL_NAME="AV-HuBERT Large (VSR, 433h)"
        MODEL_FILE="large_lrs3vox_433h_vsr.pt"
        echo ""
        echo "Selected: $MODEL_NAME"
        echo ""
        echo "Visual-only lip reading (ignores audio)."
        ;;
    4)
        MODEL_NAME="AV-HuBERT Base (VSR, 433h)"
        MODEL_FILE="base_lrs3vox_433h_vsr.pt"
        echo ""
        echo "Selected: $MODEL_NAME"
        echo ""
        echo "Faster visual-only lip reading."
        ;;
    *)
        echo "Invalid choice. Please run the script again."
        exit 1
        ;;
esac

echo ""
echo "════════════════════════════════════════════════════════════════════════"
echo "MANUAL DOWNLOAD REQUIRED"
echo "════════════════════════════════════════════════════════════════════════"
echo ""
echo "1. Visit: http://facebookresearch.github.io/av_hubert"
echo ""
echo "2. Find and download: $MODEL_FILE"
echo "   (Look in 'Finetuned Models for Audio-Visual Speech Recognition' section)"
echo ""
echo "3. Save it as: $INSTALL_DIR/model.pt"
echo ""
echo "Example download command (if direct URL available):"
echo "  wget -O $INSTALL_DIR/model.pt <DOWNLOAD_URL>"
echo ""

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
