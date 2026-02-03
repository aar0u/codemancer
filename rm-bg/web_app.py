#!/usr/bin/env python3
"""Flask web application for background removal."""

from io import BytesIO
from PIL import Image
from flask import Flask, render_template, request, send_file, jsonify
from rmbg import remove_background

app = Flask(__name__)

# Configuration
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'gif'}
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.lower().rsplit('.', 1)[1] in ALLOWED_EXTENSIONS


@app.route('/')
def index():
    """Serve the main page."""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and background removal."""
    try:
        # Check if file is present
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Allowed: PNG, JPG, JPEG, WEBP, BMP, GIF'}), 400
        
        # Get output format from request
        output_format = request.form.get('format', 'png').lower()
        if output_format not in ['png', 'jpg']:
            output_format = 'png'
        
        # Get PNG compression option
        compress_png = request.form.get('compress_png', 'true').lower() == 'true'
        
        # Load image directly from uploaded file into memory
        input_image = Image.open(file.stream).convert("RGB")
        
        # Process the image using remove_background from rmbg.py
        result, compressed_result = remove_background(input_image, compress_png=compress_png and output_format == 'png')
        
        # Create output in memory
        output_buffer = BytesIO()
        
        if output_format in ('jpg', 'jpeg'):
            result.save(output_buffer, 'JPEG', quality=85)
            mimetype = 'image/jpeg'
        else:
            # Use compressed result if available, otherwise use regular result
            output_image = compressed_result if compressed_result else result
            output_image.save(output_buffer, 'PNG')
            mimetype = 'image/png'
        
        # Reset buffer position to beginning
        output_buffer.seek(0)
        
        print(f"Processing complete, returning {output_format.upper()} image")
        
        # Return the processed image from memory
        return send_file(
            output_buffer,
            mimetype=mimetype,
            as_attachment=True,
            download_name=f'removed_bg.{output_format}'
        )
    
    except Exception as e:
        print(f"Error processing image: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    print("=" * 60)
    print("Background Removal Web Application")
    print("=" * 60)
    print("Starting server at http://localhost:5001")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5001)
