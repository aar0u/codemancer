FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    pngquant \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Pre-download model files during build
RUN python download_model.py

EXPOSE 5001

CMD ["python", "web_app.py"]
