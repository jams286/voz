# voz (casa)

Servicio de dictado compartido por las tools de la casa.

## Cómo está hecho

- `servidor.py`: `ThreadingHTTPServer` + faster-whisper (`small`, int8, CPU, la mitad de los núcleos), en `127.0.0.1:8774`. El modelo se carga en segundo plano al arrancar (`/api/estado` dice cuándo está listo) y queda en memoria (~750 MB de RAM). Un dictado a la vez (semáforo); `language='es'`, `vad_filter=True`. Audio máx. 8 MB / 90 s. Se guarda en un temporal que se borra al terminar: no se conserva ningún audio.
- `modo=lista`: `separar_lista()` parte el texto por comas, puntos, "y", "e", "luego", "además", "también"; quita arranques como "agrega", "apunta", "necesitamos"; saca la cantidad del inicio ("2 leches", "una docena de tortillas" → 12). "un/una" no se pone como cantidad.
- Errores propios: `AudioInvalido` (mensaje para el usuario). Cualquier otro error al decodificar → "No se pudo entender el audio" (no se filtra el error técnico).
- Mismas versiones que el transcriptor (`faster-whisper==1.2.1`, `av==18.1.0`) y comparte la caché del modelo en `~/.cache/huggingface`. Entorno propio en `.venv/` (no va a git).
- `web/voz.js`: componente del botón 🎤 (`Voz.boton({modo, alTerminar, alError, etiqueta})`). Calcula la URL de la API desde su propio `src`, así que cualquier tool lo carga con `<script src="../voz/voz.js">`. Graba con MediaRecorder (webm/opus en Android y escritorio, mp4/aac en iPhone), corta a los 60 s, inyecta estilos mínimos (`.voz-boton`, `.grabando`, `.pensando`) que la tool puede pisar; colores con `--voz-fondo` / `--voz-tinta`.
- `web/index.html`: página de prueba (no va en el hub).

## Dónde corre

- nginx: `/voz/api/` → `127.0.0.1:8774/api/` (config en `infra/nginx`); `/voz/` sirve `web/` desde `/var/www/voz/`.
- Servicio systemd de usuario `voz.service` (copia en `servicio/`).
