# Backend architecture: Testing strategy

> [Index](../README.md) · **Use for:** what to test per layer, fakes, contract tests, integration tests. Placeholders are defined in the index.
> **Related:** [03-code-quality-and-tests](../project-structure/03-code-quality-and-tests.md)

## 13. Testing strategy

| Layer | Test type | Uses |
|---|---|---|
| `domain/` | unit | plain objects, no mocks |
| `services/` | unit | **fakes** from `tests/fakes/` (`InMemoryConversationRepository`, `FakeLLM`, `InMemoryCache`, `RecordingPublisher`) |
| `api/` | API | `httpx.AsyncClient(transport=ASGITransport(app))`, with the container built from fakes and auth overridden |
| `adapters/` | integration (`@pytest.mark.integration`) | real technology through testcontainers or compose: Postgres, Mongo, Redis, RabbitMQ, Kafka, Qdrant |
| consumers | unit + integration | call the handler with an envelope; check idempotency by delivering the same message twice |
| migrations | integration | upgrade → downgrade → upgrade; check that the Mongo indexes exist |
| LLM / RAG quality | eval (separate, not in the unit gate) | a fixed question set with expected sources; track the scores over time |

- **Contract tests for ports.** One parametrized test suite runs against both the fake and
  the real adapter, so the two cannot drift apart.
- The suite never calls real third-party APIs. LLM and embedding calls are faked. Optionally,
  recorded fixtures can be used for adapter tests.
- Time, randomness and IDs are injectable (a `Clock` port, a seeded ID factory) to keep tests
  deterministic.
- Every bug fix includes a regression test, named after the behaviour it protects.
