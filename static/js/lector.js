const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const frozenFrame = document.getElementById("frozenFrame");
const btnStart = document.getElementById("btnStart");
const btnFlash = document.getElementById("btnFlash");
const btnManualCapture = document.getElementById("btnManualCapture");
const processingOverlay = document.getElementById("processingOverlay");
const phaseText = document.getElementById("phaseText");
const resultModal = document.getElementById("resultModal");
const connectionDot = document.getElementById("connectionDot");
const connectionText = document.getElementById("connectionText");
const aforoHeader = document.getElementById("aforoHeader");
const eventoMeta = document.getElementById("eventoMeta");
const lectorMeta = document.getElementById("lectorMeta");
const pinLoginModal = document.getElementById("pinLoginModal");
const lectorPinGrid = document.getElementById("lectorPinGrid");
const pinDigitInputs = Array.from(document.querySelectorAll(".pin-digit"));
const lectorPinLoginBtn = document.getElementById("lectorPinLoginBtn");
const lectorPinError = document.getElementById("lectorPinError");

const guestInfo = document.getElementById("guestInfo");
const btnPlusOne = document.getElementById("btnPlusOne");
const btnPlusTwo = document.getElementById("btnPlusTwo");
const btnAll = document.getElementById("btnAll");
const btnCancelGuest = document.getElementById("btnCancelGuest");

let stream = null;
let currentValidatedGuest = null;
let torchEnabled = false;
let currentAforo = { actual: 0, max: 0 };
let currentEvent = { id: "", nombre: "Evento SIGA", estado: "borrador" };
let currentLector = { uid: "", nombre: "", rol: "" };
let scanIntervalId = null;
let isProcessing = false;
let isFrameFrozen = false;
let nextScanAt = 0;
let qrDetector = null;
let detectorWarningShown = false;
let manualCaptureMode = false;
let heartbeatIntervalId = null;
const deviceId = getOrCreateDeviceId();

btnStart?.addEventListener("click", toggleCamera);
btnFlash?.addEventListener("click", toggleFlash);
btnManualCapture?.addEventListener("click", captureManualPhotoAndValidate);
lectorPinLoginBtn?.addEventListener("click", loginLectorWithPin);
bindPinInputs();
window.addEventListener("online", () => setConnectionStatus("nube"));
window.addEventListener("offline", () => setConnectionStatus("local"));
window.addEventListener("beforeunload", () => {
  try {
    navigator.sendBeacon("/api/lector/logout", JSON.stringify({ device_id: deviceId }));
  } catch (_error) {
    // noop
  }
});

document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    stopAutoScanLoop();
    return;
  }
  if (stream && !isFrameFrozen) startAutoScanLoop();
});

init();

async function init() {
  setConnectionStatus(navigator.onLine ? "nube" : "local");
  setupQrDetector();
  renderDetectorSupportState();
  await ensureLectorLogin();
  await refreshLectorEstado();
  setInterval(refreshLectorEstado, 20000);
  startHeartbeat();
}

function setupQrDetector() {
  if (typeof window.BarcodeDetector !== "function") return;
  try {
    qrDetector = new window.BarcodeDetector({ formats: ["qr_code"] });
  } catch (_error) {
    qrDetector = null;
  }
}

function renderDetectorSupportState() {
  manualCaptureMode = !qrDetector;
  if (!manualCaptureMode) {
    btnManualCapture?.classList.add("hidden");
    return;
  }
  btnManualCapture?.classList.remove("hidden");
  if (detectorWarningShown) return;
  detectorWarningShown = true;
  resetGuestPanel();
  [btnPlusOne, btnPlusTwo, btnAll].forEach((btn) => {
    if (!btn) return;
    btn.disabled = true;
    btn.onclick = null;
  });
  btnCancelGuest?.classList.add("hidden");
  updateManualCaptureAvailability();
}

