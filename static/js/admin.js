const navMenu = document.getElementById("navMenu");
const adminLayout = document.querySelector(".admin-layout");
const mobileMenuToggle = document.getElementById("mobileMenuToggle");
const mobileMenuClose = document.getElementById("mobileMenuClose");
const sidebarOverlay = document.getElementById("sidebarOverlay");
const headerTitle = document.getElementById("headerTitle");
const subheaderStatus = document.getElementById("subheaderStatus");
const opsEventChip = document.getElementById("opsEventChip");
const opsAforoChip = document.getElementById("opsAforoChip");
const globalNotice = document.getElementById("globalNotice");
const globalNoticeText = document.getElementById("globalNoticeText");
const globalNoticeClose = document.getElementById("globalNoticeClose");

const openInviteModalBtn = document.getElementById("openInviteModal");
const closeInviteModalBtn = document.getElementById("closeInviteModal");
const inviteModal = document.getElementById("inviteModal");
const inviteModalForm = document.getElementById("inviteModalForm");
const editInviteModal = document.getElementById("editInviteModal");
const closeEditInviteModal = document.getElementById("closeEditInviteModal");
const editInviteForm = document.getElementById("editInviteForm");
const editLectorModal = document.getElementById("editLectorModal");
const closeEditLectorModal = document.getElementById("closeEditLectorModal");
const editLectorForm = document.getElementById("editLectorForm");

const fileInput = document.getElementById("fileInput");
const selectFileBtn = document.getElementById("selectFileBtn");
const uploadZone = document.getElementById("uploadZone");
const uploadProgressWrapper = document.getElementById("uploadProgressWrapper");
const uploadProgress = document.getElementById("uploadProgress");
const uploadStatus = document.getElementById("uploadStatus");
const sendInvitesBtn = document.getElementById("sendInvitesBtn");
const downloadTemplateBtn = document.getElementById("downloadTemplateBtn");

const aforoCard = document.getElementById("aforoCard");
const aforoValue = document.getElementById("aforoValue");
const aforoLevelText = document.getElementById("aforoLevelText");
const aforoProgress = document.getElementById("aforoProgress");
const metricRegistrados = document.getElementById("metricRegistrados");
const metricPendientes = document.getElementById("metricPendientes");
const syncCard = document.getElementById("syncCard");
const metricSync = document.getElementById("metricSync");
const ingresosBody = document.getElementById("ingresosBody");
const metricLastSync = document.getElementById("metricLastSync");
const metricReadersOnline = document.getElementById("metricReadersOnline");
const metricReadersLocal = document.getElementById("metricReadersLocal");
const metricReadersTotal = document.getElementById("metricReadersTotal");
const metricReadersBody = document.getElementById("metricReadersBody");
const retrySyncBtn = document.getElementById("retrySyncBtn");
const goReportesBtn = document.getElementById("goReportesBtn");

const invitadosBody = document.getElementById("invitadosBody");
const invitadosFilterForm = document.getElementById("invitadosFilterForm");
const invitadosSearch = document.getElementById("invitadosSearch");
const selectAllInvitados = document.getElementById("selectAllInvitados");
const invitadosPrevPage = document.getElementById("invitadosPrevPage");
const invitadosNextPage = document.getElementById("invitadosNextPage");
const invitadosPageInfo = document.getElementById("invitadosPageInfo");
const batchScope = document.getElementById("batchScope");
const batchSendBtn = document.getElementById("batchSendBtn");
const batchExportBtn = document.getElementById("batchExportBtn");
const solicitudesCupoBody = document.getElementById("solicitudesCupoBody");
const solicitudesCupoMeta = document.getElementById("solicitudesCupoMeta");
const solicitudesCupoRefresh = document.getElementById("solicitudesCupoRefresh");

const eventoActivoStatus = document.getElementById("eventoActivoStatus");
const closeActiveEventBtn = document.getElementById("closeActiveEventBtn");
const auditBody = document.getElementById("auditBody");
const eventosHistoryBody = document.getElementById("eventosHistoryBody");
const eventosHistMeta = document.getElementById("eventosHistMeta");
const eventosSelectedMeta = document.getElementById("eventosSelectedMeta");
const activateSelectedEventBtn = document.getElementById("activateSelectedEventBtn");
const cloneSelectedEventBtn = document.getElementById("cloneSelectedEventBtn");
const reportesBody = document.getElementById("reportesBody");
const reportExportHint = document.getElementById("reportExportHint");
const reportStatusBanner = document.getElementById("reportStatusBanner");

const eventoActualForm = document.getElementById("eventoActualForm");
const eventoConfigSaveBtn = document.getElementById("eventoConfigSaveBtn");
const nuevoEventoForm = document.getElementById("nuevoEventoForm");
const lectorForm = document.getElementById("lectorForm");
const lectoresFilterForm = document.getElementById("lectoresFilterForm");
const lectoresSearch = document.getElementById("lectoresSearch");
const lectoresBody = document.getElementById("lectoresBody");
const lectoresTotalCount = document.getElementById("lectoresTotalCount");
const lectoresActivosCount = document.getElementById("lectoresActivosCount");
const lectoresOnlineCount = document.getElementById("lectoresOnlineCount");
const lectorAccessQr = document.getElementById("lectorAccessQr");
const lectorQrLink = document.getElementById("lectorQrLink");
const lectorAccessLink = document.getElementById("lectorAccessLink");
const openLectorLinkBtn = document.getElementById("openLectorLinkBtn");
const copyLectorLinkBtn = document.getElementById("copyLectorLinkBtn");
const downloadLectorQrBtn = document.getElementById("downloadLectorQrBtn");
const reportFilterForm = document.getElementById("reportFilterForm");

const rpEntradas = document.getElementById("rpEntradas");
const rpSalidas = document.getElementById("rpSalidas");
const rpAforoTotal = document.getElementById("rpAforoTotal");
const rpAforoUsado = document.getElementById("rpAforoUsado");
const rpDisponible = document.getElementById("rpDisponible");
const rpMovimientos = document.getElementById("rpMovimientos");
const reportExportCsv = document.getElementById("reportExportCsv");
const reportExportPdf = document.getElementById("reportExportPdf");
const MIN_CUPO_TOTAL = 3;
const IMPORT_ALLOWED_EXTENSIONS = [".csv", ".xlsx", ".xls"];

const debugQrsSearch = document.getElementById("debugQrsSearch");
const debugQrsRefreshBtn = document.getElementById("debugQrsRefreshBtn");
const debugQrsLoading = document.getElementById("debugQrsLoading");
const debugQrsGrid = document.getElementById("debugQrsGrid");
let debugQrsState = { items: [], loaded: false };

let adminState = null;
let eventosState = { activeEventId: "", items: [], audit: [] };
let selectedHistoryEventId = "";
let invitadosState = {
  filters: { q: "" },
  page: 1,
  pageSize: 25,
  total: 0,
  totalPages: 1,
  items: [],
  selected: new Set(),
};
let solicitudesCupoState = {
  items: [],
  total: 0,
};
let lectoresState = {
  all: [],
  filtered: [],
  activeByUid: {},
  filters: { q: "" },
};
let lectorPortalLink = "";
let eventoConfigBaseSnapshot = "";
let eventoConfigDirty = false;
let eventoConfigSaving = false;
let eventoConfigEditMode = false;
let reportExportIsFinal = false;

const viewTitles = {
  dashboard: "Panel de Control",
  invitados: "Gestión de Invitados",
  eventos: "Evento Actual",
  "nuevo-evento": "Planeación e Historial",
  lectores: "Lectores",
  "lector-qr": "Lector QR",
  "debug-qrs": "Debug QRs de Estudiantes",
  reportes: "Reportes Operativos",
};

init();

function init() {
  bindUI();
  setupLectorAccess();
  resetNuevoEventoFormDefaults();
  setView("dashboard");
  refreshAll();
  setInterval(refreshAll, 15000);
}

function isMobileViewport() {
  return window.matchMedia("(max-width: 1023px)").matches;
}

