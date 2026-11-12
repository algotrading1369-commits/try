FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV HOST=0.0.0.0 \
    PORT=8300 \
    PYTHONUNBUFFERED=1

EXPOSE 8300

VOLUME ["/data"]

CMD ["python", "run.py"]