function getOrCreateDeviceId() {
  const key = "siga_lector_device_id";
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;
  const generated = `dev_${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36).slice(-4)}`;
  window.localStorage.setItem(key, generated);
  return generated;
}

function bindPinInputs() {
  if (!pinDigitInputs.length) return;
  pinDigitInputs.forEach((input, index) => {
    input.addEventListener("input", (event) => {
      const onlyDigits = String(event.target.value || "").replace(/\D/g, "");
      event.target.value = onlyDigits.slice(0, 1);
      if (event.target.value && index < pinDigitInputs.length - 1) {
        pinDigitInputs[index + 1].focus();
      }
      if (getPinValue().length === 6) {
        void loginLectorWithPin();
      }
    });

    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        void loginLectorWithPin();
        return;
      }
      if (event.key === "Backspace" && !input.value && index > 0) {
        pinDigitInputs[index - 1].focus();
      }
      if (event.key === "ArrowLeft" && index > 0) {
        event.preventDefault();
        pinDigitInputs[index - 1].focus();
      }
      if (event.key === "ArrowRight" && index < pinDigitInputs.length - 1) {
        event.preventDefault();
        pinDigitInputs[index + 1].focus();
      }
    });
  });

  lectorPinGrid?.addEventListener("paste", (event) => {
    const text = (event.clipboardData?.getData("text") || "").replace(/\D/g, "").slice(0, 6);
    if (!text) return;
    event.preventDefault();
    pinDigitInputs.forEach((input, i) => {
      input.value = text[i] || "";
    });
    const next = Math.min(text.length, pinDigitInputs.length - 1);
    pinDigitInputs[next].focus();
    if (text.length === 6) {
      void loginLectorWithPin();
    }
  });
}

function getPinValue() {
  return pinDigitInputs.map((x) => String(x.value || "").replace(/\D/g, "")).join("");
}

function clearPinInputs() {
  pinDigitInputs.forEach((x) => {
    x.value = "";
  });
}

function showPinError(message) {
  if (!lectorPinError) return;
  lectorPinError.textContent = message;
  lectorPinError.classList.remove("hidden");
}

function hidePinError() {
  if (!lectorPinError) return;
  lectorPinError.classList.add("hidden");
  lectorPinError.textContent = "";
}

function setLectorHeader() {
  if (!lectorMeta) return;
  if (currentLector?.nombre) {
    lectorMeta.textContent = `Lector: ${currentLector.nombre}`;
  } else {
    lectorMeta.textContent = "Lector: sin sesión";
  }
}

async function ensureLectorLogin() {
  hidePinError();
  clearPinInputs();
  const autoLogin = await tryAdminAutoLogin();
  if (autoLogin) {
    pinLoginModal.classList.add("hidden");
    setLectorHeader();
    return;
  }
  pinLoginModal.classList.remove("hidden");
  pinDigitInputs[0]?.focus();
  setLectorHeader();
}

async function tryAdminAutoLogin() {
  try {
    const mode = navigator.onLine ? "online" : "local";
    const response = await fetch("/api/lector/admin_login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId, modo: mode }),
    });
    if (!response.ok) return false;
    const payload = await response.json().catch(() => ({}));
    if (!payload?.ok) return false;
    currentLector = payload.data || { uid: "", nombre: "", rol: "admin" };
    return true;
  } catch (_error) {
    return false;
  }
}

async function loginLectorWithPin() {
  const pin = getPinValue();
  if (!/^\d{6}$/.test(pin)) {
    showPinError("Ingresa un PIN de 6 dígitos");
    return;
  }
  hidePinError();
  lectorPinLoginBtn.disabled = true;
  try {
    const mode = navigator.onLine ? "online" : "local";
    const response = await fetch("/api/lector/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin, device_id: deviceId, modo: mode }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.error || `HTTP ${response.status}`);
    }
    currentLector = payload.data || { uid: "", nombre: "", rol: "lector" };
    setLectorHeader();
    clearPinInputs();
    pinLoginModal.classList.add("hidden");
    await refreshLectorEstado();
    await startCamera();
  } catch (error) {
    showPinError(error.message || "No se pudo iniciar sesión de lector");
    pinLoginModal.classList.remove("hidden");
  } finally {
    lectorPinLoginBtn.disabled = false;
  }
}