function openMobileNav() {
  if (!isMobileViewport()) return;
  adminLayout?.classList.add("mobile-nav-open");
  document.body.classList.add("no-scroll");
}

function closeMobileNav() {
  adminLayout?.classList.remove("mobile-nav-open");
  document.body.classList.remove("no-scroll");
}

function bindUI() {
  mobileMenuToggle?.addEventListener("click", () => openMobileNav());
  mobileMenuClose?.addEventListener("click", () => closeMobileNav());
  sidebarOverlay?.addEventListener("click", () => closeMobileNav());
  window.addEventListener("resize", () => {
    if (!isMobileViewport()) closeMobileNav();
  });

  navMenu?.addEventListener("click", (event) => {
    const link = event.target.closest("[data-view]");
    if (!link) return;
    event.preventDefault();
    const view = link.getAttribute("data-view");
    setView(view);
    closeMobileNav();
  });

  openInviteModalBtn?.addEventListener("click", () => inviteModal.classList.remove("hidden"));
  closeInviteModalBtn?.addEventListener("click", () => inviteModal.classList.add("hidden"));
  closeEditInviteModal?.addEventListener("click", () => editInviteModal.classList.add("hidden"));
  closeEditLectorModal?.addEventListener("click", () => editLectorModal.classList.add("hidden"));
  globalNoticeClose?.addEventListener("click", () => hideGlobalNotice());
  inviteModal?.addEventListener("click", (event) => {
    if (event.target === inviteModal) inviteModal.classList.add("hidden");
  });
  editInviteModal?.addEventListener("click", (event) => {
    if (event.target === editInviteModal) editInviteModal.classList.add("hidden");
  });
  editLectorModal?.addEventListener("click", (event) => {
    if (event.target === editLectorModal) editLectorModal.classList.add("hidden");
  });

  inviteModalForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = formToObject(inviteModalForm);
      payload.invitacion_enviada = !!inviteModalForm.elements.invitacion_enviada.checked;
      payload.cupo_total = MIN_CUPO_TOTAL;
      await api("/api/invitados", { method: "POST", body: payload });
      inviteModal.classList.add("hidden");
      inviteModalForm.reset();
      await refreshInvitados();
      showGlobalNotice("Invitado creado exitosamente.", "success");
    } catch (error) {
      showGlobalNotice(`No se pudo crear invitado: ${error.message}`, "error");
    }
  });

  invitadosFilterForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    invitadosState.filters = {
      q: invitadosSearch?.value || "",
    };
    invitadosState.page = 1;
    await refreshInvitados();
  });

  selectAllInvitados?.addEventListener("change", () => {
    invitadosState.items.forEach((row) => {
      if (selectAllInvitados.checked) invitadosState.selected.add(row.key);
      else invitadosState.selected.delete(row.key);
    });
    renderInvitados(invitadosState.items);
  });

  invitadosPrevPage?.addEventListener("click", async () => {
    if (invitadosState.page <= 1) return;
    invitadosState.page -= 1;
    await refreshInvitados();
  });

  invitadosNextPage?.addEventListener("click", async () => {
    if (invitadosState.page >= invitadosState.totalPages) return;
    invitadosState.page += 1;
    await refreshInvitados();
  });

  invitadosBody?.addEventListener("change", (event) => {
    const row = event.target.closest("tr[data-key]");
    if (!row) return;
    const key = row.getAttribute("data-key");
    if (!key) return;

    if (event.target.matches("input[data-select='row']")) {
      if (event.target.checked) invitadosState.selected.add(key);
      else invitadosState.selected.delete(key);
      syncSelectAllState();
    }
  });

  invitadosBody?.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const key = button.getAttribute("data-key");
    const action = button.getAttribute("data-action");
    if (!key) return;

    if (action === "delete") {
      if (!confirm("¿Eliminar invitado?")) return;
      await api(`/api/invitados/${encodeURIComponent(key)}`, { method: "DELETE" });
      invitadosState.selected.delete(key);
      await refreshInvitados();
      showGlobalNotice("Invitado eliminado.", "success");
      return;
    }

    if (action === "edit") {
      const row = invitadosState.items.find((x) => x.key === key);
      if (!row) return;
      openEditInviteModal(row);
      return;
    }

    if (action === "send-invite") {
      await api("/api/invitados/batch", {
        method: "POST",
        body: { action: "enviar_invitacion", scope: "selected", keys: [key], filters: {} },
      });
      await refreshInvitados();
      showGlobalNotice("Invitación enviada correctamente.", "success");
      return;
    }

    if (action === "download-qr") {
      const row = invitadosState.items.find((x) => x.key === key);
      if (!row) return;
      await downloadInvitadoQr(row);
      return;
    }
  });

  solicitudesCupoRefresh?.addEventListener("click", async () => {
    await refreshSolicitudesCupo();
  });

  batchSendBtn?.addEventListener("click", () => ejecutarBatch("enviar_invitacion"));
  batchExportBtn?.addEventListener("click", () => ejecutarBatch("exportar"));

  eventoActualForm?.addEventListener("input", () => updateEventoConfigDirtyState());
  eventoActualForm?.addEventListener("change", () => updateEventoConfigDirtyState());

  eventoActualForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!eventoConfigEditMode) return;
    await submitEventoActualConfig();
  });
  eventoConfigSaveBtn?.addEventListener("click", async () => {
    if (!eventoActualForm) return;
    const hasActiveEvent = Boolean(String(eventosState.activeEventId || "").trim());
    if (!hasActiveEvent) {
      showGlobalNotice("No hay evento activo. Debes activarlo desde Planeación e Historial.", "error");
      return;
    }
    if (!eventoConfigEditMode) {
      setEventoConfigEditable(true);
      return;
    }
    if (eventoConfigSaving) return;
    await submitEventoActualConfig();
  });

  nuevoEventoForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await api("/api/eventos", { method: "POST", body: formToObject(nuevoEventoForm) });
    nuevoEventoForm.reset();
    resetNuevoEventoFormDefaults();
    await refreshAll();
    showGlobalNotice("Evento de planeación creado con éxito.", "success");
  });

  eventosHistoryBody?.addEventListener("click", (event) => {
    const row = event.target.closest("tr[data-event-id]");
    if (!row) return;
    const eventId = String(row.getAttribute("data-event-id") || "").trim();
    if (!eventId) return;
    selectedHistoryEventId = eventId;
    renderEventosHistory(eventosState.items, eventosState.activeEventId);
  });

  activateSelectedEventBtn?.addEventListener("click", async () => {
    const eventId = String(selectedHistoryEventId || "").trim();
    if (!eventId) return;
    if (!confirm("¿Activar este evento como evento actual?")) return;
    await api(`/api/eventos/${encodeURIComponent(eventId)}/publish`, { method: "POST" });
    await refreshAll();
    showGlobalNotice("Evento publicado como activo.", "success");
  });

  cloneSelectedEventBtn?.addEventListener("click", () => {
    const row = eventosState.items.find((x) => String(x.id_evento || "").trim() === String(selectedHistoryEventId || "").trim());
    if (!row || !nuevoEventoForm) return;
    const baseName = String(row.nombre || "").trim() || "Evento";
    setInput(nuevoEventoForm, "nombre", `${baseName} (copia)`);
    setInput(nuevoEventoForm, "ubicacion", row.ubicacion || "");
    setInput(nuevoEventoForm, "aforo_max", row.aforo_max ?? "");
    const inicioClonado = fromIsoToLocalInput(row.fecha_inicio) || toLocalInputValue(getTomorrowAt(9, 0));
    const finClonado = fromIsoToLocalInput(row.fecha_fin) || toLocalInputValue(getTomorrowAt(11, 0));
    setInput(nuevoEventoForm, "fecha_inicio", inicioClonado);
    setInput(nuevoEventoForm, "fecha_fin", finClonado);
    setInput(nuevoEventoForm, "timezone", row.timezone || "America/Mexico_City");
    if (nuevoEventoForm.elements.nombre) nuevoEventoForm.elements.nombre.focus();
    showGlobalNotice("Evento clonado al formulario. Puedes ajustar y guardar como Listo.", "success");
  });

  closeActiveEventBtn?.addEventListener("click", async () => {
    const activeId = eventosState.activeEventId || "";
    if (!activeId) return;
    if (!confirm("¿Cerrar evento activo? Solo admins con override podrán registrar ingresos.")) return;
    await api(`/api/eventos/${encodeURIComponent(activeId)}/close`, { method: "POST" });
    await refreshAll();
    showGlobalNotice("Evento cerrado.", "success");
  });

  lectorForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const payload = formToObject(lectorForm);
      payload.pin = String(payload.pin || "").replace(/\D/g, "").slice(0, 6);
      payload.activo = !!lectorForm.elements.activo.checked;
      await api("/api/usuarios_staff", { method: "POST", body: payload });
      lectorForm.reset();
      lectorForm.elements.activo.checked = true;
      lectorForm.elements.rol.value = "lector";
      await refreshAll();
      showGlobalNotice("Lector registrado.", "success");
    } catch (error) {
      showGlobalNotice(`No se pudo crear lector: ${error.message}`, "error");
    }
  });

  lectoresFilterForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    lectoresState.filters.q = String(lectoresSearch?.value || "").trim();
    renderLectores();
  });

  lectoresBody?.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-lector-action]");
    if (!button) return;
    const uid = button.getAttribute("data-uid");
    const action = button.getAttribute("data-lector-action");
    if (!uid) return;

    if (action === "delete") {
      if (!confirm("¿Eliminar lector?")) return;
      await api(`/api/usuarios_staff/${encodeURIComponent(uid)}`, { method: "DELETE" });
      await refreshAll();
      showGlobalNotice("Lector eliminado.", "success");
      return;
    }

    if (action === "toggle-active") {
      const row = lectoresState.all.find((x) => x.uid === uid);
      if (!row) return;
      await api(`/api/usuarios_staff/${encodeURIComponent(uid)}`, { method: "PUT", body: { activo: !row.activo } });
      await refreshAll();
      showGlobalNotice("Estado de lector actualizado.", "success");
      return;
    }

    if (action === "reset-pin") {
      if (!confirm("¿Regenerar PIN de este lector?")) return;
      const pin = String(Math.floor(100000 + Math.random() * 900000));
      await api(`/api/usuarios_staff/${encodeURIComponent(uid)}`, { method: "PUT", body: { pin } });
      alert(`PIN actualizado para ${uid}: ${pin}`);
      await refreshAll();
      showGlobalNotice("PIN regenerado correctamente.", "success");
      return;
    }

    if (action === "disconnect") {
      await api(`/api/lectores/${encodeURIComponent(uid)}/disconnect`, { method: "POST" });
      await refreshAll();
      showGlobalNotice("Dispositivo desconectado remotamente.", "success");
      return;
    }

    if (action === "edit") {
      const row = lectoresState.all.find((x) => x.uid === uid);
      if (!row) return;
      openEditLectorModal(row);
    }
  });

  editLectorForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formToObject(editLectorForm);
    payload.pin = String(payload.pin || "").replace(/\D/g, "").slice(0, 6);
    const uid = String(payload.uid || "").trim();
    if (!uid) return;
    payload.activo = !!editLectorForm.elements.activo.checked;
    delete payload.uid;
    await api(`/api/usuarios_staff/${encodeURIComponent(uid)}`, { method: "PUT", body: payload });
    editLectorModal.classList.add("hidden");
    await refreshAll();
    showGlobalNotice("Datos del lector actualizados.", "success");
  });

  openLectorLinkBtn?.addEventListener("click", () => {
    setView("lector-qr");
  });

  copyLectorLinkBtn?.addEventListener("click", async () => {
    if (!lectorPortalLink) return;
    try {
      await navigator.clipboard.writeText(lectorPortalLink);
      alert("Enlace copiado al portapapeles");
    } catch (error) {
      if (lectorAccessLink) {
        lectorAccessLink.focus();
        lectorAccessLink.select();
      }
      alert("No se pudo copiar automáticamente. Copia manualmente el enlace seleccionado.");
    }
  });

  downloadLectorQrBtn?.addEventListener("click", () => {
    const canvas = lectorAccessQr?.querySelector("canvas");
    if (!canvas) return;
    const a = document.createElement("a");
    a.href = canvas.toDataURL("image/png");
    a.download = "siga-portal-lector-qr.png";
    a.click();
  });

  reportExportCsv?.addEventListener("click", () => {
    const params = reportFilterParams();
    params.set("format", "csv");
    window.location.href = `/api/reportes/export?${params.toString()}`;
  });

  reportExportPdf?.addEventListener("click", () => {
    const params = reportFilterParams();
    params.set("format", "pdf");
    window.location.href = `/api/reportes/export?${params.toString()}`;
  });

  selectFileBtn?.addEventListener("click", (event) => {
    event.stopPropagation();
    fileInput?.click();
  });
  uploadZone?.addEventListener("click", () => fileInput?.click());
  uploadZone?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    fileInput?.click();
  });
  ["dragenter", "dragover"].forEach((eventName) => {
    uploadZone?.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      uploadZone.classList.add("is-dragover");
    });
  });
  ["dragleave", "drop"].forEach((eventName) => {
    uploadZone?.addEventListener(eventName, (event) => {
      event.preventDefault();
      event.stopPropagation();
      uploadZone.classList.remove("is-dragover");
    });
  });
  uploadZone?.addEventListener("drop", (event) => {
    const file = event.dataTransfer?.files?.[0];
    if (!file) return;
    void handleImportFile(file);
  });
  fileInput?.addEventListener("change", () => void handleImportFile());

  sendInvitesBtn?.addEventListener("click", () => ejecutarBatch("enviar_invitacion"));

  retrySyncBtn?.addEventListener("click", async () => {
    await fakeButtonProgress(retrySyncBtn, "Sincronizando...", "Sincronizado");
    await api("/api/sync/retry", { method: "POST" });
    await refreshDashboard();
  });

  goReportesBtn?.addEventListener("click", () => setView("reportes"));

  downloadTemplateBtn?.addEventListener("click", () => {
    const csv = "id,nombre,email,invitacion_enviada\n20240001,Juan Perez,juan@example.com,true\n";
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "plantilla_invitados.csv";
    a.click();
    URL.revokeObjectURL(url);
  });

  editInviteForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formToObject(editInviteForm);
    const key = payload.key || "";
    if (!key) return;
    payload.cupo_total = Math.max(Number(payload.cupo_total || MIN_CUPO_TOTAL), MIN_CUPO_TOTAL);
    delete payload.key;
    await api(`/api/invitados/${encodeURIComponent(key)}`, { method: "PUT", body: payload });
    editInviteModal.classList.add("hidden");
    await refreshInvitados();
    showGlobalNotice("Datos actualizados correctamente.", "success");
  });

  debugQrsSearch?.addEventListener("input", (e) => {
    filterDebugQrs(e.target.value.toLowerCase());
  });
  debugQrsRefreshBtn?.addEventListener("click", () => {
    loadDebugQrs(true);
  });
}

