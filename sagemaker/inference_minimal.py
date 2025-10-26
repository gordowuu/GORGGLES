"""
SageMaker PyTorch inference script for AV-HuBERT (minimal test version).

This script follows the official SageMaker PyTorch inference handler contract:
- model_fn(model_dir): Load and return model from model_dir
- input_fn(request_body, request_content_type): Deserialize request
- predict_fn(input_object, model): Perform inference
- output_fn(prediction, response_content_type): Serialize response

For initial testing, uses a minimal placeholder model that echoes input.
Once this works, can be extended to load actual AV-HuBERT model.

Expected input (JSON):
{
  "s3_bucket": "gorggle-dev-uploads",
  "s3_video_key": "test-video.mp4"
}

Returns (JSON):
{
  "text": "transcribed text",
  "segments": []
}
"""

import json
import logging
import os

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ===================================================================
# Minimal placeholder model for testing
# ===================================================================
class MinimalPlaceholderModel:
    """
    Minimal placeholder that returns a fixed transcript.
    Used to verify SageMaker container can start and respond properly.
    """
    
    def __init__(self):
        logger.info("MinimalPlaceholderModel initialized")
    
    def __call__(self, input_data):
        """
        Return a simple placeholder response.
        
        Args:
            input_data: Dict from input_fn
            
        Returns:
            Dict with text and segments
        """
        logger.info(f"Model called with input: {input_data}")
        
        return {
            "text": "[Minimal placeholder transcript from SageMaker endpoint]",
            "segments": [],
            "note": "Container is operational. This is a minimal test handler."
        }


# ===================================================================
# SageMaker inference handler functions
# ===================================================================

def model_fn(model_dir):
    """
    Load model from model_dir.
    
    SageMaker calls this once when the container starts to load your model.
    Must return a model object that will be passed to predict_fn.
    
    Args:
        model_dir (str): Directory containing model artifacts from model.tar.gz
        
    Returns:
        Model object (any object with __call__ method or that predict_fn knows how to use)
    """
    logger.info(f"model_fn called with model_dir: {model_dir}")
    
    # Log contents of model_dir for debugging
    if os.path.exists(model_dir):
        try:
            contents = os.listdir(model_dir)
            logger.info(f"Contents of model_dir: {contents}")
        except Exception as e:
            logger.warning(f"Could not list model_dir: {e}")
    else:
        logger.warning(f"model_dir does not exist: {model_dir}")
    
    # For initial testing, return minimal placeholder
    # Once this works, replace with actual AV-HuBERT model loading
    model = MinimalPlaceholderModel()
    logger.info("Successfully loaded model")
    
    return model


def input_fn(request_body, request_content_type='application/json'):
    """
    Deserialize request body into Python object for prediction.
    
    SageMaker calls this to parse the raw request body before passing to predict_fn.
    
    Args:
        request_body: Raw bytes from HTTP POST body
        request_content_type: Content-Type header value
        
    Returns:
        Deserialized Python object (typically dict)
    """
    logger.info(f"input_fn called with content_type: {request_content_type}")
    
    if request_content_type == 'application/json':
        try:
            input_data = json.loads(request_body)
            logger.info(f"Successfully parsed JSON input")
            return input_data
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing failed: {e}")
            raise ValueError(f"Invalid JSON in request body: {e}")
    else:
        raise ValueError(
            f"Unsupported content type: {request_content_type}. "
            "Only 'application/json' is supported."
        )


def predict_fn(input_object, model):
    """
    Perform inference using the loaded model.
    
    Args:
        input_object: Deserialized input from input_fn
        model: Loaded model from model_fn
        
    Returns:
        Prediction result (any Python object that output_fn can serialize)
    """
    logger.info("predict_fn called")
    
    try:
        # Call the model
        prediction = model(input_object)
        logger.info("Prediction completed successfully")
        return prediction
    except Exception as e:
        logger.error(f"Prediction failed: {e}", exc_info=True)
        # Return error in prediction structure so output_fn can serialize it
        return {
            "text": "",
            "segments": [],
            "error": str(e),
            "note": "Prediction failed; see error field"
        }


def output_fn(prediction, response_content_type='application/json'):
    """
    Serialize prediction result to response format.
    
    Args:
        prediction: Result from predict_fn
        response_content_type: Desired response content type
        
    Returns:
        Tuple of (serialized_bytes, content_type)
    """
    logger.info(f"output_fn called with content_type: {response_content_type}")
    
    if response_content_type == 'application/json':
        try:
            serialized = json.dumps(prediction)
            logger.info("Successfully serialized response")
            return serialized, response_content_type
        except Exception as e:
            logger.error(f"Serialization failed: {e}", exc_info=True)
            error_response = json.dumps({
                "error": f"Failed to serialize response: {e}"
            })
            return error_response, response_content_type
    else:
        raise ValueError(
            f"Unsupported response content type: {response_content_type}. "
            "Only 'application/json' is supported."
        )
