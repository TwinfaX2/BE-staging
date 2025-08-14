FROM python:3.11-slim

# 필요한 종속성 설치 (psycopg2 및 pandas 빌드를 위한 종속성)
RUN apt-get update && apt-get install -y \
    libpq-dev \
    build-essential \
    gcc \
    g++ \
    fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

# matplotlib 한글 폰트 설정
RUN mkdir -p /root/.config/matplotlib
RUN echo "font.family: sans-serif" > /root/.config/matplotlib/matplotlibrc
RUN echo "font.sans-serif: NanumGothic, DejaVu Sans" >> /root/.config/matplotlib/matplotlibrc

WORKDIR /app
COPY requirements.txt .

# pip 업그레이드 및 setuptools 명시적 설치
RUN pip install --upgrade pip
RUN pip install setuptools>=69.0.0
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# BE-staging: 1-cycle 파이프라인 실행
CMD ["sh", "-c", "python main_extract.py --output output/railway_deploy.json && python main_push_db/main.py"]