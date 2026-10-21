/* Botón de dictado 🎤 para las tools de la casa.
 *
 * Uso desde otra tool (misma máquina, otra carpeta):
 *   <script src="../voz/voz.js"></script>
 *   const boton = Voz.boton({
 *     modo: "lista",                       // "lista" -> datos.items, "texto" -> solo datos.texto
 *     alTerminar: (datos) => { ... },      // { texto, items? }
 *     alError: (mensaje) => { ... },       // opcional; si no, usa alert()
 *     etiqueta: "Dictar",                  // texto accesible (aria-label)
 *   });
 *   contenedor.append(boton);
 *
 * Tocar = empieza a escuchar; tocar otra vez = termina y manda el audio a /voz/api/.
 * Se corta solo a los 60 s. Necesita HTTPS (el micrófono no funciona por http).
 */
(() => {
  // La API vive junto a este archivo: /voz/voz.js -> /voz/api/
  const BASE = new URL(".", document.currentScript.src).href;
  const MAX_MS = 60 * 1000;
  const FORMATOS = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

  const ICONO_MIC =
    '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8"/></svg>';
  const ICONO_PARAR =
    '<svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true"><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/></svg>';
  const ICONO_PENSANDO =
    '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><circle cx="5" cy="12" r="2" fill="currentColor"/><circle cx="12" cy="12" r="2" fill="currentColor"/><circle cx="19" cy="12" r="2" fill="currentColor"/></svg>';

  // Estilos mínimos; cada tool puede pisarlos con .voz-boton { ... }
  const estilo = document.createElement("style");
  estilo.textContent = `
    .voz-boton { display:inline-grid; place-items:center; min-width:48px; min-height:48px; padding:0 12px;
      border:none; border-radius:14px; background:var(--voz-fondo,#ececf3); color:var(--voz-tinta,#333);
      cursor:pointer; -webkit-tap-highlight-color:transparent; }
    .voz-boton.grabando { background:#d93025; color:#fff; animation:voz-pulso 1.2s ease-in-out infinite; }
    .voz-boton.pensando { opacity:.7; cursor:progress; }
    @keyframes voz-pulso { 0%,100% { box-shadow:0 0 0 0 rgba(217,48,37,.45); } 50% { box-shadow:0 0 0 10px rgba(217,48,37,0); } }
    @media (prefers-reduced-motion: reduce) { .voz-boton.grabando { animation:none; } }
  `;
  document.head.append(estilo);

  function disponible() {
    return !!(window.isSecureContext && navigator.mediaDevices && window.MediaRecorder);
  }

  function boton({ modo = "texto", alTerminar, alError, etiqueta = "Dictar" } = {}) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "voz-boton";
    b.innerHTML = ICONO_MIC;
    b.setAttribute("aria-label", etiqueta);
    b.title = etiqueta;

    const avisar = alError || ((m) => alert(m));
    let grabador = null;
    let trozos = [];
    let corte = null;

    function estado(cual) {
      b.classList.toggle("grabando", cual === "grabando");
      b.classList.toggle("pensando", cual === "pensando");
      b.disabled = cual === "pensando";
      b.innerHTML = cual === "grabando" ? ICONO_PARAR : cual === "pensando" ? ICONO_PENSANDO : ICONO_MIC;
      b.setAttribute("aria-label", cual === "grabando" ? "Terminar de dictar" : cual === "pensando" ? "Entendiendo…" : etiqueta);
    }

    async function empezar() {
      if (!disponible()) {
        avisar("El dictado necesita abrir la app por https y un navegador con micrófono.");
        return;
      }
      let flujo;
      try {
        flujo = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch {
        avisar("No se pudo usar el micrófono. Revisa que la página tenga permiso.");
        return;
      }
      const tipo = FORMATOS.find((f) => MediaRecorder.isTypeSupported(f));
      grabador = new MediaRecorder(flujo, tipo ? { mimeType: tipo } : undefined);
      trozos = [];
      grabador.ondataavailable = (e) => e.data.size && trozos.push(e.data);
      grabador.onstop = () => {
        flujo.getTracks().forEach((t) => t.stop());
        enviar(new Blob(trozos, { type: grabador.mimeType || "audio/webm" }));
      };
      grabador.start();
      estado("grabando");
      corte = setTimeout(terminar, MAX_MS);
    }

    function terminar() {
      clearTimeout(corte);
      if (grabador && grabador.state === "recording") grabador.stop();
    }

    async function enviar(audio) {
      estado("pensando");
      try {
        if (audio.size < 1000) throw new Error("No se escuchó nada. Mantén el botón activo mientras hablas.");
        const r = await fetch(`${BASE}api/transcribir?modo=${encodeURIComponent(modo)}`, {
          method: "POST",
          headers: { "Content-Type": audio.type },
          body: audio,
        });
        const datos = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(datos.error || `Error ${r.status}`);
        if (!datos.texto) throw new Error("No se entendió nada. Intenta de nuevo, un poco más cerca.");
        alTerminar && alTerminar(datos);
      } catch (e) {
        avisar(e.message === "Failed to fetch" ? "No hay conexión con el servidor." : e.message);
      } finally {
        estado("listo");
      }
    }

    b.addEventListener("click", () => {
      if (grabador && grabador.state === "recording") terminar();
      else empezar();
    });

    return b;
  }

  window.Voz = { boton, disponible };
})();
