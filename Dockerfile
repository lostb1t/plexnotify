FROM python:3.12-slim-bookworm
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD ["fastapi", "run", "src/main.py"]