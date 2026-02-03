#!/usr/bin/env python3
"""Download the RMBG-1.4 model and its files from Hugging Face."""

import sys

try:
    from transformers import pipeline
    print("Downloading RMBG-1.4 model and files...")
    # This will download the model and all associated files, including MyConfig.py
    pipe = pipeline("image-segmentation", model="briaai/RMBG-1.4", trust_remote_code=True)
    print("Model and files downloaded successfully!")
except Exception as e:
    print(f"Error downloading model: {e}")
    sys.exit(1)
