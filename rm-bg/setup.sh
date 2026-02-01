#!/bin/bash
python -m venv .venv

# Detect OS and use appropriate Python path
if [[ "$OSTYPE" == "linux-gnu"* || "$OSTYPE" == "darwin"* ]]; then
    # Linux or macOS
    VENV_PYTHON=".venv/bin/python"
    VENV_PIP=".venv/bin/pip"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    # Windows
    VENV_PYTHON=".venv/Scripts/python.exe"
    VENV_PIP=".venv/Scripts/pip.exe"
else
    echo "Unsupported operating system: $OSTYPE"
    exit 1
fi

# Check if virtual environment Python exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Failed to create virtual environment"
    exit 1
fi

# Install dependencies using virtual environment pip
"$VENV_PIP" install -r requirements.txt

# Create py.sh script for easy Python execution
cat > py.sh << 'EOF'
#!/bin/bash
.venv/bin/python "$@"
EOF

# Make py.sh executable
chmod +x py.sh

# Create py.bat for Windows users
cat > py.bat << 'EOF'
@echo off
.venv\Scripts\python.exe %*
EOF

echo "Virtual environment setup complete."
echo "Use './py.sh <script.py> [args]' to run Python scripts with virtual environment"
echo "Windows users can use 'py.bat <script.py> [args]'"
