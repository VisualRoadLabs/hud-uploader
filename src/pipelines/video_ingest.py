from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.config import Settings
from src.gcp.storage_client import StorageClient
from src.gcp.bigquery_client import BigQueryClient

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}
JOB_TS_FMT = "%Y%m%dT%H%M%SZ"
FRAME_EXT = ".jpg"


@dataclass(frozen=True)
class PipelineResult:
    status: str  # "ok" | "duplicate"
    message: str
    nb_frames: int = 0


@dataclass(frozen=True)
class ExtractedFrame:
    image_uid: str
    timestamp_ms: int
    frame_idx: int
    jpg_bytes: bytes
    width: int
    height: int
    sha256: str
    file_size_bytes: int


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def utc_now_job_ts() -> str:
    return utc_now().strftime(JOB_TS_FMT)


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            b = f.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run_ffprobe(video_path: Path) -> Optional[Dict]:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,r_frame_rate,avg_frame_rate",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(video_path),
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
        return json.loads(out.decode("utf-8", errors="replace"))
    except Exception:
        return None


def parse_fps(rate: str) -> float:
    if not rate or "/" not in rate:
        return 0.0
    num, den = rate.split("/", 1)
    try:
        n = float(num)
        d = float(den)
        return n / d if d != 0 else 0.0
    except Exception:
        return 0.0


def get_video_metadata(video_path: Path) -> Tuple[int, float, str]:
    data = run_ffprobe(video_path)
    if data:
        duration_s = 0.0
        try:
            duration_s = float(data.get("format", {}).get("duration", 0.0) or 0.0)
        except Exception:
            duration_s = 0.0

        streams = data.get("streams", []) or []
        stream0 = streams[0] if streams else {}
        codec = str(stream0.get("codec_name") or "unknown")

        fps = parse_fps(str(stream0.get("avg_frame_rate") or ""))
        if fps <= 0:
            fps = parse_fps(str(stream0.get("r_frame_rate") or ""))

        return int(round(duration_s * 1000.0)), fps, codec

    # Fallback OpenCV
    import cv2  # type: ignore

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return 0, 0.0, "unknown"
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
    duration_s = (frame_count / fps) if fps > 0 else 0.0
    cap.release()
    return int(round(duration_s * 1000.0)), fps, "unknown"


def gcs_video_object(
    source_type: str, provider: str, job_ts: str, filename: str
) -> str:
    return f"raw/videos/{source_type}/{provider}/{job_ts}/{filename}"


def gcs_image_object(
    source_type: str, provider: str, job_ts: str, filename: str
) -> str:
    return f"raw/images/{source_type}/{provider}/{job_ts}/{filename}"


def extract_frames_adaptive(
    video_path: Path, video_uid: str, settings: Settings
) -> List[ExtractedFrame]:
    """
    Extrae frames adaptativos devolviendo bytes JPEG + dims.
    """
    import cv2  # type: ignore

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    min_interval_ms = int(round(1000.0 / settings.max_fps))
    desired_interval_ms = int(round(1000.0 / settings.min_fps))
    max_interval_ms = int(round(settings.max_interval_s * 1000.0))

    frames: List[ExtractedFrame] = []
    last_saved_ts: Optional[int] = None
    last_gray_small = None
    frame_idx = 0

    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            break

        timestamp_ms = int(round(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0))

        # motion score
        h, w = frame.shape[:2]
        if w > settings.downscale_width:
            scale = settings.downscale_width / float(w)
            new_w = settings.downscale_width
            new_h = max(1, int(round(h * scale)))
            frame_small = cv2.resize(
                frame, (new_w, new_h), interpolation=cv2.INTER_AREA
            )
        else:
            frame_small = frame

        gray_small = cv2.cvtColor(frame_small, cv2.COLOR_BGR2GRAY)

        motion_score = 0.0
        if last_gray_small is not None:
            diff = cv2.absdiff(gray_small, last_gray_small)
            motion_score = float(diff.mean())

        save = False
        if last_saved_ts is None:
            save = True
        else:
            since_last = timestamp_ms - last_saved_ts
            if since_last < min_interval_ms:
                save = False
            else:
                if since_last >= max_interval_ms:
                    save = True
                elif motion_score >= settings.motion_threshold:
                    save = True
                elif since_last >= desired_interval_ms:
                    save = True

        last_gray_small = gray_small

        if not save:
            frame_idx += 1
            continue

        # encode jpeg
        encode_params = [
            int(cv2.IMWRITE_JPEG_QUALITY),
            int(settings.frame_jpeg_quality),
        ]
        ok2, buf = cv2.imencode(".jpg", frame, encode_params)
        if not ok2:
            frame_idx += 1
            continue

        jpg_bytes = buf.tobytes()
        seed = (video_uid + ":" + str(timestamp_ms)).encode("utf-8") + b":" + jpg_bytes
        image_uid = sha256_bytes(seed)

        file_sha = sha256_bytes(jpg_bytes)
        file_size = len(jpg_bytes)

        # width/height del frame original
        height, width = frame.shape[:2]

        frames.append(
            ExtractedFrame(
                image_uid=image_uid,
                timestamp_ms=timestamp_ms,
                frame_idx=frame_idx,
                jpg_bytes=jpg_bytes,
                width=int(width),
                height=int(height),
                sha256=file_sha,
                file_size_bytes=int(file_size),
            )
        )

        last_saved_ts = timestamp_ms
        frame_idx += 1

    cap.release()
    return frames


