// La autenticación del panel se realiza mediante la cookie HttpOnly emitida por
// POST /admin/session. El token no se lee de la URL ni se conserva en JavaScript.
export function authHeaders(): Record<string, string> {
  return {};
}
