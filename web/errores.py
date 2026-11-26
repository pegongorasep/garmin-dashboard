"""Errores de formulario con clave del catálogo i18n: `str(ex)` sigue saliendo en español (pruebas, MCP) y la web lo
muestra en el idioma de la persona con `texto(ex, t)`."""
from ajustes import ConfigError
import i18n


class ErrorT(ConfigError):
    def __init__(self, clave: str, campo: str | None = None, **vars):
        self.clave, self.campo, self.vars = clave, campo, vars
        super().__init__(texto(self, lambda k, **v: i18n.t(k, "es", **v)))


def texto(ex: Exception, t) -> str:
    """El mensaje de `ex` en el idioma de `t` (los errores del motor, que no traen clave, quedan como vienen)."""
    clave = getattr(ex, "clave", None)
    if clave is None:
        return str(ex)
    # un valor "@clave" se traduce también (nombres de campo)
    vars = {k: (t(v[1:]) if isinstance(v, str) and v.startswith("@") else v) for k, v in ex.vars.items()}
    return t(clave, **vars)
