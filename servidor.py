"""Servicio de dictado de la casa: audio -> texto con Whisper (faster-whisper, CPU).

Escucha solo en 127.0.0.1; nginx publica /voz/api/ -> /api/.
Lo usan otras tools (lista de compras, pizarra, cocina) con el botón 🎤 de `web/voz.js`.

    .venv/bin/python servidor.py

Rutas:
    POST /api/transcribir?modo=texto   cuerpo = audio crudo (webm/opus de Android, mp4/aac de iPhone…)
                                       -> {"texto"}
    POST /api/transcribir?modo=lista   -> {"texto", "items": [{"nombre", "cantidad"}]}
                                       "dos leches, huevos y tortillas" -> 3 productos
    GET  /api/estado                   -> {"listo": bool}
"""

import json
import os
import re
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from faster_whisper import WhisperModel

HOST = '127.0.0.1'
PUERTO = int(os.environ.get('VOZ_PUERTO', 8774))
MODELO = os.environ.get('VOZ_MODELO', 'small')   # el mismo que ya usa el transcriptor (queda en caché)
MAX_AUDIO = 8 * 1024 * 1024                      # ~1 min de audio comprimido sobra
MAX_SEGUNDOS = 90
ESPERA_MAX = 60                                  # si hay otro dictado en curso, cuánto esperar turno

modelo = None


class AudioInvalido(Exception):
    """Errores nuestros con mensaje apto para mostrar en la página."""


turno = threading.Semaphore(1)   # un dictado a la vez: Whisper ya usa varios núcleos


# ---------- Texto -> lista ----------

NUMEROS = {
    'un': '1', 'una': '1', 'uno': '1', 'dos': '2', 'tres': '3', 'cuatro': '4', 'cinco': '5',
    'seis': '6', 'siete': '7', 'ocho': '8', 'nueve': '9', 'diez': '10', 'doce': '12',
    'media docena': '6', 'docena': '12', 'una docena': '12',
}
# Palabras con las que se suele empezar a dictar y que no son productos
INICIOS = r'^(agrega(r|le)?|añade|añadir|apunta(r)?|anota(r)?|pon(er)?|compra(r)?|necesitamos|hace(n)? falta|falta(n)?|también|y|e)\s+'
SEPARADORES = r'\s*(?:,|;|\.|\n|\by\b|\be\b|\bluego\b|\bademás\b|\btambién\b)\s*'


def separar_lista(texto):
    items = []
    for parte in re.split(SEPARADORES, texto, flags=re.IGNORECASE):
        parte = parte.strip(' .,;:¡!¿?"\'').strip()
        for _ in range(2):  # "agrega también leche"
            parte = re.sub(INICIOS, '', parte, flags=re.IGNORECASE).strip()
        if not parte:
            continue
        cantidad = ''
        m = re.match(r'^(\d+(?:[.,]\d+)?)\s+(.+)$', parte)
        if m:
            cantidad, parte = m.group(1), m.group(2)
        else:
            for palabra in sorted(NUMEROS, key=len, reverse=True):
                m = re.match(rf'^{palabra}\s+(?:de\s+)?(.+)$', parte, flags=re.IGNORECASE)
                if m:
                    cantidad, parte = NUMEROS[palabra], m.group(1)
                    break
        # "un pan" no necesita cantidad
        if cantidad == '1':
            cantidad = ''
        parte = parte[:60]
        items.append({'nombre': parte[0].upper() + parte[1:], 'cantidad': cantidad})
    return items


# ---------- Whisper ----------

def cargar_modelo():
    global modelo
    hilos = max(2, (os.cpu_count() or 4) // 2)   # deja núcleos libres para el resto del server
    modelo = WhisperModel(MODELO, device='cpu', compute_type='int8', cpu_threads=hilos)
    print(f'Modelo {MODELO} listo ({hilos} hilos)', flush=True)


def transcribir(ruta):
    segmentos, info = modelo.transcribe(
        ruta, language='es', beam_size=5, vad_filter=True,
        condition_on_previous_text=False,
    )
    if info.duration > MAX_SEGUNDOS:
        raise AudioInvalido(f'El audio dura más de {MAX_SEGUNDOS} segundos')
    return ' '.join(s.text.strip() for s in segmentos).strip()


# ---------- HTTP ----------

class Manejador(BaseHTTPRequestHandler):
    server_version = 'Voz'

    def log_message(self, formato, *args):
        pass

    def responder(self, codigo, datos):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode('utf-8')
        self.send_response(codigo)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_GET(self):
        if urlparse(self.path).path == '/api/estado':
            self.responder(200, {'listo': modelo is not None})
        else:
            self.responder(404, {'error': 'No existe'})

    def do_POST(self):
        url = urlparse(self.path)
        if url.path != '/api/transcribir':
            self.responder(404, {'error': 'No existe'})
            return
        modo = parse_qs(url.query).get('modo', ['texto'])[0]
        largo = int(self.headers.get('Content-Length') or 0)
        if not largo:
            self.responder(400, {'error': 'No llegó audio'})
            return
        if largo > MAX_AUDIO:
            self.responder(413, {'error': 'El audio es demasiado largo'})
            return
        audio = self.rfile.read(largo)

        if modelo is None:
            self.responder(503, {'error': 'El dictado todavía está arrancando, intenta en un momento'})
            return
        if not turno.acquire(timeout=ESPERA_MAX):
            self.responder(503, {'error': 'Hay otro dictado en curso, intenta en un momento'})
            return
        try:
            with tempfile.NamedTemporaryFile(prefix='voz-', suffix='.audio') as tmp:
                tmp.write(audio)
                tmp.flush()
                inicio = time.monotonic()
                texto = transcribir(tmp.name)
                print(f'Dictado de {len(audio) // 1024} KB en {time.monotonic() - inicio:.1f} s', flush=True)
            datos = {'texto': texto}
            if modo == 'lista':
                datos['items'] = separar_lista(texto)
            self.responder(200, datos)
        except AudioInvalido as e:
            self.responder(400, {'error': str(e)})
        except Exception as e:  # noqa: BLE001 - p. ej. audio dañado: que el servicio siga vivo
            print('Error:', repr(e), flush=True)
            self.responder(400, {'error': 'No se pudo entender el audio'})
        finally:
            turno.release()


def main():
    # El modelo se carga en segundo plano para que el puerto abra de una vez
    threading.Thread(target=cargar_modelo, daemon=True).start()
    servidor = ThreadingHTTPServer((HOST, PUERTO), Manejador)
    print(f'Voz en http://{HOST}:{PUERTO}', flush=True)
    servidor.serve_forever()


if __name__ == '__main__':
    main()