function startHeartbeat() {
  stopHeartbeat();
  heartbeatIntervalId = window.setInterval(() => {
    void sendHeartbeat();
  }, 10000);
}

function stopHeartbeat() {
  if (!heartbeatIntervalId) return;
  window.clearInterval(heartbeatIntervalId);
  heartbeatIntervalId = null;
}

async function sendHeartbeat() {
  if (pinLoginModal && !pinLoginModal.classList.contains("hidden")) return;
  try {
    const mode = navigator.onLine ? "online" : "local";
    const response = await fetch("/api/lector/heartbeat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: deviceId, modo: mode }),
    });
    if (response.ok) {
      const payload = await response.json().catch(() => ({}));
      if (payload?.requires_pin || payload?.code === "LECTOR_PIN_REQUIRED" || payload?.code === "LECTOR_SESSION_EXPIRED") {
        await handleLectorSessionExpired();
        return;
      }
    }
    if (response.status === 401) {
      await handleLectorSessionExpired();
    }
  } catch (_error) {
    // noop
  }
}

async function handleLectorSessionExpired() {
  stopAutoScanLoop();
  stopCamera();
  currentLector = { uid: "", nombre: "", rol: "" };
  const autoLogin = await tryAdminAutoLogin();
  if (autoLogin) {
    hidePinError();
    pinLoginModal.classList.add("hidden");
    setLectorHeader();
    await refreshLectorEstado();
    await startCamera();
    return;
  }
  setLectorHeader();
  pinLoginModal.classList.remove("hidden");
  clearPinInputs();
  pinDigitInputs[0]?.focus();
}

async function refreshLectorEstado() {
  if (pinLoginModal && !pinLoginModal.classList.contains("hidden")) return;
  try {
    const res = await fetch("/api/lector_estado");
    if (res.status === 401) {
      await handleLectorSessionExpired();
      return;
    }
    const payload = await res.json();
    if (!res.ok || payload.ok === false) throw new Error(payload.error || `HTTP ${res.status}`);

    const data = payload.data || {};
    if (data.requires_pin) {
      await handleLectorSessionExpired();
      return;
    }
    currentAforo.actual = Number(data.aforo_actual || 0);
    currentAforo.max = Number(data.aforo_max || 0);
    currentEvent = {
      id: String(data.evento_id || ""),
      nombre: String(data.evento_nombre || "Evento SIGA"),
      estado: String(data.evento_estado || "borrador"),
    };
    currentLector = data.lector || currentLector;

    aforoHeader.textContent = `${currentAforo.actual}/${currentAforo.max}`;
    eventoMeta.textContent = `${currentEvent.nombre} (${currentEvent.estado})`;
    setLectorHeader();
    setConnectionStatus(data.firebase_ready ? "nube" : "local");
  } catch (_error) {
    setConnectionStatus("local");
    aforoHeader.textContent = `${currentAforo.actual}/${currentAforo.max}`;
  }
}

async function toggleCamera() {
  if (!pinLoginModal.classList.contains("hidden")) return;
  if (stream) {
    stopCamera();
    return;
  }
  await startCamera();
}

async function startCamera() {
  if (stream) return;
  unfreezeCameraFrame({ resumeScan: false });
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } },
      audio: false,
    });

    video.srcObject = stream;
    video.muted = true;
    video.setAttribute("muted", "");
    video.playsInline = true;
    video.setAttribute("playsinline", "");
    video.setAttribute("webkit-playsinline", "");
    await video.play().catch(() => {});

    btnStart.textContent = "Pausar camara";
    btnFlash.disabled = false;
    updateManualCaptureAvailability();
    startAutoScanLoop();
  } catch (error) {
    stopCamera();
    showResult({
      type: "error",
      title: "Acceso denegado",
      message: `No se pudo abrir camara: ${error.message}`,
      actionLabel: "Cerrar",
    });
  }
}

