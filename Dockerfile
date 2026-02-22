# ---------- Base Image ----------
FROM python:3.11-slim

# ---------- Environment ----------
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ---------- Workdir ----------
WORKDIR /app

# ---------- Install system deps ----------
RUN apt-get update && apt-get install -y --no-install-recommends     build-essential     && rm -rf /var/lib/apt/lists/*

# ---------- Copy requirements ----------
COPY requirements.txt .

# ---------- Install python deps ----------
RUN pip install --no-cache-dir --upgrade pip     && pip install --no-cache-dir -r requirements.txt

# ---------- Copy project ----------
COPY . .

# ---------- Expose port ----------
EXPOSE 8000

# ---------- Run app ----------
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]