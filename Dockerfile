FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /project
RUN pip install --no-cache-dir requests==2.32.3 pytest==8.3.5
COPY . .
CMD ["python", "-m", "lab.controller"]
