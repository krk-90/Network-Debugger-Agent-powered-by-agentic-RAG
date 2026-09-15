# Build the React frontend
FROM node:22-alpine AS frontend-build
WORKDIR /app/app/frontend
COPY app/frontend/package.json ./
RUN npm install
COPY app/frontend/ ./
# A relative API base makes the browser call the same origin as FastAPI.
ENV VITE_API_URL=.
RUN npm run build

# Run FastAPI, React static files, and MCP in one process
FROM python:3.12-slim
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping traceroute mtr-tiny \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend-build /app/app/frontend/dist ./app/frontend/dist

ENV PYTHONUNBUFFERED=1
ENV NETWORK_MCP_HOST=0.0.0.0

EXPOSE 10000

CMD ["sh", "-c", "uvicorn app.backend.route:router --host 0.0.0.0 --port ${PORT:-10000}"]
