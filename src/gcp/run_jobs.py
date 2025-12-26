from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, Optional

import google.auth
import google.auth.transport.requests
import requests


@dataclass(frozen=True)
class RunJobResult:
    execution_name: str


class CloudRunJobsRunner:
    """
    Lanza ejecuciones de Cloud Run Jobs vía REST API v2, con overrides de env vars.
    """

    def __init__(self, project_id: str, region: str) -> None:
        self.project_id = project_id
        self.region = region

    def run_job(
        self,
        *,
        job_name: str,
        env_overrides: Dict[str, str],
    ) -> RunJobResult:
        # Obtiene token ADC / service account
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        auth_req = google.auth.transport.requests.Request()
        creds.refresh(auth_req)
        token = creds.token

        url = f"https://run.googleapis.com/v2/projects/{self.project_id}/locations/{self.region}/jobs/{job_name}:run"

        payload = {
            "overrides": {
                "containerOverrides": [
                    {"env": [{"name": k, "value": v} for k, v in env_overrides.items()]}
                ]
            }
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        r = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
        if r.status_code >= 400:
            raise RuntimeError(f"Cloud Run Job run failed ({r.status_code}): {r.text}")

        data = r.json()
        # La respuesta trae execution.name
        execution_name = data.get("name", "")
        return RunJobResult(execution_name=execution_name)
