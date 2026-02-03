# Remove Background Script

Uses RMBG-1.4 model from Hugging Face to remove backgrounds from images.

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Command Line Interface

```bash
python rmbg.py path/to/image.jpg
```

Options:
- `-f, --format`: Format (png or jpg, default: png)

Examples:
```bash
python rmbg.py input.jpg -f jpg
```

### Web Interface

Start the web server:
```bash
python web_app.py
```

Then open your browser and navigate to:
```
http://localhost:5001
```

Features:
- 🎨 Modern, beautiful UI with drag-and-drop support
- 🖼️ Before/after image comparison
- 📥 Direct download of processed images
- 🎯 Support for PNG (transparent) and JPG (white background) formats
- 📱 Responsive design for all devices

## Build Executable

```bash
python -m PyInstaller --contents-directory=. --name rm-bg --collect-all torch --collect-all torchvision --collect-all transformers --collect-all PIL rmbg.py
```
