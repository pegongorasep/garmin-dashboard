"""Envío de correo con Resend (un POST con httpx; sin SDK). Sin RESEND_API_KEY la liga solo se registra en consola."""
import logging

import httpx

log = logging.getLogger("web.correo")


def enviar(settings, para: str, asunto: str, texto: str) -> bool:
    """Manda el correo; True si salió. Sin API key lo imprime en el log (desarrollo)."""
    if not settings.resend_api_key:
        log.warning("CORREO (sin RESEND_API_KEY) para %s: %s\n%s", para, asunto, texto)
        print(f"\n--- correo para {para} ---\n{asunto}\n{texto}\n---", flush=True)
        return False
    try:
        r = httpx.post("https://api.resend.com/emails", timeout=15,
                       headers={"Authorization": f"Bearer {settings.resend_api_key}"},
                       json={"from": settings.correo_de, "to": [para], "subject": asunto, "text": texto})
        r.raise_for_status()
        return True
    except httpx.HTTPError as e:
        log.error("no se pudo mandar el correo: %s", type(e).__name__)   # sin el cuerpo: lleva la liga
        return False
