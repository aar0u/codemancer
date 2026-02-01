# Remove Background Script

Uses RMBG-1.4 model from Hugging Face to remove backgrounds from images.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

```bash
python rm-bg.py path/to/image.jpg
```

Options:
- `-o, --output`: Output path
- `-f, --format`: Format (png or jpg, default: png)

Examples:
```bash
python rm-bg.py input.jpg -f jpg
```

## Build Executable

```bash
python -m PyInstaller --contents-directory=. --name rm-bg --collect-all torch --collect-all torchvision --collect-all transformers --collect-all PIL --collect-all skimage rm-bg.py
```