async function refreshAll() {
  try {
    const payload = await api("/api/admin_state");
    adminState = payload.data;
    hideGlobalNotice();
    renderEventos(adminState.eventos || [], adminState.evento_activo_id || "");
    prepareLectoresData(adminState.usuarios_staff || [], adminState.dashboard?.lectores?.detalle || []);
    renderLectores();
    renderConfig(adminState.configuracion || {});
    renderReportes(adminState.reportes || {});
    renderReportExportContext();
    await refreshEventosAudit();
    await Promise.all([refreshDashboard(), refreshInvitados(), refreshSolicitudesCupo()]);
  } catch (error) {
    showGlobalNotice(`Error cargando estado: ${error.message}`, "error");
  }
}

function renderReportExportContext() {
  if (!adminState) return;
  const cfgEvento = (adminState.configuracion && adminState.configuracion.evento_actual) || {};
  const cfgId = String(cfgEvento.id_evento || "").trim();
  let estado = String(cfgEvento.estado || "").trim().toLowerCase();
  if (cfgId && Array.isArray(adminState.eventos)) {
    const row = adminState.eventos.find((x) => String(x.id_evento || "").trim() === cfgId);
    if (row && row.estado) estado = String(row.estado).trim().toLowerCase();
  }
  reportExportIsFinal = estado === "cerrado";
  const eventoNombre = String(cfgEvento.nombre || "").trim() || "Evento sin nombre";
  const eventoUbicacion = String(cfgEvento.ubicacion || "").trim();
  const eventoId = String(cfgEvento.id_evento || "").trim();
  const eventoRef = eventoId ? `${eventoNombre} (${eventoId})` : eventoNombre;

  if (reportStatusBanner) {
    reportStatusBanner.classList.remove("hidden", "final", "draft");
    if (reportExportIsFinal) {
      reportStatusBanner.classList.add("final");
      reportStatusBanner.innerHTML = `<strong>Evento cerrado:</strong> ${escapeHtml(eventoRef)}${eventoUbicacion ? ` · ${escapeHtml(eventoUbicacion)}` : ""}. Este reporte es FINAL.`;
    } else {
      reportStatusBanner.classList.add("draft");
      reportStatusBanner.innerHTML = `<strong>Evento en curso:</strong> ${escapeHtml(eventoRef)}${eventoUbicacion ? ` · ${escapeHtml(eventoUbicacion)}` : ""}. Este reporte es un corte al momento.`;
    }
  }

  if (reportExportHint) {
    reportExportHint.textContent = reportExportIsFinal
      ? "Evento cerrado: este reporte se considera final."
      : "Evento en curso: este reporte es un corte al momento.";
  }
  if (reportExportCsv) {
    reportExportCsv.innerHTML = reportExportIsFinal
      ? '<i class="ph-bold ph-file-csv"></i> CSV (Reporte final)'
      : '<i class="ph-bold ph-file-csv"></i> CSV (Corte al momento)';
  }
  if (reportExportPdf) {
    reportExportPdf.innerHTML = reportExportIsFinal
      ? '<i class="ph-bold ph-file-pdf"></i> PDF (Reporte final)'
      : '<i class="ph-bold ph-file-pdf"></i> PDF (Corte al momento)';
  }
}

