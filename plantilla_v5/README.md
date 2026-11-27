# Mis datos de Ahí la Llevas

Este repo es el tubo que lleva tus datos de Garmin a [Ahí la Llevas](https://ahilallevas.com). No tiene código: solo dos workflows que llaman al motor.

## Cómo se usa

1. Sigue la guía de Ahí la Llevas: crea esta copia y autoriza la GitHub App para ella.
2. En el repo, ve a **Settings → Secrets and variables → Actions → New repository secret** y crea `PERSONAL_API_KEY` con tu key de la API personal de Garmin. Nunca la pongas en un archivo ni en un chat.
3. La app comprueba la conexión y trae tu historial desde la web; no necesitas buscar ni correr workflows manualmente.

Después se actualiza solo tres veces al día. Tu configuración y tu plan se editan en la web, no aquí.
