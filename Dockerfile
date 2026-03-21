# Use the official slim Python 3.14 image
FROM python:3.14-slim

# Set working directory
WORKDIR /app

# Install dependencies first (layer cache-friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# /data is a persistent disk mount on Render — ensure it exists for local runs
RUN mkdir -p /data

# Run the bot
CMD ["python", "main.py"]