function stopCamera() {
  stopAutoScanLoop();
  stream?.getTracks?.().forEach((track) => track.stop());
  stream = null;
  video.srcObject = null;
  unfreezeCameraFrame({ resumeScan: false });
  torchEnabled = false;
  btnFlash.textContent = "Flash";
  btnFlash.disabled = true;
  btnStart.textContent = "Reanudar camara";
  updateManualCaptureAvailability();
}

function startAutoScanLoop() {
  if (manualCaptureMode) return;
  if (isFrameFrozen) return;
  stopAutoScanLoop();
  scanIntervalId = window.setInterval(() => {
    void autoScanTick();
  }, 650);
}

function stopAutoScanLoop() {
  if (scanIntervalId) {
    window.clearInterval(scanIntervalId);
    scanIntervalId = null;
  }
}

function canAttemptScan() {
  if (!stream) return false;
  if (!qrDetector) return false;
  if (isFrameFrozen) return false;
  if (isProcessing) return false;
  if (Date.now() < nextScanAt) return false;
  if (document.hidden) return false;
  if (!video.videoWidth || !video.videoHeight) return false;
  if (!resultModal.classList.contains("hidden")) return false;
  if (!pinLoginModal.classList.contains("hidden")) return false;
  if (currentValidatedGuest !== null) return false;
  return true;
}

async function autoScanTick() {
  if (!canAttemptScan()) return;

  const frame = captureFrame();
  if (!frame) return;

  const hasQr = await detectQrInCanvas();
  if (!hasQr) {
    nextScanAt = Date.now() + 180;
    return;
  }

  freezeCameraFrame(captureFreezeFrame());
  await validateFrame(frame.imagenBase64, true);
}

function captureFrame() {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) return null;

  const side = Math.floor(Math.min(vw, vh) * 0.62);
  const sx = Math.floor((vw - side) / 2);
  const sy = Math.floor((vh - side) / 2);

  canvas.width = side;
  canvas.height = side;

  const ctx = canvas.getContext("2d");
  if (!ctx) return null;

  ctx.drawImage(video, sx, sy, side, side, 0, 0, side, side);
  return {
    imagenBase64: canvas.toDataURL("image/jpeg", 0.65),
  };
}

function captureFreezeFrame() {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) return "";
  const freezeCanvas = document.createElement("canvas");
  freezeCanvas.width = vw;
  freezeCanvas.height = vh;
  const ctx = freezeCanvas.getContext("2d");
  if (!ctx) return "";
  ctx.drawImage(video, 0, 0, vw, vh);
  return freezeCanvas.toDataURL("image/jpeg", 0.72);
}

function freezeCameraFrame(frameDataUrl = "") {
  if (isFrameFrozen) return;
  isFrameFrozen = true;
  stopAutoScanLoop();
  try {
    video.pause();
  } catch (_error) {
    // noop
  }
  if (frozenFrame && frameDataUrl) {
    frozenFrame.src = frameDataUrl;
    frozenFrame.classList.remove("hidden");
  }
}

function unfreezeCameraFrame({ resumeScan = true } = {}) {
  if (!isFrameFrozen && !frozenFrame?.src) return;
  isFrameFrozen = false;
  if (frozenFrame) {
    frozenFrame.classList.add("hidden");
    frozenFrame.removeAttribute("src");
  }
  if (stream) {
    void video.play().catch(() => {});
  }
  if (resumeScan && stream && !document.hidden) {
    nextScanAt = Date.now() + 450;
    startAutoScanLoop();
  }
}

async function detectQrInCanvas() {
  if (!qrDetector) return false;
  try {
    const found = await qrDetector.detect(canvas);
    return Array.isArray(found) && found.length > 0;
  } catch (_error) {
    return false;
  }
}