async function refreshEventosAudit() {
  try {
    const res = await api("/api/eventos/audit");
    eventosState.audit = (res.data && res.data.items) || [];
    renderAudit(eventosState.audit);
  } catch (error) {
    renderAudit([]);
  }
}

async function refreshDashboard() {
  const data = await api("/api/dashboard");
  renderDashboard(data.data || {});
}

async function refreshInvitados() {
  const params = new URLSearchParams();
  params.set("page", String(invitadosState.page));
  params.set("page_size", String(invitadosState.pageSize));
  if (invitadosState.filters.q) params.set("q", invitadosState.filters.q);

  const res = await api(`/api/invitados?${params.toString()}`);
  const paged = res.data || {};
  invitadosState.items = paged.items || [];
  invitadosState.page = Number(paged.page || 1);
  invitadosState.pageSize = Number(paged.page_size || 25);
  invitadosState.total = Number(paged.total || 0);
  invitadosState.totalPages = Number(paged.total_pages || 1);

  renderInvitados(invitadosState.items);
}

async function refreshSolicitudesCupo() {
  try {
    const res = await api("/api/solicitudes_cupo?limit=200");
    const data = res.data || {};
    solicitudesCupoState.items = data.items || [];
    solicitudesCupoState.total = Number(data.total || solicitudesCupoState.items.length || 0);
  } catch (_error) {
    solicitudesCupoState.items = [];
    solicitudesCupoState.total = 0;
  }
  renderSolicitudesCupo(solicitudesCupoState.items);
}

function setView(view) {
  document.querySelectorAll(".nav-item[data-view]").forEach((item) => {
    item.classList.toggle("active", item.getAttribute("data-view") === view);
  });
  document.querySelectorAll(".view-section").forEach((section) => section.classList.add("hidden"));
  document.getElementById(`view-${view}`)?.classList.remove("hidden");

  headerTitle.textContent = viewTitles[view] || "SIGA Admin";
  openInviteModalBtn.classList.toggle("hidden", view !== "invitados");
  if (view === "dashboard") refreshDashboard();
  if (view === "invitados") {
    refreshInvitados();
    refreshSolicitudesCupo();
  }
  if (view === "lectores") renderLectores();
  if (view === "debug-qrs") loadDebugQrs();
  if (isMobileViewport()) closeMobileNav();
}

async function loadDebugQrs(force = false) {
  if (debugQrsState.loaded && !force) return;
  debugQrsLoading.classList.remove("hidden");
  debugQrsGrid.innerHTML = "";
  try {
    const res = await api("/api/invitados?all=true");
    const data = res.data || {};
    debugQrsState.items = data.items || [];
    debugQrsState.loaded = true;
    renderAllDebugQrs();
  } catch (err) {
    debugQrsGrid.innerHTML = `<div class="error" style="grid-column: 1/-1;">Error cargando QRs: ${err.message}</div>`;
  } finally {
    debugQrsLoading.classList.add("hidden");
  }
}

function renderAllDebugQrs() {
  debugQrsGrid.innerHTML = "";
  debugQrsState.items.forEach(invitado => {
    const card = document.createElement("div");
    card.className = "card debug-qr-card align-center";
    card.style.textAlign = "center";
    card.style.padding = "16px";
    card.style.display = "flex";
    card.style.flexDirection = "column";
    card.style.alignItems = "center";
    card.style.gap = "8px";
    card.setAttribute("data-search", `${invitado.id} ${invitado.nombre}`.toLowerCase());

    const qrContainer = document.createElement("div");
    qrContainer.style.background = "#fff";
    qrContainer.style.padding = "8px";
    qrContainer.style.borderRadius = "8px";
    card.appendChild(qrContainer);

    const payload = `${invitado.id}|${invitado.key}`;
    if (typeof QRCode !== "undefined") {
      new QRCode(qrContainer, {
        text: payload,
        width: 140,
        height: 140,
        colorDark: "#000000",
        colorLight: "#ffffff",
        correctLevel: QRCode.CorrectLevel.M
      });
    }

    const nameEl = document.createElement("strong");
    nameEl.textContent = invitado.nombre;
    nameEl.style.fontSize = "14px";
    nameEl.style.marginTop = "4px";
    
    const idEl = document.createElement("small");
    idEl.textContent = `ID: ${invitado.id}`;
    idEl.style.color = "var(--text-secondary)";
    
    card.appendChild(nameEl);
    card.appendChild(idEl);

    debugQrsGrid.appendChild(card);
  });
  
  if (debugQrsSearch) {
    filterDebugQrs(debugQrsSearch.value.toLowerCase());
  }
}

function filterDebugQrs(term) {
  const cards = debugQrsGrid.querySelectorAll(".debug-qr-card");
  cards.forEach(card => {
    const searchData = card.getAttribute("data-search");
    if (!term || searchData.includes(term)) {
      card.style.display = "flex";
    } else {
      card.style.display = "none";
    }
  });
}

