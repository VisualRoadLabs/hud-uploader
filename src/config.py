from __future__ import annotations
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # GCP
    gcp_project: str
    gcs_bucket: str

    # BigQuery
    bq_dataset: str
    bq_table_videos: str
    bq_table_images: str
    bq_table_lineage: str

    # Video sampling
    extract_frames: bool
    min_fps: float
    max_fps: float
    max_interval_s: float
    motion_threshold: float
    downscale_width: int
    frame_jpeg_quality: int

    # BQ batching
    lineage_chunk_size: int
    images_chunk_size: int

    # Web
    host: str
    port: int
    debug: bool

    # Cloud Run Job (manual trigger)
    run_region: str
    run_job_name: str
    run_images_zip_job_name: str

    # GCS tmp staging
    gcs_tmp_videos_prefix: str
    gcs_tmp_zips_prefix: str


def _get_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "y", "on"}


def get_settings() -> Settings:
    return Settings(
        gcp_project=os.environ.get("GCP_PROJECT"),
        gcs_bucket=os.environ.get("GCS_BUCKET"),
        bq_dataset=os.environ.get("BQ_DATASET", "hud__ai__platform"),
        bq_table_videos=os.environ.get("BQ_TABLE_VIDEOS", "raw__videos"),
        bq_table_images=os.environ.get("BQ_TABLE_IMAGES", "raw__images"),
        bq_table_lineage=os.environ.get("BQ_TABLE_LINEAGE", "frame__lineage"),
        extract_frames=_get_bool("EXTRACT_FRAMES", True),
        min_fps=float(os.environ.get("MIN_FPS", "0.5")),
        max_fps=float(os.environ.get("MAX_FPS", "5.0")),
        max_interval_s=float(os.environ.get("MAX_INTERVAL_S", "10.0")),
        motion_threshold=float(os.environ.get("MOTION_THRESHOLD", "12.0")),
        downscale_width=int(os.environ.get("DOWNSCALE_WIDTH", "320")),
        frame_jpeg_quality=int(os.environ.get("FRAME_JPEG_QUALITY", "92")),
        lineage_chunk_size=int(os.environ.get("LINEAGE_CHUNK_SIZE", "500")),
        images_chunk_size=int(os.environ.get("IMAGES_CHUNK_SIZE", "500")),
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        debug=_get_bool("DEBUG", True),
        run_region=os.environ.get("RUN_REGION", "us-central1"),
        run_job_name=os.environ.get("RUN_JOB_NAME", "hud-video-worker"),
        run_images_zip_job_name=os.environ.get(
            "RUN_IMAGES_ZIP_JOB_NAME", "hud-images-zip-worker"
        ),
        gcs_tmp_videos_prefix=os.environ.get("GCS_TMP_VIDEOS_PREFIX", "tmp/videos"),
        gcs_tmp_zips_prefix=os.environ.get("GCS_TMP_ZIPS_PREFIX", "tmp/zips"),
    )
