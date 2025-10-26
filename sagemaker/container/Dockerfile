# Custom SageMaker inference image for AV-HuBERT
# Base: AWS PyTorch inference container (CPU)
# See: https://github.com/aws/deep-learning-containers/blob/master/available_images.md

FROM 763104351884.dkr.ecr.us-east-1.amazonaws.com/pytorch-inference:2.1.0-cpu-py310-ubuntu20.04-ec2

# Install system deps
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

# Copy model code (SageMaker expects /opt/ml/model/code/inference.py at runtime from model.tar.gz)
# We still use model.tar.gz for inference entrypoint; this image just pre-installs heavy deps.

# Install Python requirements
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir opencv-python-headless==4.8.1.78 sentencepiece==0.1.99 fairseq==0.12.2 scipy==1.11.3 soundfile==0.12.1

# Clone AV-HuBERT to register custom tasks (kept in site-packages via editable install)
# You may pin to a specific commit for reproducibility
RUN git clone https://github.com/facebookresearch/av_hubert.git /opt/av_hubert \
 && pip install -e /opt/av_hubert

# Ensure av_hubert package is importable
ENV PYTHONPATH="/opt/av_hubert:${PYTHONPATH}"

# TorchServe port envs are set by base image; no CMD change needed.
# The model artifact (model.tar.gz) provides code/inference.py
USER root
