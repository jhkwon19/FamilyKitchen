# Python slim 이미지를 사용해 FastAPI + 정적 파일을 서빙합니다.
FROM python:3.11-slim

WORKDIR /app

# 필요한 경우 빌드 툴을 추가하세요(여기서는 최소화).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# DB 접속 정보는 실행 시 덮어쓸 수 있습니다.
ENV DB_HOST=172.18.0.4 \
    DB_PORT=3306 \
    DB_USER=root \
    DB_PASSWORD=Wnsgh1219@ \
    DB_NAME=FamilyKitchen

EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
