# Backend architecture: Authentication and authorization

> [Index](../README.md) · **Use for:** login/JWT/refresh tokens, OIDC, API keys, RBAC, ownership checks, rate limiting. Placeholders are defined in the index.
> **Related:** [05-caching-and-sessions](05-caching-and-sessions.md)

## 10. Authentication and authorization

### 10.1 Choose an approach

| Situation | Approach |
|---|---|
| The service owns its users | Local accounts: Argon2id password hashing (`argon2-cffi`), JWT access token plus a server-side refresh session |
| Users come from an identity provider (Keycloak, Auth0, Google…) | OIDC: validate the provider's JWTs (JWKS fetched and cached, `iss`, `aud` and `exp` checked) and map claims to local users |
| Service-to-service calls | API keys (hashed at rest, scoped, rotatable) or mTLS / client-credentials tokens |

### 10.2 Token rules (local auth)

- **Access token:** a JWT, short-lived (5–15 min), containing `sub`, `exp`, `iat`, `jti`,
  roles or scopes, and `iss`/`aud`. Sign it with HS256 using a 32+ byte secret, or with
  RS256/EdDSA when other services must verify it. Allow a small clock skew (≤ 30 s).
- **Refresh token:** opaque and random, stored hashed in the `SessionStore` ([architecture §7.2](05-caching-and-sessions.md)), rotated
  on every use. If an old refresh token is used again, revoke the whole session family.
- Browser clients receive the refresh token in an `HttpOnly; Secure; SameSite=Strict` cookie.
  Mobile or API clients receive it in the response body.
- Endpoints: `POST /auth/register`, `POST /auth/login`, `POST /auth/refresh`,
  `POST /auth/logout`, `GET /auth/me`.

### 10.3 Authorization

- `api/dependencies.py` exposes `CurrentUser = Annotated[User, Depends(get_current_user)]`
  and `require_scopes(*scopes)` / `require_role(*roles)`.
- Use **role-based access control** for coarse permissions. **Ownership checks happen in the
  service or repository** ([architecture §6.1](04-database-management.md)), never only in the router.
- Deny by default. A route is public only when it is explicitly marked so (health, login,
  docs in dev).

### 10.4 Abuse protection

- Rate limiting in Redis (sliding window or token bucket), keyed per user and per IP, with a
  stricter limit on auth endpoints and on expensive endpoints (LLM, ingestion). Respond with
  429 and `Retry-After`.
- Lock out repeated failed logins with exponential backoff, and record an audit log entry.
- Limit request body size and upload size, and check the content type of uploads.
