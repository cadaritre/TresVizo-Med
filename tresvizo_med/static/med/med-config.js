// Configuración de Med: editor de colores con vista previa y recorte de la foto de perfil. Sin estilos en línea (solo CSSOM).
(function () {
  "use strict";

  // Editor de tema: el selector de color y el campo hexadecimal van juntos, y la vista previa usa los mismos tokens.
  var VARIABLES = { primary: "--tv-primario", accent: "--tv-acento", background: "--tv-fondo", surface: "--tv-superficie", header: "--tv-cabecera",
    sidebar: "--tv-lateral", text: "--tv-texto", muted: "--tv-tenue", border: "--tv-borde", button: "--tv-boton", secondary: "--tv-secundario",
    selection: "--tv-seleccion", focus: "--tv-foco" };
  document.querySelectorAll(".med-muestra").forEach(function (m) { m.style.background = m.dataset.color; });
  // Vista previa de cada tema en su tarjeta: los colores del tema van como variables solo dentro de la miniatura.
  document.querySelectorAll(".med-vista").forEach(function (v) {
    Object.keys(VARIABLES).forEach(function (k) { if (v.dataset[k]) v.style.setProperty(VARIABLES[k], v.dataset[k]); });
  });
  var editor = document.querySelector("[data-editor-tema]");
  if (editor) {
    var previa = editor.querySelector("[data-vista-previa]");
    function pintar() {
      editor.querySelectorAll("input[type=color][data-token]").forEach(function (c) {
        var v = VARIABLES[c.dataset.token];
        if (v) previa.style.setProperty(v, c.value);
      });
      previa.style.background = getComputedStyle(previa).getPropertyValue("--tv-superficie");
    }
    editor.addEventListener("input", function (e) {
      var t = e.target;
      if (t.matches("input[type=color]")) { var h = editor.querySelector('[data-hex-de="' + t.id + '"]'); if (h) h.value = t.value.toUpperCase(); }
      if (t.matches("[data-hex-de]") && /^#[0-9a-fA-F]{6}$/.test(t.value)) { document.getElementById(t.dataset.hexDe).value = t.value; }
      pintar();
    });
    pintar();
    editor.scrollIntoView({ block: "start" });
  }

  // Recorte de la foto de perfil: arrastrar para encuadrar y zoom; el resultado es un PNG cuadrado de 256 px.
  document.querySelectorAll("[data-recorte]").forEach(function (raiz) {
    var origen = raiz.querySelector("[data-recorte-origen]");
    var contenedor = raiz.querySelector("[data-recorte-editor]");
    var lienzo = raiz.querySelector("[data-recorte-lienzo]");
    var zoom = raiz.querySelector("[data-recorte-zoom]");
    var resultado = raiz.querySelector("[data-recorte-resultado]");
    var form = raiz.closest("form");
    var imagen = null, x = 0, y = 0, arrastre = null;
    var ctx = lienzo.getContext("2d");
    function base() { return Math.max(lienzo.width / imagen.width, lienzo.height / imagen.height); }
    function limitar() {
      var w = imagen.width * base() * Number(zoom.value), h = imagen.height * base() * Number(zoom.value);
      x = Math.min(0, Math.max(lienzo.width - w, x)); y = Math.min(0, Math.max(lienzo.height - h, y));
    }
    function dibujar() {
      limitar();
      var e = base() * Number(zoom.value);
      ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, lienzo.width, lienzo.height);
      ctx.drawImage(imagen, x, y, imagen.width * e, imagen.height * e);
    }
    origen.addEventListener("change", function () {
      var archivo = origen.files[0];
      if (!archivo) return;
      var img = new Image();
      img.onload = function () { imagen = img; zoom.value = 1; x = 0; y = 0; contenedor.hidden = false; dibujar(); URL.revokeObjectURL(img.src); };
      img.src = URL.createObjectURL(archivo);
    });
    zoom.addEventListener("input", function () { if (imagen) dibujar(); });
    lienzo.addEventListener("pointerdown", function (e) { arrastre = { x: e.clientX - x, y: e.clientY - y }; lienzo.setPointerCapture(e.pointerId); });
    lienzo.addEventListener("pointermove", function (e) { if (arrastre && imagen) { x = e.clientX - arrastre.x; y = e.clientY - arrastre.y; dibujar(); } });
    lienzo.addEventListener("pointerup", function () { arrastre = null; });
    form.addEventListener("submit", function (e) {
      if (!imagen || resultado.files.length) return;
      e.preventDefault();
      lienzo.toBlob(function (blob) {
        var datos = new DataTransfer();
        datos.items.add(new File([blob], "foto.png", { type: "image/png" }));
        resultado.files = datos.files;
        form.submit();
      }, "image/png");
    });
  });
})();