function renderDashboard(data) {
  const hasActiveEvent = Boolean(String(eventosState.activeEventId || "").trim());
  const aforoActualRaw = Number(data.aforo_actual || 0);
  const aforoMaximoRaw = Number(data.aforo_maximo || 0);
  const aforoActual = hasActiveEvent ? aforoActualRaw : 0;
  const aforoMaximo = hasActiveEvent ? aforoMaximoRaw : 0;
  const registrados = Number(data.total_invitados_registrados || 0);
  const pendientes = Number(data.invitados_pendientes || 0);
  const syncPendientes = Number(data.sincronizaciones_pendientes || 0);
  const eventoNombre = hasActiveEvent ? String(data.evento_nombre || "").trim() || "Evento activo" : "Sin evento activo";
  const eventoUbicacion = hasActiveEvent ? String(data.evento_ubicacion || "").trim() : "";

  setAforoState(aforoActual, aforoMaximo);
  if (opsEventChip) {
    opsEventChip.textContent = hasActiveEvent ? `Evento activo: ${eventoNombre}` : "Sin evento activo";
  }
  if (opsAforoChip) opsAforoChip.textContent = `Aforo: ${aforoActual} / ${aforoMaximo}`;
  metricRegistrados.textContent = String(registrados);
  metricPendientes.textContent = String(pendientes);
  metricSync.textContent = String(syncPendientes);
  syncCard.classList.remove("hidden");
  metricLastSync.textContent = formatIso(data.ultima_sincronizacion) || "--";
  metricReadersOnline.textContent = String(data.lectores?.online || 0);
  metricReadersLocal.textContent = String(data.lectores?.local || 0);
  metricReadersTotal.textContent = String(data.lectores?.total || 0);
  if (metricReadersBody) {
    const detalle = data.lectores?.detalle || [];
    metricReadersBody.innerHTML = detalle.length
      ? detalle
          .map(
            (r) => `<tr>
        <td>${escapeHtml(r.nombre || r.staff_id || "-")}</td>
        <td>${escapeHtml(r.pin || "-")}</td>
        <td>${escapeHtml(r.modo || "online")}</td>
        <td>${escapeHtml(formatIso(r.timestamp) || r.timestamp || "--")}</td>
      </tr>`
          )
          .join("")
      : '<tr><td colspan="4" class="empty-row">Sin lectores activos</td></tr>';

  }

  subheaderStatus.textContent = data.firebase_ready
    ? `Evento: ${eventoNombre}${eventoUbicacion ? ` · ${eventoUbicacion}` : ""}`
    : "Modo local sin Firebase";

  const ingresos = data.ultimos_ingresos || [];
  ingresosBody.innerHTML = ingresos.length
    ? ingresos
        .map((item) => {
          const fase = item.fase_pdi || "N/D";
          return `<tr>
            <td>${escapeHtml(item.hora || "--:--")}</td>
            <td>${escapeHtml(item.nombre_lider || "N/D")}</td>
            <td>${Number(item.cupo || 0)}</td>
            <td>+${Number(item.entraron || 0)}</td>
            <td><span class="pdi-tag ${getFaseClass(fase)}">${escapeHtml(shortFaseLabel(fase))}</span></td>
          </tr>`;
        })
        .join("")
    : '<tr><td colspan="5" class="empty-row">Sin ingresos registrados aún</td></tr>';
}

function renderInvitados(rows) {
  invitadosBody.innerHTML = rows.length
    ? rows
        .map((x) => {
          const invitacionBadge = x.invitacion_enviada
            ? '<span class="status-badge activo">Enviada</span>'
            : '<span class="status-badge">Pendiente</span>';
          return `<tr data-key="${escapeHtml(x.key)}">
            <td><input data-select="row" type="checkbox" ${invitadosState.selected.has(x.key) ? "checked" : ""} /></td>
            <td>${escapeHtml(x.id)}</td>
            <td>${escapeHtml(x.nombre || "")}</td>
            <td>${escapeHtml(x.email || "")}</td>
            <td>${Number(x.cupo_total || 0)}</td>
            <td>${Number(x.cupo_usado || 0)}</td>
            <td>
              <div class="invitation-cell">
                ${invitacionBadge}
                <button class="btn btn-muted btn-inline" data-action="send-invite" data-key="${escapeHtml(x.key)}">Enviar invitación</button>
              </div>
            </td>
            <td>
              <div class="inline-actions">
                <button class="btn btn-muted btn-inline" data-action="edit" data-key="${escapeHtml(x.key)}">Editar</button>
                <details class="row-menu">
                  <summary aria-label="Más acciones">⋮</summary>
                  <div class="row-menu-items popover-menu">
                    <button class="btn btn-muted" data-action="download-qr" data-key="${escapeHtml(x.key)}">Descargar QR</button>
                    <button class="btn btn-secondary" data-action="delete" data-key="${escapeHtml(x.key)}">Eliminar</button>
                  </div>
                </details>
              </div>
            </td>
          </tr>`;
        })
        .join("")
    : '<tr><td colspan="8" class="empty-row">No hay invitados para los filtros actuales</td></tr>';
  
  invitadosPageInfo.textContent = `Página ${invitadosState.page} de ${invitadosState.totalPages} · ${invitadosState.total} registros`;
  invitadosPrevPage.disabled = invitadosState.page <= 1;
  invitadosNextPage.disabled = invitadosState.page >= invitadosState.totalPages;
  syncSelectAllState();
}

function renderSolicitudesCupo(rows) {
  if (!solicitudesCupoBody) return;
  const items = rows || [];
  solicitudesCupoBody.innerHTML = items.length
    ? items
        .map(
          (x) => `<tr>
      <td>${escapeHtml(formatIso(x.created_at) || x.created_at || "--")}</td>
      <td>${escapeHtml(x.nombre_invitado || x.invitado_id || "")}<br/><small>${escapeHtml(x.invitado_id || "")}</small></td>
      <td>+${Number(x.cantidad_solicitada || 0)}</td>
      <td>+${Number(x.cantidad_aprobada || 0)}</td>
      <td>${Number(x.delta_cupo || 0) > 0 ? `+${Number(x.delta_cupo || 0)}` : String(Number(x.delta_cupo || 0))}</td>
      <td>${Number(x.cupo_total_anterior || 0)} -> ${Number(x.cupo_total_nuevo || x.cupo_total_anterior || 0)}</td>
      <td>${escapeHtml(x.solicitado_desde || "lector")}</td>
      <td><span class="status-badge ${String(x.status || "").toLowerCase() === "aprobada" ? "activo" : "cerrado"}">${escapeHtml(x.status || "-")}</span></td>
    </tr>`
        )
        .join("")
    : '<tr><td colspan="8" class="empty-row">Sin historial de cambios de cupo</td></tr>';

  if (solicitudesCupoMeta) {
    solicitudesCupoMeta.textContent = `Registros: ${items.length}`;
  }
}

function syncSelectAllState() {
  if (!selectAllInvitados) return;
  if (!invitadosState.items.length) {
    selectAllInvitados.checked = false;
    return;
  }
  selectAllInvitados.checked = invitadosState.items.every((x) => invitadosState.selected.has(x.key));
}

async function ejecutarBatch(action) {
  const scope = batchScope?.value || "selected";
  const keys = Array.from(invitadosState.selected);
  const filters = { ...invitadosState.filters };
  try {
    const res = await api("/api/invitados/batch", {
      method: "POST",
      body: { action, scope, keys, filters },
    });

    if (action === "exportar" && res.export_url) {
      window.location.href = res.export_url;
      showGlobalNotice("Exportación iniciada.", "success");
    } else if (action === "enviar_invitacion") {
      showGlobalNotice(`Invitaciones enviadas: ${res.sent || 0}, fallidas: ${res.failed || 0}`, "success");
    }

    await refreshInvitados();
  } catch (error) {
    showGlobalNotice(`No se pudo ejecutar lote: ${error.message}`, "error");
  }
}

function renderEventos(rows, activeEventId = "") {
  eventosState.items = rows || [];
  eventosState.activeEventId = activeEventId || "";
  if (selectedHistoryEventId) {
    const exists = eventosState.items.some((x) => String(x.id_evento || "").trim() === String(selectedHistoryEventId).trim());
    if (!exists) selectedHistoryEventId = "";
  }

  if (eventoActivoStatus) {
    const active = eventosState.items.find((x) => x.id_evento === eventosState.activeEventId);
    if (active) {
      eventoActivoStatus.textContent = `Activo: ${active.nombre} · Ubicación: ${active.ubicacion || "Sin ubicación"} · Aforo: ${Number(active.aforo_max || 0)}`;
    } else {
      eventoActivoStatus.textContent = "Sin evento activo";
    }
  }
  if (closeActiveEventBtn) closeActiveEventBtn.disabled = !eventosState.activeEventId;
  if (!eventosState.activeEventId) setEventoConfigEditable(false);
  renderEventosHistory(eventosState.items, eventosState.activeEventId);
}

