FROM python:3.10-slim

RUN apt-get update && \
    apt-get install -y build-essential libssl-dev libffi-dev python3-dev

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["uvicorn", "scripts.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
