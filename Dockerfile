FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    DB_PATH=/data/plans.db

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

EXPOSE 8000

# 一条命令完成依赖内启动：应用启动时自动初始化 SQLite（建表，幂等）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
