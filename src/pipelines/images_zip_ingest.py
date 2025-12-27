from __future__ import annotations

import io
import os
import zipfile
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image  # type: ignore

from src.config import Settings
from src.gcp.storage_client import StorageClient
from src.gcp.bigquery_client import BigQueryClient

JOB_TS_FMT = "%Y%m%dT%H%M%SZ"

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MIME_BY_EXT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def utc_now_job_ts() -> str:
    return utc_now().strftime(JOB_TS_FMT)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def normalize_ext(name: str) -> str:
    return (Path(name).suffix or "").lower()


def pick_output_ext(img: Image.Image, original_ext: str) -> str:
    # Mantén ext si es soportada; si no, jpg.
    if original_ext in ALLOWED_EXTS:
        return ".jpg" if original_ext == ".jpeg" else original_ext
    return ".jpg"


def gcs_image_object(
    source_type: str, dataset_name: str, job_ts: str, filename: str
) -> str:
    return f"raw/images/{source_type}/{dataset_name}/{job_ts}/{filename}"


@dataclass(frozen=True)
class ZipIngestResult:
    status: str  # "ok"
    message: str
    nb_images_inserted: int
    nb_images_skipped_duplicates: int
    nb_images_invalid: int


def _chunk_list(items: List[str], size: int) -> List[List[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def process_images_zip(
    *,
    settings: Settings,
    local_zip_path: Path,
    source_type: str,
    dataset_name: str,
) -> ZipIngestResult:
    """
    - Descomprime ZIP
    - Para cada imagen válida:
        - image_uid = sha256(bytes)
        - dedupe en BQ
        - sube a raw/images/<source_type>/<dataset_name>/<job_ts>/<image_uid>.<ext>
        - inserta raw__images
    """
    if source_type not in {"public", "captured", "simulated"}:
        raise ValueError("source_type inválido. Usa public/captured/simulated.")
    dataset_name = (dataset_name or "").strip()
    if not dataset_name:
        raise ValueError("dataset_name es obligatorio.")

    storage = StorageClient(project_id=settings.gcp_project)
    bq = BigQueryClient(project_id=settings.gcp_project, settings=settings)

    ingest_ts = utc_now_iso()
    job_ts = utc_now_job_ts()

    # 1) Leer ZIP y recolectar imágenes (en memoria, una a una)
    #    Primero recolectamos (uid, bytes, meta preliminar) para dedupe por lotes
    candidates: List[Tuple[str, bytes, str]] = []  # (image_uid, bytes, ext)
    invalid = 0

    with zipfile.ZipFile(local_zip_path, "r") as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = info.filename
            ext = normalize_ext(name)
            if ext not in ALLOWED_EXTS:
                continue

            try:
                data = z.read(info)
                if not data:
                    invalid += 1
                    continue

                image_uid = sha256_bytes(data)
                candidates.append((image_uid, data, ext))
            except Exception:
                invalid += 1

    if not candidates:
        return ZipIngestResult(
            status="ok",
            message="ZIP sin imágenes válidas.",
            nb_images_inserted=0,
            nb_images_skipped_duplicates=0,
            nb_images_invalid=invalid,
        )

    # 2) Dedupe por lotes (BQ)
    uids = [c[0] for c in candidates]
    existing: set[str] = set()
    for chunk in _chunk_list(uids, min(2000, max(1, settings.images_chunk_size * 4))):
        existing |= bq.images_exist(chunk)

    # 3) Subida + filas BQ
    rows: List[Dict] = []
    inserted = 0
    skipped = 0

    for image_uid, data, in_ext in candidates:
        if image_uid in existing:
            skipped += 1
            continue

        # Validación dims/formato
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.load()
                width, height = im.size
                out_ext = pick_output_ext(im, in_ext)
                fmt = out_ext.lstrip(".")
        except Exception:
            invalid += 1
            continue

        filename = f"{image_uid}{out_ext}"
        obj = gcs_image_object(source_type, dataset_name, job_ts, filename)

        gcs_obj = storage.upload_bytes(
            settings.gcs_bucket,
            obj,
            data,
            content_type=MIME_BY_EXT.get(out_ext, "application/octet-stream"),
        )

        rows.append(
            {
                "image_uid": image_uid,
                "source_type": source_type,
                "source_name": dataset_name,  # dataset como source_name
                "gcs_uri": gcs_obj.uri,
                "ingest_ts": ingest_ts,
                "width": int(width),
                "height": int(height),
                "format": fmt,
                "sha256": image_uid,  # hash del contenido
                "file_size_bytes": int(len(data)),
            }
        )
        inserted += 1

        # Insert en chunks para no acumular demasiado
        if len(rows) >= settings.images_chunk_size:
            bq.insert_raw_images_chunked(rows)
            rows.clear()

    if rows:
        bq.insert_raw_images_chunked(rows)

    return ZipIngestResult(
        status="ok",
        message="ZIP procesado correctamente.",
        nb_images_inserted=inserted,
        nb_images_skipped_duplicates=skipped,
        nb_images_invalid=invalid,
    )
