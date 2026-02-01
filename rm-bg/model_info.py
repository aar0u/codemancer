#!/usr/bin/env python3
"""
This script demonstrates how to inspect the RMBG-1.4 model's input/output format
and available methods using the pipeline API.
"""

import torch
from transformers import pipeline
from PIL import Image
import numpy as np

def inspect_model():
    """Inspect the RMBG-1.4 model structure and methods."""
    print("Loading RMBG-1.4 model...")
    pipe = pipeline("image-segmentation", model="briaai/RMBG-1.4", trust_remote_code=True)
    
    # Print pipeline information
    print("\n=== Pipeline Information ===")
    print(f"Pipeline type: {type(pipe)}")
    print(f"Pipeline task: {pipe.task}")
    
    # Print available methods
    print("\n=== Available Methods ===")
    methods = [method for method in dir(pipe) if not method.startswith('_')]
    for method in methods:
        print(f"- {method}")
    
    # Create a dummy image for testing
    dummy_image = Image.new('RGB', (512, 512), color='red')
    
    # Run inference
    result = pipe(dummy_image)
    
    # Print output information
    print("\n=== Output Information ===")
    print(f"Output type: {type(result)}")
    
    if isinstance(result, list):
        print(f"Result is a list with {len(result)} items")
        if len(result) > 0:
            print(f"First item type: {type(result[0])}")
            if isinstance(result[0], dict):
                print(f"First item keys: {list(result[0].keys())}")
                if "mask" in result[0]:
                    mask = result[0]["mask"]
                    print(f"Mask type: {type(mask)}")
                    print(f"Mask size: {mask.size}")
                    print(f"Mask mode: {mask.mode}")
                    
                    # Convert to numpy to check values
                    mask_array = np.array(mask)
                    print(f"Mask shape: {mask_array.shape}")
                    print(f"Mask dtype: {mask_array.dtype}")
                    print(f"Mask min/max: {mask_array.min()}/{mask_array.max()}")
    elif isinstance(result, dict):
        print(f"Result keys: {list(result.keys())}")
        if "mask" in result:
            mask = result["mask"]
            print(f"Mask type: {type(mask)}")
            print(f"Mask size: {mask.size}")
            print(f"Mask mode: {mask.mode}")
            
            # Convert to numpy to check values
            mask_array = np.array(mask)
            print(f"Mask shape: {mask_array.shape}")
            print(f"Mask dtype: {mask_array.dtype}")
            print(f"Mask min/max: {mask_array.min()}/{mask_array.max()}")

if __name__ == "__main__":
    inspect_model()