async function validateFrame(imagenBase64, showLoader = true) {
  isProcessing = true;
  updateManualCaptureAvailability();
  if (showLoader) {
    showProcessing();
    phaseText.textContent = "PDI Fase: Analizando";
  }

  try {
    const response = await fetch("/validar_qr", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ imagen_base64: imagenBase64 }),
    });

    if (response.status === 401) {
      if (showLoader) hideProcessing();
      await handleLectorSessionExpired();
      unfreezeCameraFrame({ resumeScan: false });
      return;
    }

    const data = await response.json();
    if (showLoader) hideProcessing();

    if (!response.ok || !data.ok || !data.valido) {
      if (data?.error === "QR no legible") {
        unfreezeCameraFrame();
        nextScanAt = Date.now() + 500;
        return;
      }

      vibrate("error");
      showResult({
        type: "error",
        title: "Acceso denegado",
        message: data.error || "Codigo QR invalido o falsificado",
        actionLabel: "Cerrar",
      });
      nextScanAt = Date.now() + 1200;
      return;
    }

    const invitado = data.invitado || null;

    if (!invitado) {
      vibrate("warn");
      showResult({
        type: "warn",
        title: "Atencion",
        message: data.mensaje || "QR valido sin invitado registrado",
        actionLabel: "Cerrar",
      });
      nextScanAt = Date.now() + 1200;
      return;
    }

    if (data.evento_estado === "cerrado") {
      vibrate("warn");
      showResult({
        type: "warn",
        title: "Evento cerrado",
        message: "El evento esta cerrado. Solo admins con override pueden registrar ingresos.",
        actionLabel: "Cerrar",
      });
      nextScanAt = Date.now() + 1200;
      return;
    }

    const cupoTotal = Number(invitado.cupo_total || 1);
    const cupoUsado = Number(invitado.cupo_usado ?? invitado.ingresados ?? 0);

    if (cupoUsado >= cupoTotal) {
      showGuestSnapshot({
        invitadoId: data.invitado_id,
        invitadoKey: data.invitado_key || "",
        nombre: invitado.nombre_lider || invitado.nombre || "Invitado",
        cuenta: invitado.id || data.invitado_id,
        cupoTotal,
        cupoUsado,
        fase: data.fase_exitosa || "N/A",
      }, "Cupo agotado. Puedes solicitar aumento de cupo.");
      vibrate("warn");
      showResult({
        type: "warn",
        title: "Cupo agotado",
        message: `Este QR ya utilizo todo su cupo (${cupoUsado}/${cupoTotal}).`,
        actionLabel: "Cerrar",
        secondaryLabel: "Solicitar más cupo",
        onSecondary: async () => {
          await solicitarAumentoCupo(data.invitado_id, data.invitado_key || "", cupoUsado, cupoTotal);
        },
      });
      nextScanAt = Date.now() + 1200;
      return;
    }

    vibrate("ok");
    showGuestActions({
      invitadoId: data.invitado_id,
      invitadoKey: data.invitado_key || "",
      nombre: invitado.nombre_lider || invitado.nombre || "Invitado",
      cuenta: invitado.id || data.invitado_id,
      cupoTotal,
      cupoUsado,
      fase: data.fase_exitosa || "N/A",
    });
    nextScanAt = Date.now() + 1200;
  } catch (error) {
    if (showLoader) hideProcessing();
    setConnectionStatus("local");
    vibrate("error");
    showResult({
      type: "error",
      title: "Error de red",
      message: error.message,
      actionLabel: "Cerrar",
    });
    nextScanAt = Date.now() + 1500;
  } finally {
    isProcessing = false;
    updateManualCaptureAvailability();
  }
}

function showProcessing() {
  processingOverlay.classList.remove("hidden");
}

function hideProcessing() {
  processingOverlay.classList.add("hidden");
}

