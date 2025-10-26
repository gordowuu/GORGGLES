Custom SageMaker inference image for AV-HuBERT

Overview
- The stock PyTorch inference container doesn't include the av_hubert custom Fairseq task.
- AV-HuBERT checkpoints require that the av_hubert package is importable to register the task (av_hubert_pretraining).
- This minimal image builds on the official PyTorch inference image and installs fairseq + av_hubert.

Build and push (PowerShell)
1. Set variables:

   $AccountId = (aws sts get-caller-identity --query Account --output text)
   $Region = 'us-east-1'
   $Repo = 'avhubert-sagemaker-inference'

2. Create ECR repo (once):

   aws ecr describe-repositories --repository-names $Repo 2>$null | Out-Null; if (!$?) { aws ecr create-repository --repository-name $Repo | Out-Null }

3. Get login and build:

   aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin "$AccountId.dkr.ecr.$Region.amazonaws.com"
   docker build -t $Repo -f sagemaker/container/Dockerfile .
   docker tag $Repo:latest "$AccountId.dkr.ecr.$Region.amazonaws.com/$Repo:latest"
   docker push "$AccountId.dkr.ecr.$Region.amazonaws.com/$Repo:latest"

Use in deployment
- Update scripts/deploy_sagemaker_minimal.py to pass image_uri to PyTorchModel:

  model = PyTorchModel(
      name=model_name,
      model_data=args.model_data,
      role=args.role_arn,
      framework_version=args.framework_version, # optional when using custom image
      py_version=args.py_version,               # optional when using custom image
      sagemaker_session=sagemaker_session,
      image_uri=f"{AccountId}.dkr.ecr.{Region}.amazonaws.com/{Repo}:latest",
  )

Notes
- You still package code/inference.py and avhubert.pt inside model.tar.gz. The custom image just ensures av_hubert is importable and heavy deps are preinstalled for fast/consistent startup.
- Pin av_hubert to a known commit if reproducibility is important.
