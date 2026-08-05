---
id: 003
title: LLMProvider interface + OpenAI implementation
status: ready-for-merge
depends_on: [001]
branch: ticket/003-llm-provider-openai
base_branch: ticket/001-scaffold-docker-compose
test_command: ".venv/bin/python -m pytest tests/test_llm_provider.py -q"
full_suite_command: ".venv/bin/ruff check . && .venv/bin/mypy app && .venv/bin/python -m pytest -q"
attempts: 1
---

## Description
Define the `LLMProvider` interface (`chat`, `embed`) and an `OpenAIProvider` concrete impl.
Provider is config-selected so Bedrock can slot in later. Include timeout + basic retry.

## Acceptance criteria
- [ ] `LLMProvider` abstract interface with typed `chat()` and `embed()` signatures
- [ ] `OpenAIProvider` implements both; selected via config/env
- [ ] Calls are mockable in tests (no live API needed in CI)
- [ ] Timeout + basic retry on transient errors

## Test plan (orchestrator authors these)
- unit: `tests/test_llm_provider.py` — mocked OpenAI client: chat returns text, embed returns
  vector, retry path on transient error, provider selected from config
