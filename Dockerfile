# 1. Use the official Python base
FROM python:3.10-slim

# 2. Install FFmpeg AND Node.js (Crucial for the JS challenge!)
USER root
RUN apt-get update && \
    apt-get install -y ffmpeg nodejs npm git && \
    rm -rf /var/lib/apt/lists/*

# 3. Setup security user
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# 4. Install Python dependencies
COPY --chown=user ./requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# 5. Copy your code
COPY --chown=user . /app

# 6. Start the API on Render's default port
CMD ["uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", "10000"]
