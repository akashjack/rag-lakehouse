# EC2 Deployment Guide

## Target architecture
EC2 t3.xlarge (4 vCPU, 16 GiB RAM)

├── Docker Compose

│   ├── rag-oracle      Oracle 23ai Free  (EBS gp3 50 GiB)

│   ├── rag-ollama      Ollama + models   (EBS gp3 20 GiB)

│   ├── rag-minio       MinIO object store

│   ├── rag-iceberg     Iceberg REST catalog

│   └── rag-api         FastAPI gateway   (port 8000)

└── Security group

├── 22   SSH (your IP only)

├── 8000 FastAPI (your IP only)

└── 4200 Angular dev server (optional)

## Prerequisites

- AWS account with EC2 access
- Key pair created in target region
- AWS CLI configured locally

## Step 1 — Launch EC2 instance

```bash
# Launch t3.xlarge with Ubuntu 24.04
aws ec2 run-instances \
  --image-id ami-0c7217cdde317cfec \  # Ubuntu 24.04 us-east-1
  --instance-type t3.xlarge \
  --key-name YOUR_KEY_PAIR \
  --security-group-ids sg-XXXXXXXX \
  --block-device-mappings '[
    {
      "DeviceName": "/dev/sda1",
      "Ebs": {"VolumeSize": 80, "VolumeType": "gp3"}
    }
  ]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=rag-lakehouse}]' \
  --count 1
```

## Step 2 — Security group rules

```bash
# Create security group
aws ec2 create-security-group \
  --group-name rag-lakehouse-sg \
  --description "RAG Lakehouse security group"

# SSH — your IP only
aws ec2 authorize-security-group-ingress \
  --group-name rag-lakehouse-sg \
  --protocol tcp --port 22 --cidr YOUR_IP/32

# FastAPI — your IP only
aws ec2 authorize-security-group-ingress \
  --group-name rag-lakehouse-sg \
  --protocol tcp --port 8000 --cidr YOUR_IP/32

# Prometheus (optional)
aws ec2 authorize-security-group-ingress \
  --group-name rag-lakehouse-sg \
  --protocol tcp --port 9090 --cidr YOUR_IP/32

# Grafana (optional)
aws ec2 authorize-security-group-ingress \
  --group-name rag-lakehouse-sg \
  --protocol tcp --port 3000 --cidr YOUR_IP/32
```

## Step 3 — Bootstrap the instance

SSH in and run:

```bash
ssh -i YOUR_KEY.pem ubuntu@EC2_PUBLIC_IP

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu
newgrp docker

# Install uv + Node.js
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs git

# Clone the repo
git clone https://github.com/akashjack/rag-lakehouse.git
cd rag-lakehouse
```

## Step 4 — Configure environment

```bash
cp .env.example .env

# Edit the following in .env:
# ORACLE_APP_PWD=<strong-password>
# OLLAMA_BASE_URL=http://localhost:11434
# S3_ENDPOINT=http://localhost:9000
nano .env
```

## Step 5 — Start the stack

```bash
# Create the Docker network
docker network create ragnet

# Start MinIO + Iceberg REST
docker compose -f infra/docker/docker-compose.minio.yml up -d
docker compose -f infra/docker/docker-compose.lakehouse.yml up -d

# Start Oracle 23ai (first boot takes ~3 minutes)
docker compose -f infra/docker/docker-compose.indexer.yml up -d rag-oracle
echo "Waiting for Oracle to initialize..."
sleep 180
docker exec rag-oracle bash -c "echo SELECT 1 FROM DUAL | sqlplus -s sys/RagPass_2026@FREEPDB1 as sysdba"

# Start Ollama and pull models
docker compose -f infra/docker/docker-compose.indexer.yml up -d rag-ollama
docker exec rag-ollama ollama pull nomic-embed-text
docker exec rag-ollama ollama pull llama3.2:3b

# Bootstrap Oracle schema
cd services/indexer
uv venv && uv pip install -e "."
.venv/bin/python -m indexer schema-init
cd ../..

# Run the embed job
make idx-embed

# Verify
cd services/indexer && .venv/bin/python -m indexer stats
```

## Step 6 — Start the API

```bash
cd ~/rag-lakehouse/services/api
uv venv && uv pip install -e "." -e "../indexer"

# Run with systemd (recommended for production)
sudo tee /etc/systemd/system/rag-api.service << EOF
[Unit]
Description=RAG Lakehouse FastAPI
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/rag-lakehouse/services/api
ExecStart=/home/ubuntu/rag-lakehouse/services/api/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable rag-api
sudo systemctl start rag-api
sudo systemctl status rag-api
```

## Step 7 — Verify production deployment

```bash
# From your local machine:
curl http://EC2_PUBLIC_IP:8000/health
# Expected: {"status":"ok","oracle":"up","ollama":"up"}

curl "http://EC2_PUBLIC_IP:8000/search?q=kubernetes+pod&k=3"
# Expected: JSON with ranked chunks

curl -X POST http://EC2_PUBLIC_IP:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "what is a kubernetes pod?", "k": 3}'
# Expected: SSE token stream
```

## Step 8 — Observability (optional)

```bash
cd ~/rag-lakehouse
make obs-up
# Prometheus: http://EC2_PUBLIC_IP:9090
# Grafana:    http://EC2_PUBLIC_IP:3000  (admin/admin)
```

## Cost estimate

| Resource | Spec | Monthly cost (approx) |
|---|---|---|
| EC2 t3.xlarge | 4 vCPU, 16 GiB | ~$120 |
| EBS gp3 80 GiB | Root + Oracle | ~$8 |
| Data transfer | Minimal | ~$1 |
| **Total** | | **~$130/month** |

> Stop the instance when not in use to avoid charges:
> `aws ec2 stop-instances --instance-ids i-XXXXXXXXX`

## Troubleshooting

| Symptom | Fix |
|---|---|
| Oracle ORA-51928 on embed | Drop HNSW index before load, rebuild after |
| Ollama timeout on first request | Model loading takes 30s on cold start — retry |
| FTS returns 0 results | Run `CTX_DDL.SYNC_INDEX('CHUNKS_EMBED_TEXT_IDX')` |
| API 500 on /search | Check `journalctl -u rag-api -n 50` for traceback |