function resetGuestPanel() {
  currentValidatedGuest = null;
  if (guestInfo) {
    guestInfo.innerHTML = manualCaptureMode
      ? `<p class="placeholder-text">Presiona "Tomar foto y validar" para capturar el QR</p>`
      : `<p class="placeholder-text">Enfoca un código QR para escanear</p>`;
  }
  btnCancelGuest?.classList.add("hidden");
  [btnPlusOne, btnPlusTwo, btnAll].forEach((btn) => {
    if (btn) {
      btn.disabled = true;
      btn.onclick = null;
    }
  });
  updateManualCaptureAvailability();
}

function showGuestSnapshot(guest, statusText = "") {
  const disponibles = Math.max(Number(guest.cupoTotal || 0) - Number(guest.cupoUsado || 0), 0);
  currentValidatedGuest = null;
  guestInfo.innerHTML = `
    <h3>QR detectado</h3>
    <p><strong>${escapeHtml(guest.nombre)}</strong></p>
    <p>Cupo: <strong>${guest.cupoUsado}/${guest.cupoTotal}</strong> &nbsp;—&nbsp; Disponibles: <strong>${disponibles}</strong></p>
    <small>ID: ${escapeHtml(guest.cuenta)} &nbsp;|&nbsp; Fase PDI: ${escapeHtml(guest.fase)}</small>
    ${statusText ? `<p><small>${escapeHtml(statusText)}</small></p>` : ""}
  `;
  btnCancelGuest?.classList.add("hidden");
  [btnPlusOne, btnPlusTwo, btnAll].forEach((btn) => {
    if (btn) {
      btn.disabled = true;
      btn.onclick = null;
    }
  });
}

btnCancelGuest?.addEventListener("click", () => {
  unfreezeCameraFrame();
  resetGuestPanel();
  nextScanAt = Date.now() + 500;
  updateManualCaptureAvailability();
});

function showGuestActions(guest) {
  const disponibles = Math.max(Number(guest.cupoTotal || 0) - Number(guest.cupoUsado || 0), 0);
  const allowOne = disponibles >= 1;
  const allowTwo = disponibles >= 2;
  const allowAll = disponibles >= 1;

  currentValidatedGuest = guest;

  guestInfo.innerHTML = `
    <h3>Invitación válida</h3>
    <p><strong>${escapeHtml(guest.nombre)}</strong></p>
    <p>Cupo: <strong>${guest.cupoUsado}/${guest.cupoTotal}</strong> &nbsp;—&nbsp; Disponibles: <strong>${disponibles}</strong></p>
    <small>ID: ${escapeHtml(guest.cuenta)} &nbsp;|&nbsp; Fase PDI: ${escapeHtml(guest.fase)}</small>
  `;

  btnCancelGuest?.classList.remove("hidden");

  const bindAction = (btn, modo, allowed) => {
    if (!btn) return;
    btn.disabled = !allowed;
    btn.onclick = async () => {
      btn.disabled = true;
      const registro = await registrarIngreso(guest.invitadoId, guest.invitadoKey, modo, guest.cupoUsado, guest.fase, false);
      if (!registro.ok) {
        btn.disabled = false;
        return;
      }
      showConfirmation(registro.delta > 0 ? registro.delta : 1);
      bumpAforo(registro.delta > 0 ? registro.delta : 1);
      unfreezeCameraFrame();
      resetGuestPanel();
      await refreshLectorEstado();
      updateManualCaptureAvailability();
    };
  };

  bindAction(btnPlusOne, "1", allowOne);
  bindAction(btnPlusTwo, "2", allowTwo);
  bindAction(btnAll, "todos", allowAll);
}

