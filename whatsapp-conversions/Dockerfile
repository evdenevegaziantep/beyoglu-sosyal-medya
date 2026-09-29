FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
ENV PORT=8080 DB_PATH=/var/data/whatsapp-conversions.sqlite3
EXPOSE 8080
CMD ["gunicorn","-b","0.0.0.0:8080","--workers","2","--threads","4","--timeout","120","app:app"]
