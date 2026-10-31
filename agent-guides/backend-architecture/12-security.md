# Backend architecture: Security baseline

> [Index](../README.md) · **Use for:** secrets handling, injection, uploads, audit log, LLM prompt-injection guards. Placeholders are defined in the index.

## 14. Security baseline

- Secrets come only from the environment or a secret file. They never sit in code, in the
  image, or in logs. Type them as `SecretStr`.
- Use parameterized queries only. The Mongo adapter never builds a query from raw user
  dictionaries; validate with Pydantic first, and reject `$`-prefixed keys.
- Validate uploads: size, type, safe file names, and storage outside any web root.
- Containers run as a non-root user. Security-relevant dependencies get pinned floors, with
  comments that cite the advisory.
- Write an audit log for auth events and admin actions, with stable event codes.
- For LLM features: guard against prompt injection by keeping system and retrieved content
  separate, never granting a model the ability to call tools beyond the user's own
  permissions, and filtering output where required.
