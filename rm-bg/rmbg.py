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
    print("Please install required packages with: pip install -r requirements.txt")
    sys.exit(1)


_pipe = None


def get_pipeline():
    """Get or initialize the RMBG-1.4 pipeline (singleton pattern)."""
    global _pipe
    if _pipe is None:
        print("Loading RMBG-1.4 model...")
        _pipe = pipeline("image-segmentation", model="briaai/RMBG-1.4", trust_remote_code=True)
        print("Model loaded successfully")
    return _pipe


def remove_background(image, compress_png=True):
    """Remove background from an image using RMBG-1.4 model."""
    pipe = get_pipeline()
    
    print("Processing image...")
    result = pipe(image.convert("RGB"))
    
    if not isinstance(result, Image.Image):
        raise ValueError(f"Unexpected pipeline result format: {type(result)}")
    
    compressed_result = None
    if compress_png and shutil.which("pngquant"):
        from io import BytesIO
        buffer = BytesIO()
        result.save(buffer, format='PNG')
        buffer.seek(0)
        
        proc = subprocess.Popen(
            ["pngquant", "--quality=60-80", "--speed=1", "--strip", "--force", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = proc.communicate(buffer.getvalue())
        
        if proc.returncode == 0:
            compressed_result = Image.open(BytesIO(stdout))
            print("PNG compression completed")
        else:
            print(f"PNG compression failed: {stderr.decode()}")
    elif compress_png:
        print("PNG compression skipped (pngquant not available)")
        print("To install pngquant:")
        print("  macOS:   brew install pngquant")
        print("  Ubuntu:   sudo apt-get install pngquant")
        print("  Fedora:   sudo dnf install pngquant")
        print("  Windows:  Download from https://pngquant.org/")
    
    return result, compressed_result


def process_file(input_path, output_format="png"):
    """Remove background from an image file and save to file."""
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    image = Image.open(input_path)
    result, compressed_result = remove_background(image, compress_png=(output_format.lower() == 'png'))
    
    input_file = Path(input_path)
    timestamp = datetime.now().strftime("%H%M%S")
    output_format = output_format.lower()
    output_path = str(input_file.parent / f"{input_file.stem}_{timestamp}_rmbg.{output_format}")
    
    if output_format in ('jpg', 'jpeg'):
        white_bg = Image.new('RGB', result.size, (255, 255, 255))
        white_bg.paste(result, mask=result.split()[-1] if result.mode == 'RGBA' else None)
        white_bg.save(output_path, 'JPEG', quality=85)
        print(f"Saved as JPEG: {output_path}")
    else:
        result.save(output_path, 'PNG')
        print(f"Saved as PNG with transparency: {output_path}")
        
        if compressed_result:
            output_compressed = output_path.replace('_rmbg.png', '_rmbg_cmp.png')
            compressed_result.save(output_compressed, 'PNG')
            print(f"Compressed PNG saved: {output_compressed}")


def main():
    parser = argparse.ArgumentParser(description="Remove background from images using RMBG-1.4 model")
    parser.add_argument("input", help="Path to input image file")
    parser.add_argument("-f", "--format", choices=["png", "jpg"], default="png", 
                        help="Output format: png (default, supports transparency) or jpg (smaller file size)")
    
    args = parser.parse_args()
    
    try:
        process_file(args.input, args.format)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