function showResult({ type, title, message, detail, actionLabel, secondaryLabel, onSecondary }) {
  resultModal.className = `result-modal ${type}`;
  resultModal.innerHTML = `
    <h3>${escapeHtml(title)}</h3>
    <p>${escapeHtml(message)}</p>
    ${detail ? `<small>${escapeHtml(detail)}</small>` : ""}
    <div class="result-actions">
      ${secondaryLabel ? `<button class="btn btn-secondary" data-secondary="true">${escapeHtml(secondaryLabel)}</button>` : ""}
      <button class="btn btn-muted btn-block" data-close="true">${escapeHtml(actionLabel || "Cerrar")}</button>
    </div>
  `;

  resultModal.classList.remove("hidden");
  resultModal.querySelector("[data-close='true']")?.addEventListener("click", () => {
    resultModal.classList.add("hidden");
    if (!currentValidatedGuest) {
      unfreezeCameraFrame();
    }
    updateManualCaptureAvailability();
  });
  if (secondaryLabel && typeof onSecondary === "function") {
    resultModal.querySelector("[data-secondary='true']")?.addEventListener("click", async () => {
      await onSecondary();
    });
  }
}

function updateManualCaptureAvailability() {
  if (!btnManualCapture) return;
  if (!manualCaptureMode) {
    btnManualCapture.classList.add("hidden");
    return;
  }
  btnManualCapture.classList.remove("hidden");
  const modalOpen = !resultModal.classList.contains("hidden");
  const pinModalOpen = !!pinLoginModal && !pinLoginModal.classList.contains("hidden");
  const canCapture = !!stream && !isProcessing && !isFrameFrozen && !modalOpen && !pinModalOpen && !currentValidatedGuest;
  btnManualCapture.disabled = !canCapture;
}

async function captureManualPhotoAndValidate() {
  if (!manualCaptureMode) return;
  if (!stream || isProcessing || isFrameFrozen || currentValidatedGuest) return;
  const frame = captureFrame();
  if (!frame) {
    showResult({
      type: "error",
      title: "Camara no lista",
      message: "No se pudo capturar la imagen. Intenta nuevamente en unos segundos.",
      actionLabel: "Cerrar",
    });
    updateManualCaptureAvailability();
    return;
  }
  freezeCameraFrame(captureFreezeFrame());
  updateManualCaptureAvailability();
  await validateFrame(frame.imagenBase64, true);
}

