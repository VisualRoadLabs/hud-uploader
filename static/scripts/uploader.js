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

function setBusy(btnId, statusId, isBusy, text) {
  const btn = document.getElementById(btnId);
  const status = document.getElementById(statusId);
  btn.disabled = isBusy;
  status.textContent = text || "";
}

function activateTab(which) {
  const btnVideo = document.getElementById("tabBtnVideo");
  const btnZip = document.getElementById("tabBtnZip");
  const panelVideo = document.getElementById("panelVideo");
  const panelZip = document.getElementById("panelZip");

  const isVideo = which === "video";

  btnVideo.classList.toggle("tab--active", isVideo);
  btnZip.classList.toggle("tab--active", !isVideo);

  btnVideo.setAttribute("aria-selected", isVideo ? "true" : "false");
  btnZip.setAttribute("aria-selected", !isVideo ? "true" : "false");

  panelVideo.style.display = isVideo ? "block" : "none";
  panelZip.style.display = isVideo ? "none" : "block";

  // Opcional: limpiar aviso al cambiar pestaña
  const notice = document.getElementById("notice");
  notice.style.display = "none";
}

async function handleVideoUpload(e) {
  e.preventDefault();

  const fileInput = document.getElementById("video_file");
  const sourceType = document.getElementById("video_source_type");
  const provider = document.getElementById("video_provider");

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
    setBusy("videoSubmitBtn", "videoStatusText", true, "Subiendo y verificando…");

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
    document.getElementById("uploadVideoForm").reset();

  } catch (err) {
    console.error(err);
    setNotice("err", "Error", err?.message || "Ha ocurrido un error durante el proceso.");
  } finally {
    setBusy("videoSubmitBtn", "videoStatusText", false, "");
  }
}

async function handleZipUpload(e) {
  e.preventDefault();

  const fileInput = document.getElementById("zip_file");
  const sourceType = document.getElementById("zip_source_type");
  const datasetName = document.getElementById("dataset_name");

  const file = fileInput.files?.[0];
  if (!file) {
    setNotice("err", "Error", "Selecciona un ZIP.");
    return;
  }

  // Validación rápida de extensión
  const name = (file.name || "").toLowerCase();
  if (!name.endsWith(".zip")) {
    setNotice("err", "Error", "El archivo debe ser .zip");
    return;
  }

  const dn = (datasetName.value || "").trim();
  if (!dn) {
    setNotice("err", "Error", "dataset_name es obligatorio.");
    return;
  }

  const fd = new FormData();
  fd.append("zipfile", file);
  fd.append("source_type", sourceType.value);
  fd.append("dataset_name", dn);

  try {
    setBusy("zipSubmitBtn", "zipStatusText", true, "Subiendo ZIP…");

    const res = await fetch("/api/upload-images-zip", { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));

    if (!res.ok || !data.ok) {
      throw new Error(data?.message || "Ha ocurrido un error durante el proceso.");
    }

    setNotice("ok", "Subido", "ZIP subido. Descompresión e ingesta iniciadas.");
    document.getElementById("uploadZipForm").reset();

  } catch (err) {
    console.error(err);
    setNotice("err", "Error", err?.message || "Ha ocurrido un error durante el proceso.");
  } finally {
    setBusy("zipSubmitBtn", "zipStatusText", false, "");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Tabs
  document.getElementById("tabBtnVideo").addEventListener("click", () => activateTab("video"));
  document.getElementById("tabBtnZip").addEventListener("click", () => activateTab("zip"));

  // Forms
  document.getElementById("uploadVideoForm").addEventListener("submit", handleVideoUpload);
  document.getElementById("uploadZipForm").addEventListener("submit", handleZipUpload);
});
