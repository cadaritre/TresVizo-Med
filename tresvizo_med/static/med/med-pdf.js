// Visor de PDF por páginas con PDF.js (se renderiza cada página al acercarse a la pantalla). Sin estilos en línea.
const raiz = document.querySelector("[data-pdf]");
if (raiz) {
  const estado = raiz.querySelector("[data-pdf-estado]");
  const contenedor = raiz.querySelector("[data-pdf-paginas]");
  try {
    const pdfjs = await import(raiz.dataset.lib);
    pdfjs.GlobalWorkerOptions.workerSrc = raiz.dataset.worker;
    const documento = await pdfjs.getDocument({ url: raiz.dataset.src, withCredentials: true }).promise;
    estado.textContent = documento.numPages + (documento.numPages === 1 ? " página" : " páginas");
    const ancho = () => Math.min(contenedor.clientWidth || 800, 1000);
    const marcadores = [];
    for (let n = 1; n <= documento.numPages; n++) {
      const lienzo = document.createElement("canvas");
      lienzo.className = "med-pdf__pagina";
      lienzo.setAttribute("role", "img");
      lienzo.setAttribute("aria-label", "Página " + n + " de " + documento.numPages);
      lienzo.dataset.pagina = String(n);
      contenedor.append(lienzo);
      marcadores.push(lienzo);
    }
    const dibujar = async (lienzo) => {
      if (lienzo.dataset.lista) return;
      lienzo.dataset.lista = "1";
      const pagina = await documento.getPage(Number(lienzo.dataset.pagina));
      const base = pagina.getViewport({ scale: 1 });
      const escala = ancho() / base.width;
      const vista = pagina.getViewport({ scale: escala * (window.devicePixelRatio || 1) });
      lienzo.width = vista.width;
      lienzo.height = vista.height;
      lienzo.classList.add("med-pdf__pagina--lista");
      await pagina.render({ canvasContext: lienzo.getContext("2d"), viewport: vista }).promise;
    };
    const observador = new IntersectionObserver((entradas) => {
      for (const e of entradas) if (e.isIntersecting) dibujar(e.target);
    }, { rootMargin: "600px 0px" });
    marcadores.forEach((m) => observador.observe(m));
  } catch (error) {
    estado.textContent = "No se pudo mostrar el PDF. Descárgalo para abrirlo.";
  }
}
