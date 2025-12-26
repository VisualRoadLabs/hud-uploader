# **HUD Video Uploader**

![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)
![license](https://img.shields.io/github/license/VisualRoadLabs/hud-uploader?style=flat-square)
![python](https://img.shields.io/badge/python-3.13-blue?style=flat-square)
![docker](https://img.shields.io/badge/docker-ready-blue?style=flat-square)

HUD Video Uploader is a Cloud Run–ready web application for uploading road videos, extracting representative frames, and ingesting structured metadata into Google Cloud Storage and BigQuery for AI and computer vision workflows.

## **Table of Contents**

- [Security](#security)
- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [API](#api)
- [License](#license)

## **Security**

This application relies on **Google Application Default Credentials (ADC)**.

- Local development uses user credentials via:

    ```bash
    gcloud auth application-default login
    ```

- Credentials are stored locally at:

  ```powershell
  C:\Users\<username>\AppData\Roaming\gcloud\application_default_credentials.json
  ```

- In Docker, credentials are mounted read-only into the container.

For production (Cloud Run), a **Service Account** with least-privilege IAM roles should be used:

- BigQuery Data Editor
- BigQuery Job User
- Storage Object Admin

> Never commit credentials or service account keys to the repository.

## **Background**

Modern computer vision pipelines for road understanding require:

- Reliable ingestion of raw video data
- Deterministic deduplication of assets
- Traceability from extracted frames back to source videos
- Scalable metadata storage for downstream AI workflows

This project provides a clean, auditable ingestion layer that bridges raw video uploads with structured datasets stored in Google Cloud Storage and BigQuery.

## **Install**

### **Requirements**

- Python **3.13**
- Docker (recommended)
- Google Cloud SDK (`gcloud`)
- Access to a Google Cloud project with BigQuery and Cloud Storage enabled

### **Local setup (without Docker)**

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Authenticate with Google Cloud:

```bash
gcloud auth application-default login
```

## **Usage**

### **Run locally with Docker (recommended)**

Build the image:

```bash
docker build -t hud-uploader:local .
```

Run the container (PowerShell):

```powershell
docker run --rm -p 8000:8080 `
  -e PORT=8080 `
  -e HOST=0.0.0.0 `
  -e DEBUG=true `
  -e GCP_PROJECT=<your-project-id> `
  -e GCS_BUCKET=<your-gcs-bucket> `
  -e BQ_DATASET=hud__ai__platform `
  -e BQ_TABLE_VIDEOS=raw__videos `
  -e BQ_TABLE_IMAGES=raw__images `
  -e BQ_TABLE_LINEAGE=frame__lineage `
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc/application_default_credentials.json `
  -v "$env:APPDATA\gcloud:/tmp/adc:ro" `
  hud-uploader:local
```

Open your browser at:

```powershell
http://localhost:8000
```

### **Processing flow**

1. Video is uploaded through the web UI
2. Video is deduplicated using a SHA-256 content hash
3. Video is uploaded to Google Cloud Storage
4. Frames are extracted adaptively based on motion and time constraints
5. Frames are uploaded to Google Cloud Storage
6. Metadata is inserted into BigQuery tables: `raw__videos`, `raw__images`, `frame__lineage`

## **API**

This project does not expose a public REST API.

It provides a minimal web interface:

- `GET /` — Upload form
- `POST /` — Video upload and processing

All configuration is managed through environment variables (12-factor compliant).

## **License**

MIT License © HUD AI Platform