async function solicitarAumentoCupo(invitadoId, invitadoKey, cupoUsado = 0, cupoTotal = 0) {
  const ingreso = window.prompt("¿Cuántos boletos extra deseas solicitar?", "1");
  if (ingreso === null) return;
  const cantidad = Math.trunc(Number(ingreso));
  if (!Number.isFinite(cantidad) || cantidad < 1) {
    showResult({
      type: "warn",
      title: "Solicitud inválida",
      message: "Debes ingresar una cantidad válida mayor o igual a 1.",
      actionLabel: "Volver",
    });
    return;
  }

  try {
    const response = await fetch("/api/solicitudes_cupo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        invitado_id: invitadoId,
        invitado_key: invitadoKey,
        cantidad_solicitada: cantidad,
        motivo: `Solicitado desde lector. Cupo actual ${cupoUsado}/${cupoTotal}`,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    const decision = String(data.decision_automatica || "").toLowerCase();
    if (decision === "aprobada") {
      showResult({
        type: "success",
        title: "Cupo aprobado",
        message: "La solicitud fue aprobada automáticamente por disponibilidad.",
        detail: `Cantidad aprobada: +${Number(data?.solicitud?.cantidad_aprobada || cantidad)}`,
        actionLabel: "Cerrar",
      });
      return;
    }
    if (decision === "rechazada") {
      showResult({
        type: "warn",
        title: "Solicitud rechazada",
        message: "No hay disponibilidad de aforo para aumentar cupo en este momento.",
        detail: `Solicitado: +${cantidad}`,
        actionLabel: "Cerrar",
      });
      return;
    }
    showResult({
      type: "success",
      title: "Solicitud registrada",
      message: "La solicitud de cupo fue registrada.",
      detail: `Cantidad solicitada: +${cantidad}`,
      actionLabel: "Cerrar",
    });
  } catch (error) {
    showResult({
      type: "error",
      title: "No se pudo solicitar",
      message: error.message || "Error al enviar la solicitud",
      actionLabel: "Volver",
    });
  }
}

async function registrarIngreso(invitadoId, invitadoKey, modo, usadosAntes = 0, fasePdi = "N/D", adminOverride = false) {
  try {
    let pinConfirm = "";
    if (adminOverride) {
      pinConfirm = window.prompt("Ingresa PIN para autorizar override:") || "";
      if (!pinConfirm.trim()) {
        showResult({
          type: "warn",
          title: "Override cancelado",
          message: "Se requiere PIN para continuar.",
          actionLabel: "Volver",
        });
        return { ok: false, delta: 0 };
      }
    }
    const response = await fetch("/registrar_ingreso", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        invitado_id: invitadoId,
        invitado_key: invitadoKey,
        modo,
        fase_pdi: fasePdi,
        admin_override: adminOverride,
        pin_confirm: pinConfirm,
        device_id: deviceId,
      }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (data.code === "EVENT_CLOSED" && !adminOverride) {
        showResult({
          type: "warn",
          title: "Evento cerrado",
          message: "Solo admin puede forzar el registro.",
          actionLabel: "Cancelar",
          secondaryLabel: "Forzar",
          onSecondary: async () => {
            resultModal.classList.add("hidden");
            await registrarIngreso(invitadoId, invitadoKey, modo, usadosAntes, fasePdi, true);
          },
        });
        return { ok: false, delta: 0 };
      }

      if (data.code === "LECTOR_PIN_REQUIRED" || data.code === "LECTOR_SESSION_EXPIRED") {
        await handleLectorSessionExpired();
      }

      showResult({
        type: "warn",
        title: "No se pudo registrar",
        message: data.error || `HTTP ${response.status}`,
        actionLabel: "Volver",
      });
      return { ok: false, delta: 0 };
    }

    const usadosDespues = Number(data.cupo_usado ?? data.ingresados ?? 0);
    const deltaReal = Math.max(usadosDespues - Number(usadosAntes || 0), 0);
    return { ok: true, delta: deltaReal };
  } catch (error) {
    showResult({
      type: "error",
      title: "Error",
      message: error.message,
      actionLabel: "Volver",
    });
    return { ok: false, delta: 0 };
  }
}

function showConfirmation(cantidad) {
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = `Bienvenidos (+${cantidad})`;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.remove();
  }, 1400);
}

async function toggleFlash() {
  const track = stream?.getVideoTracks?.()[0];
  if (!track) return;

  const capabilities = track.getCapabilities?.();
  if (!capabilities?.torch) {
    showResult({
      type: "warn",
      title: "Flash no disponible",
      message: "Este dispositivo no soporta control de flash desde navegador.",
      actionLabel: "Continuar",
    });
    return;
  }

  try {
    torchEnabled = !torchEnabled;
    await track.applyConstraints({ advanced: [{ torch: torchEnabled }] });
    btnFlash.textContent = torchEnabled ? "Flash ON" : "Flash";
  } catch (_error) {
    torchEnabled = false;
    btnFlash.textContent = "Flash";
  }
}

function setConnectionStatus(mode) {
  const isOnline = mode === "nube";
  connectionDot.classList.toggle("online", isOnline);
  connectionDot.classList.toggle("local", !isOnline);
  connectionText.textContent = isOnline ? "Nube" : "Local";
}

function bumpAforo(delta) {
  currentAforo.actual = Math.max(0, Number(currentAforo.actual || 0) + Number(delta || 0));
  if (currentAforo.max > 0) {
    currentAforo.actual = Math.min(currentAforo.actual, currentAforo.max);
  }
  aforoHeader.textContent = `${currentAforo.actual}/${currentAforo.max}`;
}

function vibrate(mode) {
  if (!navigator.vibrate) return;

  if (mode === "ok") navigator.vibrate([80]);
  else if (mode === "warn") navigator.vibrate([120, 80, 120]);
  else navigator.vibrate([300]);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
