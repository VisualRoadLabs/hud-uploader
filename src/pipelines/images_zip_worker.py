from __future__ import annotations

import os
from pathlib import Path

from google.cloud import storage
from google.api_core.exceptions import NotFound

from src.config import get_settings
from src.pipelines.images_zip_ingest import process_images_zip


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
    dataset_name = os.environ.get("INPUT_DATASET_NAME", "").strip()

    if not gcs_uri:
        raise RuntimeError("Falta INPUT_GCS_URI")
    if source_type not in {"public", "captured", "simulated"}:
        raise RuntimeError("INPUT_SOURCE_TYPE inválido")
    if not dataset_name:
        raise RuntimeError("Falta INPUT_DATASET_NAME")

    local_zip = Path("/tmp/input_images.zip")

    client = storage.Client(project=settings.gcp_project)
    bucket_name, object_name = parse_gcs_uri(gcs_uri)
    blob = client.bucket(bucket_name).blob(object_name)

    # Descarga staging zip
    local_zip.parent.mkdir(parents=True, exist_ok=True)
    blob.download_to_filename(str(local_zip))

    try:
        res = process_images_zip(
            settings=settings,
            local_zip_path=local_zip,
            source_type=source_type,
            dataset_name=dataset_name,
        )
        print(
            f"[OK] {res.message} inserted={res.nb_images_inserted} dup={res.nb_images_skipped_duplicates} invalid={res.nb_images_invalid}"
        )
    finally:
        # Borra staging tmp/zips
        try:
            blob.delete()
            print(f"[OK] Deleted staging object: {gcs_uri}")
        except NotFound:
            print(f"[INFO] Staging object already deleted: {gcs_uri}")
        except Exception as e:
            print(f"[WARN] Could not delete staging object: {gcs_uri} -> {e}")

        # Limpia disco
        try:
            local_zip.unlink(missing_ok=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
