from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from google.cloud import storage, bigquery

from src.config import get_settings
from src.gcp.run_jobs import CloudRunJobsRunner


def _bq_video_exists(
    bq: bigquery.Client, dataset: str, table: str, video_uid: str
) -> bool:
    q = f"""
    SELECT 1
    FROM `{bq.project}.{dataset}.{table}`
    WHERE video_uid = @uid
    LIMIT 1
    """
    job = bq.query(
        q,
        job_config=bigquery.QueryJobConfig(
            query_parameters=[bigquery.ScalarQueryParameter("uid", "STRING", video_uid)]
        ),
    )
    return any(True for _ in job.result())


def create_app() -> Flask:
    app = Flask(__name__)
    settings = get_settings()

    jobs = CloudRunJobsRunner(
        project_id=settings.gcp_project, region=settings.run_region
    )
    storage_client = storage.Client(project=settings.gcp_project)
    bq_client = bigquery.Client(project=settings.gcp_project)

    @app.get("/")
    def index():
        return render_template("upload.html")

    @app.get("/healthz")
    def healthz():
        return "ok", 200

    @app.post("/api/upload-video")
    def api_upload_video():
        if "video" not in request.files:
            return (
                jsonify({"ok": False, "message": "No se recibió ningún archivo."}),
                400,
            )

        video = request.files["video"]
        if not video or not video.filename:
            return jsonify({"ok": False, "message": "Archivo inválido."}), 400

        source_type = (request.form.get("source_type") or "").strip()
        provider = (request.form.get("provider") or "").strip() or "unknown"

        if source_type not in {"public", "captured", "simulated"}:
            return jsonify({"ok": False, "message": "Tipo de fuente inválido."}), 400

        ext = Path(video.filename).suffix.lower() or ".mp4"

        # 1) Volcar a /tmp y calcular SHA256 + tamaño
        h = hashlib.sha256()
        total = 0

        tmp_dir = "/tmp"
        os.makedirs(tmp_dir, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            prefix="upload_", suffix=ext, dir=tmp_dir, delete=False
        ) as f:
            tmp_path = Path(f.name)

            while True:
                chunk = video.stream.read(1024 * 1024)  # 1MB
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                total += len(chunk)

        video_uid = h.hexdigest()

        # 2) Dedupe en BQ (NO subimos si existe)
        try:
            exists = _bq_video_exists(
                bq_client, settings.bq_dataset, settings.bq_table_videos, video_uid
            )
        except Exception:
            # Si BQ falla, mejor no subir para evitar duplicados accidentales
            tmp_path.unlink(missing_ok=True)
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "No se pudo verificar duplicados (BigQuery).",
                    }
                ),
                500,
            )

        if exists:
            tmp_path.unlink(missing_ok=True)
            return (
                jsonify(
                    {
                        "ok": False,
                        "duplicate": True,
                        "message": "Duplicado: el vídeo ya existe.",
                    }
                ),
                409,
            )

        # 3) Subir a GCS tmp/videos/<sha>.<ext>
        object_name = f"{settings.gcs_tmp_videos_prefix}/{video_uid}{ext}"
        gcs_uri = f"gs://{settings.gcs_bucket}/{object_name}"

        try:
            bucket = storage_client.bucket(settings.gcs_bucket)
            blob = bucket.blob(object_name)

            with tmp_path.open("rb") as rf:
                blob.upload_from_file(
                    rf,
                    content_type=video.mimetype or "application/octet-stream",
                    rewind=True,
                )

            # 4) Lanzar job (el worker borrará el tmp al final)
            jobs.run_job(
                job_name=settings.run_job_name,
                env_overrides={
                    "INPUT_GCS_URI": gcs_uri,
                    "INPUT_SOURCE_TYPE": source_type,
                    "INPUT_PROVIDER": provider,
                    "INPUT_ORIGINAL_FILENAME": video.filename,
                    "INPUT_VIDEO_UID": video_uid,  # opcional (por si lo quieres usar luego)
                },
            )

            return jsonify({"ok": True, "message": "Subido. Procesamiento iniciado."})

        except Exception:
            return (
                jsonify(
                    {"ok": False, "message": "Ha ocurrido un error durante el proceso."}
                ),
                500,
            )

        finally:
            tmp_path.unlink(missing_ok=True)

    return app


app = create_app()

if __name__ == "__main__":
    settings = get_settings()
    app.run(host=settings.host, port=settings.port, debug=settings.debug)