function renderEventosHistory(rows, activeEventId = "") {
  if (!eventosHistoryBody) return;
  const items = rows || [];
  const hasSelected = items.some((x) => String(x.id_evento || "").trim() === String(selectedHistoryEventId || "").trim());
  if (!hasSelected) selectedHistoryEventId = "";

  if (activateSelectedEventBtn) {
    activateSelectedEventBtn.disabled = !selectedHistoryEventId;
  }
  if (cloneSelectedEventBtn) {
    cloneSelectedEventBtn.disabled = !selectedHistoryEventId;
  }
  if (eventosSelectedMeta) {
    const selected = items.find((x) => String(x.id_evento || "").trim() === String(selectedHistoryEventId || "").trim());
    eventosSelectedMeta.textContent = selected
      ? `Seleccionado: ${selected.nombre || selected.id_evento}`
      : "Selecciona un evento";
  }

  eventosHistoryBody.innerHTML = items.length
    ? items
        .map((x) => {
          const id = String(x.id_evento || "").trim();
          const estadoRaw = String(x.estado || "borrador").toLowerCase();
          const isActive = id && id === String(activeEventId || "");
          const isSelected = id && id === String(selectedHistoryEventId || "");
          const estadoLabel = isActive ? "Activo" : estadoRaw === "cerrado" ? "Cerrado" : "Listo";
          const estadoClass = isActive ? "activo" : estadoRaw === "cerrado" ? "cerrado" : "";
          return `<tr class="event-history-row ${isSelected ? "is-selected" : ""}" data-event-id="${escapeHtml(id)}">
      <td><input type="radio" name="selectedEventHistory" ${isSelected ? "checked" : ""} aria-label="Seleccionar evento ${escapeHtml(id)}" /></td>
      <td>${escapeHtml(id)}</td>
      <td>${escapeHtml(x.nombre || "")}</td>
      <td>${escapeHtml(x.ubicacion || "")}</td>
      <td>${Number(x.aforo_max || 0)}</td>
      <td>${escapeHtml(formatIso(x.fecha_inicio) || "-")}</td>
      <td>${escapeHtml(formatIso(x.fecha_fin) || "-")}</td>
      <td><span class="status-badge ${estadoClass}">${escapeHtml(isActive ? "Activo" : estadoLabel)}</span></td>
    </tr>`;
        })
        .join("")
    : '<tr><td colspan="8" class="empty-row">Sin eventos registrados</td></tr>';

  if (eventosHistMeta) eventosHistMeta.textContent = `Total: ${items.length}`;
}

function toLocalInputValue(dateObj) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${dateObj.getFullYear()}-${pad(dateObj.getMonth() + 1)}-${pad(dateObj.getDate())}T${pad(dateObj.getHours())}:${pad(dateObj.getMinutes())}`;
}

function getTomorrowAt(hour, minute = 0) {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  date.setHours(hour, minute, 0, 0);
  return date;
}

function resetNuevoEventoFormDefaults() {
  if (!nuevoEventoForm) return;
  setInput(nuevoEventoForm, "timezone", "America/Mexico_City");
  setInput(nuevoEventoForm, "fecha_inicio", toLocalInputValue(getTomorrowAt(9, 0)));
  setInput(nuevoEventoForm, "fecha_fin", toLocalInputValue(getTomorrowAt(11, 0)));
}

function renderAudit(rows) {
  if (!auditBody) return;
  auditBody.innerHTML = rows.length
    ? rows
        .map((x) => {
          const changes = Array.isArray(x.changes) ? x.changes.map((c) => `${c.field}: ${String(c.before)} -> ${String(c.after)}`).join(" | ") : "";
          return `<tr>
            <td>${escapeHtml(formatIso(x.timestamp) || x.timestamp || "")}</td>
            <td>${escapeHtml(x.actor || "")}</td>
            <td>${escapeHtml(x.entidad || "")}</td>
            <td>${escapeHtml(x.accion || "")}</td>
            <td>${escapeHtml(changes || "-")}</td>
          </tr>`;
        })
        .join("")
    : '<tr><td colspan="5" class="empty-row">Sin cambios registrados</td></tr>';
}

function prepareLectoresData(staffRows, activeRows) {
  const activeByUid = {};
  (activeRows || []).forEach((row) => {
    const uid = String(row?.staff_uid || "").trim();
    if (!uid) return;
    const prev = activeByUid[uid];
    if (!prev) {
      activeByUid[uid] = row;
      return;
    }
    const prevTs = new Date(prev.timestamp || 0).getTime();
    const nextTs = new Date(row.timestamp || 0).getTime();
    if (nextTs > prevTs) activeByUid[uid] = row;
  });

  const lectores = (staffRows || []).filter((x) => {
    const rol = String(x?.rol || "").toLowerCase();
    return rol === "lector" || rol === "supervisor" || rol === "admin";
  });

  lectoresState.activeByUid = activeByUid;
  const fromStaff = lectores.map((x) => {
    const onlineInfo = activeByUid[String(x.uid || "").trim()] || null;
    return {
      ...x,
      online: !!onlineInfo,
      onlineInfo,
    };
  });

  const knownUids = new Set(fromStaff.map((x) => String(x.uid || "").trim()).filter(Boolean));
  const syntheticOnline = Object.entries(activeByUid)
    .filter(([uid]) => uid && !knownUids.has(uid))
    .map(([uid, row]) => ({
      uid,
      nombre: String(row?.nombre || uid),
      email: "",
      rol: String(row?.rol || "lector"),
      pin: String(row?.pin || ""),
      activo: true,
      online: true,
      onlineInfo: row,
      synthetic: true,
    }));

  lectoresState.all = [...fromStaff, ...syntheticOnline];
}

function renderLectores() {
  if (!lectoresBody) return;

  const q = String(lectoresState.filters.q || "").toLowerCase();

  const filtered = (lectoresState.all || []).filter((x) => {
    if (q) {
      const hay = [x.nombre, x.email, x.pin].some((v) => String(v || "").toLowerCase().includes(q));
      if (!hay) return false;
    }
    return true;
  });
  lectoresState.filtered = filtered;

  if (lectoresTotalCount) lectoresTotalCount.textContent = String(lectoresState.all.length);
  if (lectoresActivosCount) lectoresActivosCount.textContent = String(lectoresState.all.filter((x) => !!x.activo).length);
  if (lectoresOnlineCount) lectoresOnlineCount.textContent = String(lectoresState.all.filter((x) => !!x.online).length);

  lectoresBody.innerHTML = filtered.length
    ? filtered
        .map((x) => {
          const onlineInfo = x.onlineInfo || {};
          const onlineBadge = x.online
            ? '<span class="status-badge activo">Online</span>'
            : '<span class="status-badge">Offline</span>';
          const activoBadge = x.activo
            ? '<span class="status-badge activo">Sí</span>'
            : '<span class="status-badge cerrado">No</span>';
          const actions = x.synthetic
            ? `<button class="btn btn-muted" data-lector-action="disconnect" data-uid="${escapeHtml(x.uid)}" ${x.online ? "" : "disabled"}>Desconectar sesión</button>`
            : `<button class="btn btn-muted" data-lector-action="edit" data-uid="${escapeHtml(x.uid)}">Editar</button>
            <button class="btn btn-muted" data-lector-action="toggle-active" data-uid="${escapeHtml(x.uid)}">${x.activo ? "Desactivar" : "Activar"}</button>
            <button class="btn btn-muted" data-lector-action="reset-pin" data-uid="${escapeHtml(x.uid)}">Reset PIN</button>
            <button class="btn btn-muted" data-lector-action="disconnect" data-uid="${escapeHtml(x.uid)}" ${x.online ? "" : "disabled"}>Desconectar sesión</button>
            <button class="btn btn-secondary" data-lector-action="delete" data-uid="${escapeHtml(x.uid)}">Eliminar</button>`;
          return `<tr>
      <td>${escapeHtml(x.nombre || "")}</td>
      <td>${escapeHtml(x.email || "")}</td>
      <td>${escapeHtml(x.rol || "lector")}</td>
      <td>${escapeHtml(x.pin || "")}</td>
      <td>${activoBadge}</td>
      <td>${onlineBadge}</td>
      <td>${escapeHtml(formatIso(onlineInfo.timestamp) || "--")}</td>
      <td>
        <details class="row-menu">
          <summary aria-label="Más acciones">⋮</summary>
          <div class="row-menu-items">
            ${actions}
          </div>
        </details>
      </td>
    </tr>`;
        })
        .join("")
    : '<tr><td colspan="8" class="empty-row">Sin lectores para los filtros actuales</td></tr>';
}

function openEditLectorModal(row) {
  if (!editLectorForm || !editLectorModal) return;
  editLectorForm.elements.uid.value = row.uid || "";
  editLectorForm.elements.nombre.value = row.nombre || "";
  editLectorForm.elements.email.value = row.email || "";
  editLectorForm.elements.pin.value = row.pin || "";
  editLectorForm.elements.rol.value = row.rol || "lector";
  editLectorForm.elements.activo.checked = !!row.activo;
  editLectorModal.classList.remove("hidden");
}

function setupLectorAccess() {
  lectorPortalLink = `${window.location.origin}/lector`;
  if (lectorAccessLink) lectorAccessLink.value = lectorPortalLink;
  if (lectorQrLink) lectorQrLink.href = lectorPortalLink;
  if (!lectorAccessQr) return;

  lectorAccessQr.innerHTML = "";
  if (typeof QRCode !== "undefined") {
    new QRCode(lectorAccessQr, {
      text: lectorPortalLink,
      width: 200,
      height: 200,
      colorDark: "#111827",
      colorLight: "#ffffff",
      correctLevel: QRCode.CorrectLevel.H,
    });
    return;
  }

  lectorAccessQr.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:200px;text-align:center;color:#64748b;font-size:13px;padding:8px;">No se pudo generar QR.<br/>Usa el enlace directo.</div>`;
}

