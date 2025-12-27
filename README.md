# **HUD Video Uploader**

![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)
![license](https://img.shields.io/github/license/VisualRoadLabs/hud-uploader?style=flat-square)
![python](https://img.shields.io/badge/python-3.11-blue?style=flat-square)
![docker](https://img.shields.io/badge/docker-ready-blue?style=flat-square)

HUD Video Uploader is a **Cloud Run–native video ingestion platform** designed for road and driving datasets.  
It provides a clean, auditable pipeline to upload videos, deduplicate them, extract representative frames, and ingest structured metadata into **Google Cloud Storage** and **BigQuery** for AI and computer vision workflows.

## **Table of Contents**

- [Security](#security)
- [Architecture](#architecture)
- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [Deployment](#deployment)
- [API](#api)
- [License](#license)

## **Security**

This application relies on **Google Application Default Credentials (ADC)**.

### Local development

```bash
gcloud auth application-default login
```

Credentials are stored locally at:

```powershell
C:\Users\<username>\AppData\Roaming\gcloud\application_default_credentials.json
```

In Docker, credentials are mounted **read-only** into the container.

### Production (Cloud Run)

For production, use a **dedicated Service Account** with least-privilege IAM roles:

- BigQuery Data Editor
- BigQuery Job User
- Storage Object Admin
- Cloud Run Invoker (Service to Job)

> Never commit credentials or service account keys to the repository.

## **Architecture**

The final architecture is composed of **two decoupled Cloud Run components**:

### **1. Cloud Run Service (Web entrypoint)**

- Authenticated web interface
- Receives video uploads via `multipart/form-data`
- Streams the upload to `/tmp`
- Computes a **SHA-256 hash** for deterministic deduplication
- Checks **BigQuery** to avoid re-ingesting duplicates
- Uploads valid videos to **GCS temporary staging**:

  ```powershell
  tmp/videos/<video_uid>.<ext>
  ```

- Triggers a **Cloud Run Job** with metadata passed as environment variables

### **2. Cloud Run Job (Batch worker)**

- Downloads the staged video from `tmp/videos`
- Organizes it into:

  ```powershell
  raw/videos/<source_type>/<provider>/<job_ts>/<video_uid>.<ext>
  ```

- Extracts frames adaptively based on motion and time thresholds
- Stores frames under:

  ```powershell
  raw/images/<source_type>/<provider>/<job_ts>/<image_uid>.jpg
  ```

- Inserts metadata into BigQuery: `raw__videos`, `raw__images`, `frame__lineage`.
- Deletes the temporary object in `tmp/videos`
- Cleans up local `/tmp` storage

This design:

- Fully decouples web traffic from heavy compute
- Prevents duplicate ingestions
- Avoids signed URLs and complex IAM setups
- Scales cleanly and predictably
- Provides full end-to-end lineage

## **Background**

Modern road perception pipelines require:

- Reliable ingestion of large video assets
- Deterministic deduplication
- Frame-level traceability
- Structured metadata storage for ML training and auditing

HUD Video Uploader provides a production-ready ingestion layer bridging raw video uploads with analytics-ready datasets in GCS and BigQuery.

## **Install**

### **Requirements**

- Python **3.11**
- Docker (recommended)
- Google Cloud SDK (`gcloud`)
- A Google Cloud project with: Cloud Run, BigQuery, Cloud Storage.

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
  -e RUN_REGION=us-central1 `
  -e RUN_JOB_NAME=hud-video-worker `
  -e GCS_TMP_VIDEOS_PREFIX=tmp/videos `
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc/application_default_credentials.json `
  -v "$env:APPDATA\gcloud:/tmp/adc:ro" `
  hud-uploader:local
```

Open:

```bash
http://localhost:8000
```

## **Deployment**

### **Publish image to Docker Hub**

```bash
docker build -t mgonzalz/hud-uploader:latest .
docker push mgonzalz/hud-uploader:latest
```

### **Promote image to GCR (from Cloud Shell)**

```bash
docker pull mgonzalz/hud-uploader:latest
docker tag mgonzalz/hud-uploader:latest gcr.io/braided-torch-459606-c6/hud-uploader:vXXXXXXXX
docker push gcr.io/braided-torch-459606-c6/hud-uploader:vXXXXXXXX
```

### **Update Cloud Run Service and Job**

After pushing a new version:

- Update the **Cloud Run Service** image:

  ```bash
  gcr.io/braided-torch-459606-c6/hud-uploader:vXXXXXXXX
  ```

- Update the **Cloud Run Job** to use the same (or compatible) image version

This ensures service and worker remain in sync.

## **API**

This project does not expose a public REST API.

Available endpoints:

- `GET /` — Upload UI
- `POST /api/upload-video` — Video upload
- `GET /healthz` — Health check

All configuration is provided via environment variables (12-factor compliant).

## **License**

MIT License © HUD AI Platform
