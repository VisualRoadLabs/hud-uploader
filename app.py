from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, request, render_template

from src.config import get_settings
from src.pipelines.video_ingest import process_video_upload


UPLOAD_TMP_DIR = Path(".tmp_uploads")
UPLOAD_TMP_DIR.mkdir(parents=True, exist_ok=True)


def create_app() -> Flask:
    app = Flask(__name__)
    settings = get_settings()

    @app.route("/", methods=["GET", "POST"])
    def index():
        ctx = {
            "message": None,
            "level": "ok",  # ok | warn | err
            "title": "",
            "details": None,
            "year": 2025,
        }

        if request.method == "GET":
            return render_template("upload.html", **ctx)

        try:
            source_type = (request.form.get("source_type") or "").strip()
            provider = (request.form.get("provider") or "").strip()
            f = request.files.get("video")

            if not f or not f.filename:
                ctx.update(
                    level="err",
                    title="Error",
                    message="No se recibió ningún archivo.",
                    details=None,
                )
                return render_template("upload.html", **ctx)

            tmp_name = f"upload_{os.getpid()}_{Path(f.filename).name}"
            tmp_path = UPLOAD_TMP_DIR / tmp_name
            f.save(str(tmp_path))

            result = process_video_upload(
                settings=settings,
                local_video_path=tmp_path,
                original_filename=f.filename,
                source_type=source_type,
                provider=provider,
            )

            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

            if result.status == "duplicate":
                ctx.update(
                    level="warn",
                    title="Duplicado",
                    message="Este vídeo ya estaba cargado. No se ha duplicado.",
                    details=None,
                )
            else:
                details = (
                    f"Se han generado {result.nb_frames} imágenes."
                    if settings.extract_frames
                    else None
                )
                ctx.update(
                    level="ok",
                    title="Subido",
                    message="Vídeo subido y procesado correctamente.",
                    details=details,
                )

            return render_template("upload.html", **ctx)

        except Exception as e:
            ctx.update(
                level="err",
                title="Error",
                message="Ha ocurrido un error durante el proceso.",
                details=str(e),
            )
            return render_template("upload.html", **ctx)

    return app


if __name__ == "__main__":
    settings = get_settings()
    app = create_app()
    app.run(host=settings.host, port=settings.port, debug=settings.debug)