function openEditInviteModal(row) {
  if (!editInviteForm || !editInviteModal) return;
  editInviteForm.elements.key.value = row.key || "";
  editInviteForm.elements.nombre.value = row.nombre || "";
  editInviteForm.elements.email.value = row.email || "";
  editInviteForm.elements.id.value = row.id || "";
  editInviteForm.elements.cupo_total.value = Math.max(Number(row.cupo_total || MIN_CUPO_TOTAL), MIN_CUPO_TOTAL);
  editInviteModal.classList.remove("hidden");
}

let globalNoticeTimer = null;
function showGlobalNotice(message, level = "info") {
  if (!globalNotice || !globalNoticeText) return;
  clearTimeout(globalNoticeTimer);
  globalNotice.classList.remove("hidden", "info", "error", "success");
  globalNotice.classList.add(level);
  globalNoticeText.textContent = message;
  
  if (level === "success") {
    globalNoticeTimer = setTimeout(hideGlobalNotice, 4000);
  }
}

function hideGlobalNotice() {
  if (!globalNotice) return;
  globalNotice.classList.add("hidden");
}

function serializeEventoConfigForm() {
  if (!eventoActualForm) return "";
  const raw = formToObject(eventoActualForm);
  const normalized = {
    id_evento: String(raw.id_evento || "").trim(),
    nombre: String(raw.nombre || "").trim(),
    ubicacion: String(raw.ubicacion || "").trim(),
    aforo_max: String(raw.aforo_max || "").trim(),
    fecha_inicio: String(raw.fecha_inicio || "").trim(),
    fecha_fin: String(raw.fecha_fin || "").trim(),
    timezone: String(raw.timezone || "").trim(),
  };
  return JSON.stringify(normalized);
}

function updateEventoConfigDirtyState() {
  const current = serializeEventoConfigForm();
  eventoConfigDirty = Boolean(current && eventoConfigBaseSnapshot && current !== eventoConfigBaseSnapshot);
  if (!eventoConfigSaveBtn || !eventoActualForm) return;
  const hasActiveEvent = Boolean(String(eventosState.activeEventId || "").trim());
  if (!hasActiveEvent) {
    eventoConfigSaveBtn.textContent = "No hay evento";
    eventoConfigSaveBtn.disabled = true;
    return;
  }
  if (!eventoConfigEditMode) {
    eventoConfigSaveBtn.textContent = "Modificar Configuración";
    eventoConfigSaveBtn.disabled = eventoConfigSaving;
    return;
  }
  eventoConfigSaveBtn.textContent = "Guardar Configuración";
  eventoConfigSaveBtn.disabled = eventoConfigSaving;
}

function captureEventoConfigBaseSnapshot() {
  eventoConfigBaseSnapshot = serializeEventoConfigForm();
  eventoConfigDirty = false;
  updateEventoConfigDirtyState();
}

function clearEventoConfigForm() {
  if (!eventoActualForm) return;
  setInput(eventoActualForm, "id_evento", "");
  setInput(eventoActualForm, "nombre", "");
  setInput(eventoActualForm, "ubicacion", "");
  setInput(eventoActualForm, "aforo_max", "");
  setInput(eventoActualForm, "fecha_inicio", "");
  setInput(eventoActualForm, "fecha_fin", "");
  setInput(eventoActualForm, "timezone", "America/Mexico_City");
}

function setEventoConfigEditable(enabled) {
  eventoConfigEditMode = !!enabled;
  if (!eventoActualForm) return;
  for (const field of Array.from(eventoActualForm.elements || [])) {
    if (!field || field === eventoConfigSaveBtn) continue;
    if (field.name === "id_evento" || field.type === "hidden") continue;
    field.disabled = !eventoConfigEditMode;
  }
  updateEventoConfigDirtyState();
}

async function submitEventoActualConfig() {
  if (!eventoActualForm) return;
  const payload = formToObject(eventoActualForm);
  eventoConfigSaving = true;
  updateEventoConfigDirtyState();
  try {
    await api("/api/configuracion/evento_actual", { method: "PUT", body: payload });
    await refreshAll();
    setEventoConfigEditable(false);
    showGlobalNotice("Configuración del evento guardada adecuadamente.", "success");
  } catch (error) {
    showGlobalNotice(`No se pudo guardar configuración: ${error.message}`, "error");
  } finally {
    eventoConfigSaving = false;
    updateEventoConfigDirtyState();
  }
}

function renderConfig(config) {
  const evento = config.evento_actual || {};
  if (!eventoActualForm) return;
  const hasActiveEvent = Boolean(String(eventosState.activeEventId || "").trim());
  if (!hasActiveEvent) {
    setEventoConfigEditable(false);
    clearEventoConfigForm();
    captureEventoConfigBaseSnapshot();
    return;
  }
  if (eventoConfigDirty && !eventoConfigSaving) {
    updateEventoConfigDirtyState();
    return;
  }
  setInput(eventoActualForm, "id_evento", evento.id_evento || "");
  setInput(eventoActualForm, "nombre", evento.nombre || "");
  setInput(eventoActualForm, "ubicacion", evento.ubicacion || "");
  setInput(eventoActualForm, "aforo_max", evento.aforo_max ?? "");
  setInput(eventoActualForm, "fecha_inicio", fromIsoToLocalInput(evento.fecha_inicio));
  setInput(eventoActualForm, "fecha_fin", fromIsoToLocalInput(evento.fecha_fin));
  setInput(eventoActualForm, "estado", evento.estado || "borrador");
  setInput(eventoActualForm, "timezone", evento.timezone || "America/Mexico_City");
  captureEventoConfigBaseSnapshot();
}

