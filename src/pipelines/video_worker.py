from __future__ import annotations

import os
from pathlib import Path

from google.cloud import storage
from google.api_core.exceptions import NotFound

from ..config import get_settings
from ..pipelines.video_ingest import process_video_upload


def parse_gcs_uri(gcs_uri: str) -> tuple[str, str]:
    if not gcs_uri.startswith("gs://"):
        raise ValueError("gcs_uri debe empezar por gs://")
    x = gcs_uri[len("gs://") :]
    bucket, _, obj = x.partition("/")
    if not bucket or not obj:
        raise ValueError("gcs_uri inválido")
    return bucket, obj


def main() -> None:
    settings = get_settings()

    gcs_uri = os.environ.get("INPUT_GCS_URI", "").strip()
    source_type = os.environ.get("INPUT_SOURCE_TYPE", "").strip()
    provider = os.environ.get("INPUT_PROVIDER", "").strip() or "unknown"
    original_filename = (
        os.environ.get("INPUT_ORIGINAL_FILENAME", "").strip() or "uploaded_video.mp4"
    )

    if not gcs_uri:
        raise RuntimeError("Falta INPUT_GCS_URI")
    if source_type not in {"public", "captured", "simulated"}:
        raise RuntimeError("INPUT_SOURCE_TYPE inválido")

    ext = Path(original_filename).suffix.lower() or ".mp4"
    local_video = (Path("/tmp") / "input_video").with_suffix(ext)

    client = storage.Client(project=settings.gcp_project)

    bucket_name, object_name = parse_gcs_uri(gcs_uri)
    blob = client.bucket(bucket_name).blob(object_name)

    # Descarga staging
    local_video.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(str(local_video))

    try:
        process_video_upload(
            settings=settings,
            local_video_path=local_video,
            original_filename=original_filename,
            source_type=source_type,
            provider=provider,
        )
    finally:
        # 1) Borra staging tmp/videos (si existe)
        try:
            blob.delete()
            print(f"[OK] Deleted staging object: {gcs_uri}")
        except NotFound:
            print(f"[INFO] Staging object already deleted: {gcs_uri}")
        except Exception as e:
            print(f"[WARN] Could not delete staging object: {gcs_uri} -> {e}")

        # 2) Limpia disco
        try:
            local_video.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
