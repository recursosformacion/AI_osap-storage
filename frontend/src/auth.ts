// Token de servicio para la SPA de mantenimiento de osap-storage.
//
// La SPA se abre desde osap-api con `?token=<service-token storage:admin>`. Ahí no hay
// sesión de navegador, así que el token viaja en la URL; se guarda en `sessionStorage`
// para que sobreviva a la navegación interna entre páginas del SPA.

const STORAGE_KEY = "osap-storage-admin-token";

export function resolveToken(): string {
  try {
    const fromQuery = new URLSearchParams(window.location.search).get("token");
    if (fromQuery) {
      window.sessionStorage.setItem(STORAGE_KEY, fromQuery);
      return fromQuery;
    }
    return window.sessionStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function authHeaders(): Record<string, string> {
  const token = resolveToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
