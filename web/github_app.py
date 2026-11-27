"""Cliente mínimo de la GitHub App (instalada solo en el repo de cada persona). Nunca se registran tokens ni la llave."""
import time
from urllib.parse import quote

import httpx
import jwt

BASE = "https://api.github.com"
CABECERAS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


class GitHubError(Exception):
    def __init__(self, status: int, mensaje: str = ""):
        super().__init__(f"GitHub {status}: {mensaje}")
        self.status = status
        self.mensaje = mensaje


class InstalacionPerdida(GitHubError):
    """La instalación ya no existe o no llega al repo (la persona desinstaló la app): distinta de una caída de red o un 5xx."""


def _ts(iso: str) -> float:
    from datetime import datetime
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


class GitHubApp:
    def __init__(self, settings, transport=None):
        self.s = settings
        self.transport = transport
        self._tokens: dict[int, tuple[str, float]] = {}

    # --- infraestructura ---
    def _cliente(self) -> httpx.Client:
        return httpx.Client(base_url=BASE, headers=CABECERAS, timeout=10, transport=self.transport)

    def _pedir(self, metodo, ruta, *, auth=None, ok=(200,), **kw):
        h = {"Authorization": auth} if auth else {}
        with self._cliente() as c:
            r = c.request(metodo, ruta, headers=h, **kw)
        if r.status_code not in ok:
            try:
                msg = r.json().get("message", "")
            except Exception:
                msg = ""
            raise GitHubError(r.status_code, msg)
        return r

    def jwt_app(self) -> str:
        ahora = int(time.time())
        return jwt.encode({"iat": ahora - 60, "exp": ahora + 540, "iss": str(self.s.github_app_id)},
                          self.s.github_app_private_key, algorithm="RS256")

    def token_instalacion(self, instalacion_id) -> str:
        instalacion_id = int(instalacion_id)
        t = self._tokens.get(instalacion_id)
        if t and t[1] - 300 > time.time():
            return t[0]
        try:
            r = self._pedir("POST", f"/app/installations/{instalacion_id}/access_tokens",
                            auth=f"Bearer {self.jwt_app()}", ok=(201,))
        except GitHubError as e:
            if e.status == 404:
                self._tokens.pop(instalacion_id, None)
                raise InstalacionPerdida(e.status, e.mensaje) from e
            raise
        d = r.json()
        self._tokens[instalacion_id] = (d["token"], _ts(d["expires_at"]))
        return d["token"]

    def _inst(self, instalacion_id, metodo, ruta, **kw):
        try:
            return self._pedir(metodo, ruta, auth=f"token {self.token_instalacion(instalacion_id)}", **kw)
        except InstalacionPerdida:
            raise
        except GitHubError as e:
            limite = "rate limit" in (e.mensaje or "").lower()   # un 403 por límite de uso no es una desinstalación
            if e.status in (401, 404) or (e.status == 403 and not limite):
                self._tokens.pop(int(instalacion_id), None)
                raise InstalacionPerdida(e.status, e.mensaje) from e
            raise

    # --- instalación y verificación ---
    def url_instalar(self, state: str) -> str:
        return f"https://github.com/apps/{self.s.github_app_slug}/installations/new?state={quote(state, safe='')}"

    def token_de_usuario(self, code: str) -> str:
        with httpx.Client(timeout=10, transport=self.transport) as c:
            r = c.post("https://github.com/login/oauth/access_token", headers={"Accept": "application/json"},
                       data={"client_id": self.s.github_app_client_id,
                             "client_secret": self.s.github_app_client_secret, "code": code})
        d = r.json() if r.status_code == 200 else {}
        if not d.get("access_token"):
            raise GitHubError(r.status_code if r.status_code != 200 else 400, d.get("error", "sin token"))
        return d["access_token"]

    def instalaciones_del_usuario(self, token_usuario: str) -> list[int]:
        r = self._pedir("GET", "/user/installations", auth=f"Bearer {token_usuario}")
        return [i["id"] for i in r.json().get("installations", [])]

    def repos_de_instalacion(self, instalacion_id) -> list[dict]:
        r = self._inst(instalacion_id, "GET", "/installation/repositories", params={"per_page": 100})
        return [{"id": x["id"], "full_name": x["full_name"], "private": x.get("private", False),
                 "default_branch": x.get("default_branch", "main")} for x in r.json().get("repositories", [])]

    # --- repo ---
    def secretos(self, instalacion_id, repo) -> list[dict]:
        r = self._inst(instalacion_id, "GET", f"/repos/{repo}/actions/secrets", params={"per_page": 100})
        return [{"name": x["name"], "updated_at": x.get("updated_at")} for x in r.json().get("secrets", [])]

    def disparar(self, instalacion_id, repo, rama, workflow="deploy.yml") -> bool:
        r = self._inst(instalacion_id, "POST", f"/repos/{repo}/actions/workflows/{workflow}/dispatches",
                       ok=(204,), json={"ref": rama})
        return r.status_code == 204

    def corridas(self, instalacion_id, repo, workflow="deploy.yml", desde=None) -> list[dict]:
        params = {"per_page": 20}
        if desde:
            params["created"] = f">={desde}"
        r = self._inst(instalacion_id, "GET", f"/repos/{repo}/actions/workflows/{workflow}/runs", params=params)
        return [{k: x.get(k) for k in ("id", "status", "conclusion", "event", "created_at")}
                for x in r.json().get("workflow_runs", [])]

    def jobs(self, instalacion_id, repo, run_id) -> list[dict]:
        r = self._inst(instalacion_id, "GET", f"/repos/{repo}/actions/runs/{run_id}/jobs")
        return [{"id": j.get("id"), "name": j.get("name"), "status": j.get("status"),
                 "conclusion": j.get("conclusion"),
                 "steps": [{k: s.get(k) for k in ("name", "status", "conclusion")} for s in j.get("steps", [])]}
                for j in r.json().get("jobs", [])]