function renderReportes(data) {
  const resumen = data.resumen || {};
  rpEntradas.textContent = String(resumen.entradas_total || 0);
  rpSalidas.textContent = String(resumen.salidas_total || 0);
  rpAforoTotal.textContent = String(resumen.aforo_total || 0);
  rpAforoUsado.textContent = String(resumen.aforo_utilizado || 0);
  rpDisponible.textContent = String(resumen.capacidad_disponible || 0);
  rpMovimientos.textContent = String(resumen.movimientos_total || 0);

  const rows = data.movimientos || [];
  reportesBody.innerHTML = rows.length
    ? rows
        .map(
          (x) => `<tr>
      <td>${escapeHtml(x.hora || x.timestamp || "")}</td>
      <td>${escapeHtml(x.tipo || "")}</td>
      <td>${Number(x.cantidad || 0)}</td>
      <td>${escapeHtml(x.nombre_invitado || "")}</td>
      <td>${renderModoBadge(x.modo || "")}</td>
    </tr>`
        )
        .join("")
    : '<tr><td colspan="5" class="empty-row">Sin movimientos para el rango seleccionado</td></tr>';
}

function renderModoBadge(modo) {
  const raw = String(modo || "").toLowerCase();
  const isNube = raw.includes("nube");
  const cls = isNube ? "nube" : "local";
  const label = isNube ? "Nube" : "Local";
  return `<span class="mode-badge ${cls}">${escapeHtml(label)}</span>`;
}

function reportFilterParams() {
  if (!reportFilterForm) return new URLSearchParams();
  const payload = formToObject(reportFilterForm);
  const params = new URLSearchParams();
  if (payload.desde) params.set("desde", toIsoFromLocal(payload.desde));
  if (payload.hasta) params.set("hasta", toIsoFromLocal(payload.hasta));
  return params;
}

function isAllowedImportFile(file) {
  const name = String(file?.name || "").toLowerCase();
  return IMPORT_ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext));
}

async function handleImportFile(fileOverride = null) {
  const selectedFile = fileOverride || fileInput?.files?.[0];
  if (!selectedFile) return;
  if (!isAllowedImportFile(selectedFile)) {
    uploadProgressWrapper.classList.remove("hidden");
    uploadProgress.style.width = "100%";
    uploadStatus.textContent = "Archivo no soportado. Usa CSV o XLSX.";
    if (fileInput) fileInput.value = "";
    return;
  }

  const form = new FormData();
  form.append("file", selectedFile);

  uploadProgressWrapper.classList.remove("hidden");
  uploadProgress.style.width = "30%";
  uploadStatus.textContent = "Subiendo archivo...";
  uploadZone?.classList.add("is-uploading");

  try {
    const res = await fetch("/api/invitados/import", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok || data.ok === false) {
      throw new Error(data.error?.message || data.error || `HTTP ${res.status}`);
    }

    uploadProgress.style.width = "100%";
    const s = data.summary || {};
    uploadStatus.textContent = `Importación: insertados ${s.inserted || 0}, duplicados ${s.duplicated || 0}, inválidos ${s.invalid || 0}`;

    if (data.error_report_csv) {
      const blob = new Blob([data.error_report_csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "invitados_import_errores.csv";
      a.click();
      URL.revokeObjectURL(url);
    }

    await refreshInvitados();
  } catch (error) {
    uploadProgress.style.width = "100%";
    uploadStatus.textContent = `Error importando: ${error.message}`;
  } finally {
    uploadZone?.classList.remove("is-uploading");
    if (fileInput) fileInput.value = "";
  }
}

function setAforoState(actual, maximo) {
  const safeMax = Math.max(Number(maximo) || 0, 0);
  const safeActual = Math.max(Number(actual) || 0, 0);
  const pct = safeMax > 0 ? Math.round((safeActual / safeMax) * 100) : 0;
  aforoValue.textContent = `${safeActual} / ${safeMax}`;
  aforoProgress.style.width = `${Math.min(pct, 100)}%`;
  aforoCard.classList.remove("aforo-ok", "aforo-warning", "aforo-critical", "aforo-full");

  let levelClass = "aforo-ok";
  let levelLabel = "Nivel: Normal";
  if (pct >= 100) {
    levelClass = "aforo-full";
    levelLabel = "Nivel: Lleno";
  } else if (pct >= 90) {
    levelClass = "aforo-critical";
    levelLabel = "Nivel: Crítico";
  } else if (pct >= 75) {
    levelClass = "aforo-warning";
    levelLabel = "Nivel: Alerta";
  }
  aforoCard.classList.add(levelClass);
  if (aforoLevelText) aforoLevelText.textContent = `${levelLabel} (${pct}%)`;
}

async function downloadInvitadoQr(invitado) {
  const invitadoId = String(invitado?.id || "").trim();
  const invitadoKey = String(invitado?.key || "").trim();
  if (!invitadoId || !invitadoKey) {
    showGlobalNotice("No se pudo descargar el QR: faltan datos del invitado.", "error");
    return;
  }
  if (typeof QRCode === "undefined") {
    showGlobalNotice("No se pudo generar el QR en este navegador.", "error");
    return;
  }

  const payload = `${invitadoId}|${invitadoKey}`;
  const holder = document.createElement("div");
  holder.style.position = "fixed";
  holder.style.left = "-9999px";
  holder.style.top = "-9999px";
  document.body.appendChild(holder);

  try {
    new QRCode(holder, {
      text: payload,
      width: 512,
      height: 512,
      colorDark: "#111827",
      colorLight: "#ffffff",
      correctLevel: QRCode.CorrectLevel.H,
    });

    await delay(0);

    const canvas = holder.querySelector("canvas");
    const img = holder.querySelector("img");
    const href = canvas?.toDataURL("image/png") || img?.src || "";
    if (!href) {
      showGlobalNotice("No se pudo generar el archivo del QR.", "error");
      return;
    }

    const safeId = invitadoId.replace(/[^a-zA-Z0-9_-]/g, "_");
    const a = document.createElement("a");
    a.href = href;
    a.download = `siga-invitado-${safeId}-qr.png`;
    a.click();
    showGlobalNotice("QR descargado correctamente.", "success");
  } catch (error) {
    showGlobalNotice(`No se pudo descargar el QR: ${error.message}`, "error");
  } finally {
    holder.remove();
  }
}

async function api(url, options = {}) {
  const config = { method: options.method || "GET", headers: { "Content-Type": "application/json" } };
  if (options.body) config.body = JSON.stringify(options.body);
  const res = await fetch(url, config);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || data.ok === false) {
    const err = data.error?.message || data.error || `HTTP ${res.status}`;
    throw new Error(err);
  }
  return data;
}

async function fakeButtonProgress(button, loadingText, doneText) {
  button.disabled = true;
  const original = button.textContent;
  button.textContent = loadingText;
  await delay(600);
  button.textContent = doneText;
  await delay(400);
  button.textContent = original;
  button.disabled = false;
}

function formToObject(form) {
  const fd = new FormData(form);
  const out = {};
  for (const [k, v] of fd.entries()) out[k] = v;
  return out;
}

function setInput(form, name, value) {
  if (form.elements[name]) form.elements[name].value = value ?? "";
}

function toIsoFromLocal(localValue) {
  if (!localValue) return "";
  return new Date(localValue).toISOString();
}

function fromIsoToLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function formatIso(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString();
}

function shortFaseLabel(fase) {
  if (fase.includes("Fase 1")) return "Gris";
  if (fase.includes("Fase 2")) return "Fijo";
  if (fase.includes("Fase 3")) return "Adaptativo";
  return fase;
}

function getFaseClass(fase) {
  const f = String(fase || "").toLowerCase();
  if (f.includes("fase 1") || f.includes("gris")) return "pdi-gris";
  if (f.includes("fase 2") || f.includes("fijo")) return "pdi-fijo";
  if (f.includes("fase 3") || f.includes("adaptativo")) return "pdi-adaptativo";
  return "pdi-gris";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
