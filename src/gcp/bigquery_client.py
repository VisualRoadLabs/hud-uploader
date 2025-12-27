from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from google.cloud import bigquery

from src.config import Settings


def _chunked(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


class BigQueryClient:
    def __init__(self, project_id: Optional[str], settings: Settings) -> None:
        self.client = bigquery.Client(project=project_id or None)
        self.settings = settings

    def _table_id(self, table_name: str) -> str:
        return f"{self.client.project}.{self.settings.bq_dataset}.{table_name}"

    def video_exists(self, video_uid: str) -> bool:
        table = self._table_id(self.settings.bq_table_videos)
        q = f"SELECT 1 FROM `{table}` WHERE video_uid = @uid LIMIT 1"
        job = self.client.query(
            q,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ScalarQueryParameter("uid", "STRING", video_uid)
                ]
            ),
        )
        return job.result().total_rows > 0

    def insert_raw_videos(self, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        table_id = self._table_id(self.settings.bq_table_videos)
        errors = self.client.insert_rows_json(table_id, rows)
        if errors:
            raise RuntimeError(
                f"BigQuery insert {self.settings.bq_table_videos} error: {errors}"
            )

    def insert_raw_images_chunked(
        self, rows: List[Dict[str, Any]], chunk_size: Optional[int] = None
    ) -> None:
        if not rows:
            return
        table_id = self._table_id(self.settings.bq_table_images)
        cs = chunk_size or self.settings.images_chunk_size
        for batch in _chunked(rows, cs):
            errors = self.client.insert_rows_json(table_id, batch)
            if errors:
                raise RuntimeError(
                    f"BigQuery insert {self.settings.bq_table_images} error: {errors}"
                )

    def insert_frame_lineage_chunked(
        self, rows: List[Dict[str, Any]], chunk_size: Optional[int] = None
    ) -> None:
        if not rows:
            return
        table_id = self._table_id(self.settings.bq_table_lineage)
        cs = chunk_size or self.settings.lineage_chunk_size
        for batch in _chunked(rows, cs):
            errors = self.client.insert_rows_json(table_id, batch)
            if errors:
                raise RuntimeError(
                    f"BigQuery insert {self.settings.bq_table_lineage} error: {errors}"
                )

    def images_exist(self, image_uids: List[str]) -> Set[str]:
        if not image_uids:
            return set()

        table = self._table_id(self.settings.bq_table_images)
        q = f"""
        SELECT image_uid
        FROM `{table}`
        WHERE image_uid IN UNNEST(@uids)
        """

        job = self.client.query(
            q,
            job_config=bigquery.QueryJobConfig(
                query_parameters=[
                    bigquery.ArrayQueryParameter("uids", "STRING", image_uids)
                ]
            ),
        )
        return {row["image_uid"] for row in job.result()}
