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
  }

  function indicador() { return document.getElementById("indicador"); }
  function avisar(texto, error) {
    var el = indicador();
    if (!el) return;
    el.textContent = texto;
    el.classList.toggle("med-indicador--error", !!error);
  }

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
    if (buscador && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); buscador.focus(); buscador.select(); }
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

  // «Revisar y finalizar» vuelve a abrir la captura que falta (?abrir=…).
  document.addEventListener("DOMContentLoaded", function () {
    var editor = document.getElementById("editor");
    var url = editor && editor.getAttribute("data-abrir-url");
    if (url && window.htmx) htmx.ajax("GET", url, { target: "#panel" });
  });
})();
