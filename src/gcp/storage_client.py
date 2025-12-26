from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from google.cloud import storage


@dataclass(frozen=True)
class GCSObject:
    bucket: str
    name: str

    @property
    def uri(self) -> str:
        return f"gs://{self.bucket}/{self.name}"


class StorageClient:
    def __init__(self, project_id: Optional[str] = None) -> None:
        self.client = storage.Client(project=project_id or None)

    def upload_file(self, bucket: str, object_name: str, local_path: Path) -> GCSObject:
        b = self.client.bucket(bucket)
        blob = b.blob(object_name)
        blob.upload_from_filename(str(local_path))
        return GCSObject(bucket=bucket, name=object_name)

    def upload_bytes(
        self, bucket: str, object_name: str, data: bytes, content_type: str
    ) -> GCSObject:
        b = self.client.bucket(bucket)
        blob = b.blob(object_name)
        blob.upload_from_string(data, content_type=content_type)
        return GCSObject(bucket=bucket, name=object_name)
