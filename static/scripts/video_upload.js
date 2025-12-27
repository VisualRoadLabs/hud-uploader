function setNotice(level, title, body) {
  const notice = document.getElementById("notice");
  const nt = document.getElementById("noticeTitle");
  const nb = document.getElementById("noticeBody");

  notice.style.display = "block";
  notice.classList.remove("notice--ok", "notice--err", "notice--warn");
  notice.classList.add(level === "ok" ? "notice--ok" : (level === "warn" ? "notice--warn" : "notice--err"));

  nt.textContent = title;
  nb.textContent = body;
}

function setBusy(isBusy, text) {
  const btn = document.getElementById("submitBtn");
  const status = document.getElementById("statusText");
  btn.disabled = isBusy;
  status.textContent = text || "";
}

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("uploadForm");
  const fileInput = document.getElementById("video");
  const sourceType = document.getElementById("source_type");
  const provider = document.getElementById("provider");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const file = fileInput.files?.[0];
    if (!file) {
      setNotice("err", "Error", "Selecciona un vídeo.");
      return;
    }

    const fd = new FormData();
    fd.append("video", file);
    fd.append("source_type", sourceType.value);
    fd.append("provider", provider.value || "unknown");

    try {
      setBusy(true, "Subiendo y verificando…");

      const res = await fetch("/api/upload-video", { method: "POST", body: fd });
      const data = await res.json().catch(() => ({}));

      if (res.status === 409 && data?.duplicate) {
        setNotice("warn", "Duplicado", "Este vídeo ya existe. No se ha subido.");
        return;
      }

      if (!res.ok || !data.ok) {
        throw new Error(data?.message || "Ha ocurrido un error durante el proceso.");
      }

      setNotice("ok", "Subido", "Vídeo subido. Procesamiento iniciado.");
      form.reset();

    } catch (err) {
      console.error(err);
      setNotice("err", "Error", err?.message || "Ha ocurrido un error durante el proceso.");
    } finally {
      setBusy(false, "");
    }
  });
});
