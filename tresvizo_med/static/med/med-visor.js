// Visor de imágenes: zoom con rueda, botones o pellizco, y paneo arrastrando. Sin estilos en línea (solo CSSOM).
(function () {
  "use strict";
  document.querySelectorAll("[data-zoom]").forEach(function (visor) {
    var lienzo = visor.querySelector("[data-zoom-lienzo]");
    var imagen = visor.querySelector("[data-zoom-imagen]");
    var escala = 1, x = 0, y = 0;
    var punteros = new Map(), distancia = 0;
    function aplicar() { imagen.style.transform = "translate(" + x + "px," + y + "px) scale(" + escala + ")"; }
    function zoom(factor) { escala = Math.min(8, Math.max(1, escala * factor)); if (escala === 1) { x = 0; y = 0; } aplicar(); }
    visor.querySelector("[data-zoom-mas]").addEventListener("click", function () { zoom(1.25); });
    visor.querySelector("[data-zoom-menos]").addEventListener("click", function () { zoom(0.8); });
    visor.querySelector("[data-zoom-reiniciar]").addEventListener("click", function () { escala = 1; x = 0; y = 0; aplicar(); });
    lienzo.addEventListener("wheel", function (e) { e.preventDefault(); zoom(e.deltaY < 0 ? 1.1 : 0.9); }, { passive: false });
    lienzo.addEventListener("keydown", function (e) {
      if (e.key === "+" || e.key === "=") zoom(1.25);
      if (e.key === "-") zoom(0.8);
      var paso = 40;
      if (e.key === "ArrowLeft") x += paso; if (e.key === "ArrowRight") x -= paso;
      if (e.key === "ArrowUp") y += paso; if (e.key === "ArrowDown") y -= paso;
      aplicar();
    });
    lienzo.addEventListener("pointerdown", function (e) { lienzo.setPointerCapture(e.pointerId); punteros.set(e.pointerId, { x: e.clientX, y: e.clientY }); });
    lienzo.addEventListener("pointermove", function (e) {
      var previo = punteros.get(e.pointerId);
      if (!previo) return;
      punteros.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (punteros.size === 2) {
        var p = Array.from(punteros.values());
        var d = Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y);
        if (distancia) zoom(d / distancia);
        distancia = d;
      } else if (escala > 1) { x += e.clientX - previo.x; y += e.clientY - previo.y; aplicar(); }
    });
    function soltar(e) { punteros.delete(e.pointerId); distancia = 0; }
    lienzo.addEventListener("pointerup", soltar); lienzo.addEventListener("pointercancel", soltar);
  });
})();
