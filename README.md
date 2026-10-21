# voz

Servicio de dictado de la casa: recibe audio del micrófono y lo devuelve como texto (Whisper `small`, en CPU). No es una app del hub: lo usan otras tools con un botón 🎤 (`web/voz.js`), por ejemplo para dictar varios productos a la lista de compras de una vez.

- API: `https://192.168.1.4/voz/api/transcribir` (nginx → `127.0.0.1:8774`)
- Página de prueba: https://192.168.1.4/voz/
- El micrófono del navegador solo funciona por HTTPS.

## Comandos

Entorno (una vez):

```
cd ~/proyectos/casa/voz && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Publicar la parte web:

```
rsync -a --delete ~/proyectos/casa/voz/web/ /var/www/voz/
```

Servicio:

```
cp ~/proyectos/casa/voz/servicio/voz.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now voz.service
journalctl --user -u voz -f
```
