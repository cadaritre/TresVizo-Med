// Comportamiento de Med. Sin código en línea (CSP). Se carga con «defer», después de htmx y de la base del portal.
(function () {
  "use strict";

  // Respuestas 409/422 (conflicto, validación) también se muestran: son parte del flujo, no errores de red.
  if (window.htmx) {
    htmx.config.responseHandling = [
      { code: "204", swap: false },
      { code: "[23]..", swap: true },
      { code: "409|422", swap: true, error: false },
      { code: "[45]..", swap: false, error: true },
      { code: "...", swap: false }
    ];
    // Sin espera entre insertar y «settle»: el contenido nuevo queda activo (sus formularios envían por HTMX) de inmediato. Med no
    // usa las transiciones de clase que justifican esa espera.
    htmx.config.defaultSettleDelay = 0;
  }

  // Foco tras un intercambio de HTMX (panel de captura, errores de validación). htmx enfoca los [autofocus] en la fase «settle»,
  // un temporizador DESPUÉS de insertar: si mientras tanto la persona ya pasó a otro campo y escribe, el foco salta y lo que
  // teclea cae en el campo equivocado (así «8» de la frecuencia terminó en el nombre: «Paracetamol8»). Aquí el foco se da en el
  // mismo instante en que llega el contenido, antes de cualquier tecla, y nunca se mueve si ya se está escribiendo en un campo.
  function escribiendo() {
    var a = document.activeElement;
    return !!(a && a !== document.body && document.contains(a) && a.matches("input:not([type=button]):not([type=submit]), textarea, select, [contenteditable]"));
  }
  function campoDeTexto(a) {
    return !!(a && a.matches && a.matches("input:not([type=button]):not([type=submit]), textarea, select, [contenteditable]"));
  }
  function seleccion(a) {
    try { return typeof a.selectionStart === "number" ? [a.selectionStart, a.selectionEnd] : null; } catch (err) { return null; }
  }
  // beforeSwap guarda dónde se escribía (con el elemento aún en la página); afterSwap llega justo después de insertar el contenido,
  // en la misma tarea y antes de cualquier tecla o temporizador (incluido el «settle» de htmx).
  var antesDelIntercambio = null;
  document.addEventListener("htmx:beforeSwap", function (e) {
    var previo = document.activeElement;
    antesDelIntercambio = { previo: previo, id: previo && previo.id, rango: campoDeTexto(previo) ? seleccion(previo) : null,
                            fondo: !!(e.detail.xhr && e.detail.xhr.getResponseHeader("HX-Reswap") === "none") };
  });
  document.addEventListener("htmx:afterSwap", function (e) {
    var raiz = e.detail.target || e.target, antes = antesDelIntercambio || {};  // vale para todos los afterSwap de esa respuesta
    if (!raiz || !raiz.querySelectorAll) return;
    raiz.querySelectorAll("[autofocus]").forEach(function (x) { x.removeAttribute("autofocus"); x.setAttribute("data-autofoco", ""); });
    if (antes.fondo) return;  // guardado de fondo: no toca el foco
    // Se escribía en un campo que sigue en la página (o en el mismo campo vuelto a pintar): el foco y el cursor se quedan ahí.
    var previo = antes.previo;
    var mismo = campoDeTexto(previo) ? (previo.isConnected ? previo : (antes.id && document.getElementById(antes.id))) : null;
    if (mismo) {
      if (document.activeElement !== mismo) mismo.focus({ preventScroll: true });
      if (antes.rango) { try { mismo.setSelectionRange(antes.rango[0], antes.rango[1]); } catch (err) { /* tipos sin selección */ } }
      return;
    }
    if (escribiendo()) return;
    var destino = raiz.querySelector('[aria-invalid="true"]') || raiz.querySelector("[data-autofoco]");
    if (!destino) return;
    destino.focus();
    if (/^(text|search|tel|email)$/.test(destino.type)) { var n = destino.value.length; try { destino.setSelectionRange(n, n); } catch (err) { /* sin selección */ } }
  });

  function indicador() { return document.getElementById("indicador"); }
  function avisar(texto, error) {
    var el = indicador();
    if (!el) return;
    el.textContent = texto;
    el.classList.toggle("med-indicador--error", !!error);
  }

  // Preferencia del perfil: reducir el movimiento (también se respeta la del sistema operativo con prefers-reduced-motion).
  document.addEventListener("DOMContentLoaded", function () {
    if (document.querySelector("[data-reducir-movimiento]")) document.documentElement.classList.add("med-sin-movimiento");
  });

  // Estadísticas: si cambian los filtros, el resultado mostrado ya no corresponde a ellos y no se puede exportar.
  document.addEventListener("input", function (e) {
    if (e.target.closest && e.target.closest("form[data-estadisticas]")) {
      var resultado = document.querySelector(".med-resultado");
      if (resultado) resultado.setAttribute("data-obsoleto", "");
    }
  });

  // htmx guarda la ruta actual en sessionStorage; Med no guarda nada en el dispositivo, así que se borra.
  function sinAlmacenamiento() { try { sessionStorage.clear(); } catch (e) { /* sin acceso: nada que borrar */ } }
  document.addEventListener("DOMContentLoaded", sinAlmacenamiento);
  document.addEventListener("htmx:afterSettle", sinAlmacenamiento);
  window.addEventListener("pagehide", sinAlmacenamiento);

  // Sin señal: Med no guarda nada en el dispositivo (sin service worker ni almacenamiento local); solo avisa.
  function red() {
    var aviso = document.getElementById("sin-conexion");
    if (aviso) aviso.hidden = navigator.onLine !== false;
  }
  window.addEventListener("offline", red);
  window.addEventListener("online", red);
  document.addEventListener("DOMContentLoaded", red);

  // Indicador «Guardado» real: si la red o el servidor fallan, lo dice.
  document.addEventListener("htmx:sendError", function () { avisar("No se pudo guardar: sin conexión. Se reintentará al seguir escribiendo.", true); });
  document.addEventListener("htmx:responseError", function (e) {
    if (e.detail.xhr && e.detail.xhr.status !== 401) avisar("No se pudo guardar (error " + e.detail.xhr.status + "). Copia tu texto antes de salir.", true);
  });

  // La captura lateral se guarda como pendiente mientras se escribe; «Aplicar» y «Descartar» son explícitos.
  document.addEventListener("htmx:configRequest", function (e) {
    var form = e.detail.elt;
    if (form && form.id === "captura" && e.detail.triggeringEvent && e.detail.triggeringEvent.type === "input") {
      e.detail.parameters["accion"] = "pendiente";
    }
  });

  // Autoguardado: además de los 900 ms sin teclear, nunca pasan más de 5 s con cambios sin guardar.
  var pendientes = new WeakMap();
  document.addEventListener("input", function (e) {
    var form = e.target.closest && e.target.closest("form[data-autoguardar]");
    if (!form || pendientes.has(form)) return;
    pendientes.set(form, window.setTimeout(function () {
      pendientes.delete(form);
      if (window.htmx) htmx.trigger(form, "guardar");
    }, 5000));
  });
  document.addEventListener("htmx:afterRequest", function (e) {
    var form = e.detail.elt;
    var t = pendientes.get(form);
    if (t) { window.clearTimeout(t); pendientes.delete(form); }
  });

  // Al terminar un PDF se abre su vista previa sin un clic de más (el enlace queda como respaldo).
  function abrirResultado(raiz) {
    var contenedor = raiz.closest ? raiz.closest("[data-abrir-al-terminar]") : null;
    var ok = contenedor && contenedor.querySelector('.tv-progreso[data-estado="completada"] a[href]');
    if (ok && !contenedor.dataset.abierto) { contenedor.dataset.abierto = "1"; window.location.assign(ok.getAttribute("href")); }
  }
  document.addEventListener("htmx:afterSwap", function (e) { abrirResultado(e.target); });
  document.addEventListener("htmx:afterSettle", function (e) { abrirResultado(e.target); });

  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-volver]")) { e.preventDefault(); if (history.length > 1) history.back(); else window.location.assign("/"); }
  });

  // Paquete del expediente: marcar todos o ninguno y tamaño total de los documentos elegidos.
  function totalPaquete(caja) {
    var bytes = 0, n = 0;
    caja.querySelectorAll("input[type=checkbox][data-tamano]").forEach(function (c) { if (c.checked) { bytes += Number(c.dataset.tamano) || 0; n += 1; } });
    var mb = bytes >= 1048576 ? (bytes / 1048576).toFixed(1).replace(".", ",") + " MB" : Math.max(1, Math.round(bytes / 1024)) + " KB";
    var salida = caja.querySelector("[data-total]");
    if (salida) salida.textContent = n ? n + " documento" + (n === 1 ? "" : "s") + " · " + (bytes ? mb : "0 KB") + " (sin contar los datos)" : "Ningún documento elegido";
  }
  document.querySelectorAll("[data-paquete]").forEach(totalPaquete);
  document.addEventListener("click", function (e) {
    var b = e.target.closest("[data-marcar]");
    if (!b) return;
    var caja = b.closest("[data-paquete]");
    caja.querySelectorAll("input[type=checkbox][data-tamano]").forEach(function (c) { c.checked = b.dataset.marcar === "todo"; });
    totalPaquete(caja);
  });
  document.addEventListener("change", function (e) { var caja = e.target.closest && e.target.closest("[data-paquete]"); if (caja) totalPaquete(caja); });

  // Sección plegada de la consulta: su primera línea se actualiza al escribir para que, plegada, no parezca vacía.
  document.addEventListener("input", function (e) {
    var area = e.target.closest(".med-colapsable textarea");
    if (!area) return;
    var vista = area.closest(".med-colapsable").querySelector("[data-vista-de]");
    if (!vista) return;
    var linea = area.value.split("\n").map(function (x) { return x.trim(); }).filter(Boolean)[0] || "";
    vista.textContent = linea.length > 110 ? linea.slice(0, 109).trim() + "…" : linea;
  });

  // Quitar una fila de una colección repetible.
  document.addEventListener("click", function (e) {
    var quitar = e.target.closest("[data-quitar-fila]");
    if (quitar) {
      var fila = quitar.closest("[data-fila]");
      var form = quitar.closest("form");
      if (fila) fila.remove();
      if (form && window.htmx) htmx.trigger(form, "guardar");
    }
    if (e.target.closest("[data-cerrar-panel]")) {
      var panel = document.getElementById("panel");
      if (panel) panel.replaceChildren();
    }
  });

  document.addEventListener("keydown", function (e) {
    var soap = document.getElementById("soap");
    // Ctrl+S guarda; Ctrl+Enter abre «Revisar y finalizar».
    if (soap && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      if (window.htmx) htmx.trigger(soap, "guardar");
    }
    if (soap && (e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      var boton = document.getElementById("boton-revisar");
      if (boton) boton.click();
    }
    // Buscador: Ctrl+K enfoca; flecha abajo baja a los resultados; Enter abre el seleccionado.
    var buscador = document.querySelector("[data-atajo-buscar]");
    if (buscador && e.key === "ArrowDown" && document.activeElement === buscador) {
      var primero = document.querySelector("[data-resultado]");
      if (primero) { e.preventDefault(); primero.focus(); }
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      var actual = document.activeElement;
      if (actual && actual.hasAttribute && actual.hasAttribute("data-resultado")) {
        var enlaces = Array.prototype.slice.call(document.querySelectorAll("[data-resultado]"));
        var i = enlaces.indexOf(actual) + (e.key === "ArrowDown" ? 1 : -1);
        if (i >= 0 && i < enlaces.length) { e.preventDefault(); enlaces[i].focus(); }
        else if (i < 0 && buscador) { e.preventDefault(); buscador.focus(); }
      }
    }
  });

  // Una subida terminada pasa a la cola de su destino (el contrato de subidas no lleva el expediente en los metadatos).
  document.addEventListener("tv-subida:listo", function (e) {
    var zona = e.target.closest && e.target.closest("[data-asociar]");
    var id = e.detail && e.detail.resultado && e.detail.resultado.subido_id;
    if (!zona || !id || !window.htmx) return;
    htmx.ajax("POST", zona.dataset.asociar, { target: "#cola-docs", swap: "outerHTML", values: { subido: id, reemplaza: zona.dataset.reemplaza || "" } });
  });

  // «Revisar y finalizar» vuelve a abrir la captura que falta (?abrir=…).
  document.addEventListener("DOMContentLoaded", function () {
    var editor = document.getElementById("editor");
    var url = editor && editor.getAttribute("data-abrir-url");
    if (url && window.htmx) htmx.ajax("GET", url, { target: "#panel" });
  });
})();
