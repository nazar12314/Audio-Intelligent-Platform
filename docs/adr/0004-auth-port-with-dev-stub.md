# 0004. Authentication port with a development stub

- **Status:** accepted
- **Date:** 2026-11-01

## Context

Stage 1 endpoints must know the calling user: object keys are per user, and every query
filters by owner. The authentication approach (Cognito, another OIDC provider, or local
accounts) is not decided yet.

## Decision

- Endpoints depend on an `Authenticator` port (`core/auth.py`) that turns request
  headers into a `Principal` or raises `Unauthorized`. Routers use `CurrentUser`; services
  receive a plain `owner_id`.
- The only implementation for now, `DevHeaderAuthenticator`, trusts the
  `X-Dev-User-Id` header (a UUID).
- `AUDIO_AUTH__MODE=dev_header` is refused when `AUDIO_ENV=prod`, so a production
  deployment cannot start until real authentication exists.

## Consequences

- Upload code does not change when real authentication arrives: a new `Authenticator`
  implementation is selected in the container through `AUTH__MODE`.
- Anyone who can reach a dev or test deployment can act as any user. Such deployments
  must not be publicly reachable.
- User IDs are UUIDs. A provider with non-UUID subjects needs a mapping to local users.