def process_video_upload(
    *,
    settings: Settings,
    local_video_path: Path,
    original_filename: str,
    source_type: str,
    provider: str,
) -> PipelineResult:
    """
    Flujo final:
        - Dedupe en BigQuery (video_uid)
        - Subir video a GCS
        - Extraer frames adaptativos
        - Subir frames a GCS
        - Insert:
            raw__videos (1)
            raw__images (N)
            frame__lineage (N)
    """
    provider = (provider or "").strip() or "unknown"
    source_type = (source_type or "").strip()

    if source_type not in {"public", "captured", "simulated"}:
        raise ValueError("source_type inválido. Usa public/captured/simulated.")

    ext = Path(original_filename).suffix.lower()
    if ext not in VIDEO_EXTS:
        raise ValueError(f"Extensión no soportada: {ext}")

    # Clients (ADC en local / SA en Cloud Run)
    storage = StorageClient(project_id=settings.gcp_project)
    bq = BigQueryClient(project_id=settings.gcp_project, settings=settings)

    video_uid = sha256_file(local_video_path)

    # Dedup
    if bq.video_exists(video_uid):
        return PipelineResult(
            status="duplicate",
            message="Este vídeo ya estaba cargado. No se ha duplicado.",
        )

    ingest_ts = utc_now_iso()
    job_ts = utc_now_job_ts()
    source_name = Path(original_filename).stem  # humano

    # Upload video (renombrado por hash en destino)
    video_filename = f"{video_uid}{ext}"
    video_obj = gcs_video_object(source_type, provider, job_ts, video_filename)
    gcs_video = storage.upload_file(settings.gcs_bucket, video_obj, local_video_path)

    # Video metadata
    duration_ms, fps, codec = get_video_metadata(local_video_path)

    # Frames
    frames: List[ExtractedFrame] = []
    if settings.extract_frames:
        frames = extract_frames_adaptive(local_video_path, video_uid, settings)

    nb_frames = len(frames)

    # Upload frames + prepare BQ rows
    extract_job_id = ingest_ts  # simple y consistente

    images_rows: List[Dict] = []
    lineage_rows: List[Dict] = []

    for fr in frames:
        img_filename = f"{fr.image_uid}{FRAME_EXT}"
        img_obj = gcs_image_object(source_type, provider, job_ts, img_filename)
        gcs_img = storage.upload_bytes(
            settings.gcs_bucket,
            img_obj,
            fr.jpg_bytes,
            content_type="image/jpeg",
        )

        # raw__images row
        images_rows.append(
            {
                "image_uid": fr.image_uid,
                "source_type": source_type,
                "source_name": source_name,  # mismo “origen humano” que el vídeo
                "gcs_uri": gcs_img.uri,
                "ingest_ts": ingest_ts,
                "width": fr.width,
                "height": fr.height,
                "format": "jpg",
                "sha256": fr.sha256,
                "file_size_bytes": fr.file_size_bytes,
            }
        )

        # frame__lineage row
        lineage_rows.append(
            {
                "image_uid": fr.image_uid,
                "video_uid": video_uid,
                "frame_idx": fr.frame_idx,
                "timestamp_ms": fr.timestamp_ms,
                "extract_job_id": extract_job_id,
            }
        )

    # Insert raw__videos (1 row)
    bq.insert_raw_videos(
        [
            {
                "video_uid": video_uid,
                "gcs_uri": gcs_video.uri,
                "duration_ms": int(duration_ms),
                "fps": float(fps),
                "codec": str(codec),
                "source_type": source_type,
                "source_name": source_name,
                "ingest_ts": ingest_ts,
                "nb_frames": int(nb_frames),
            }
        ]
    )

    # Insert raw__images (chunked)
    if images_rows:
        bq.insert_raw_images_chunked(images_rows)

    # Insert frame__lineage (chunked)
    if lineage_rows:
        bq.insert_frame_lineage_chunked(lineage_rows)

    return PipelineResult(
        status="ok",
        message="Vídeo subido y procesado correctamente.",
        nb_frames=nb_frames,
    )
