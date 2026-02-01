#!/usr/bin/env python3
"""Remove background from images using RMBG-1.4 model from Hugging Face."""

import argparse
import os
import sys
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

try:
    import torch
    from PIL import Image
    from transformers import pipeline
except ImportError as e:
    print(f"Missing required package: {e}")
    print("Please install required packages with:")
    print("pip install torch torchvision transformers pillow")
    sys.exit(1)


def remove_background(input_path, output_format="png"):
    """Remove background from an image using RMBG-1.4 model."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    input_file = Path(input_path)
    timestamp = datetime.now().strftime("%H%M%S")
    output_format = output_format.lower()
    output_path = str(input_file.parent / f"{input_file.stem}_{timestamp}_rmbg.{output_format}")
    
    print("Loading RMBG-1.4 model...")
    pipe = pipeline("image-segmentation", model="briaai/RMBG-1.4", trust_remote_code=True)
    
    print(f"Processing image: {input_path}")
    result = pipe(Image.open(input_path).convert("RGB"))
    
    if not isinstance(result, Image.Image):
        raise ValueError(f"Unexpected pipeline result format: {type(result)}")
    
    if output_format in ('jpg', 'jpeg'):
        white_bg = Image.new('RGB', result.size, (255, 255, 255))
        white_bg.paste(result, mask=result.split()[-1] if result.mode == 'RGBA' else None)
        white_bg.save(output_path, 'JPEG', quality=85)
        print(f"Saved as JPEG: {output_path}")
    else:
        result.save(output_path, 'PNG')
        print(f"Saved as PNG with transparency: {output_path}")
        
        output_compressed = output_path.replace('_rmbg.png', '_rmbg_cmp.png')
        if shutil.which("pngquant"):
            subprocess.run(["pngquant", "--quality=60-80", "--speed=1", "--strip", "--force",
                          "--output", output_compressed, output_path], capture_output=True)
            print(f"Compressed PNG saved: {output_compressed}")
        else:
            print("PNG compression skipped (pngquant not available)")
            print("To install pngquant:")
            print("  macOS:   brew install pngquant")
            print("  Ubuntu:   sudo apt-get install pngquant")
            print("  Fedora:   sudo dnf install pngquant")
            print("  Windows:  Download from https://pngquant.org/")


def main():
    parser = argparse.ArgumentParser(description="Remove background from images using RMBG-1.4 model")
    parser.add_argument("input", help="Path to input image file")
    parser.add_argument("-f", "--format", choices=["png", "jpg"], default="png", 
                        help="Output format: png (default, supports transparency) or jpg (smaller file size)")
    
    args = parser.parse_args()
    
    try:
        remove_background(args.input, args.format)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
