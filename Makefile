dev:
	.venv/bin/fastapi dev src/main.py
  
run:
	.venv/bin/fastapi run src/main.py

prod:
	fastapi run src/main.py

env:
	.venv/bin/pip install -r requirements.txt

tunnel:
	tailscale funnel 8000

  

build:
	docker buildx build -t ghcr.io/lostb1t/plexnotify:latest  .

release:
	docker buildx build --push --platform linux/amd64,linux/arm64 -t ghcr.io/lostb1t/plexnotify:latest  .
