# **HUD Video & Image Uploader**

![standard-readme compliant](https://img.shields.io/badge/readme%20style-standard-brightgreen.svg?style=flat-square)
![license](https://img.shields.io/github/license/VisualRoadLabs/hud-uploader?style=flat-square)
![python](https://img.shields.io/badge/python-3.11-blue?style=flat-square)
![docker](https://img.shields.io/badge/docker-ready-blue?style=flat-square)
![cloud-run](https://img.shields.io/badge/google%20cloud-run-blue?style=flat-square)

HUD Uploader is a **Cloud Run–native ingestion platform** for road perception datasets.  
It supports **video uploads** and **image ZIP uploads**, performs deterministic deduplication, extracts metadata and frames, and ingests structured data into **Google Cloud Storage** and **BigQuery** for AI and computer vision workflows.

## **Table of Contents**

- [Security](#security)
- [Architecture](#architecture)
- [Background](#background)
- [Install](#install)
- [Usage](#usage)
- [Deployment](#deployment)
- [Configuration](#configuration)
- [API](#api)
- [License](#license)

## **Security**

This application relies on **Google Application Default Credentials (ADC)**.

### Local development

```bash
gcloud auth application-default login
````

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

The system is composed of **one Cloud Run Service** and **multiple Cloud Run Jobs**, fully decoupled.

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

### **2. Cloud Run Jobs (Batch workers)**

#### **Video ingestion job**

- Downloads the staged video from `tmp/videos`
- Organizes it into:

  ```bash
  raw/videos/<source_type>/<provider>/<job_ts>/<video_uid>.<ext>
  ```

- Extracts frames adaptively
- Stores frames in:

  ```bash
  raw/images/<source_type>/<provider>/<job_ts>/<image_uid>.jpg
  ```

- Inserts metadata into BigQuery: `raw__videos`, `raw__images`
`frame__lineage`
- Deletes the temporary staged object

#### **Image ZIP ingestion job**

- Downloads staged ZIP
- Validates images
- Deduplicates using `image_uid`
- Uploads images to:

  ```bash
  raw/images/<source_type>/<dataset_name>/<job_ts>/<image_uid>.<ext>
  ```

- Inserts metadata into `raw__images`
- Deletes the temporary ZIP

### **Key benefits**

- Clean separation between UI and compute
- No signed URLs required
- Deterministic deduplication
- Fully auditable lineage
- Scales independently per workload

## **Background**

Road perception pipelines require:

- Large-scale ingestion of heterogeneous media
- Strong deduplication guarantees
- Frame-level traceability
- Structured metadata for ML training and audits

HUD Uploader provides a production-ready ingestion layer bridging raw uploads with analytics-ready datasets in GCS and BigQuery.

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
  -e RUN_IMAGES_ZIP_JOB_NAME=hud-images-zip-worker `
  -e GCS_TMP_VIDEOS_PREFIX=tmp/videos `
  -e GCS_TMP_ZIPS_PREFIX=tmp/zips `
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

- Update **Cloud Run Service** image
- Update **Cloud Run Jobs** image versions
- Ensure Service Account permissions remain unchanged

## **Configuration**

All behavior is controlled via environment variables (12-factor compliant).

Key variables:

- `RUN_REGION`
- `RUN_JOB_NAME`
- `RUN_IMAGES_ZIP_JOB_NAME`
- `GCS_TMP_VIDEOS_PREFIX`
- `GCS_TMP_ZIPS_PREFIX`
- `MIN_FPS`, `MAX_FPS`, `MOTION_THRESHOLD`

Defaults are safe for production and can be overridden.

## **API**

### Endpoints

Available endpoints:

- `GET /` — Upload UI
- `POST /api/upload-video` — Video upload
- `POST /api/upload-images-zip` — Image ZIP upload
- `GET /healthz` — Health check

No public REST API is exposed beyond ingestion.

## **License**

MIT License © HUD AI Platform
