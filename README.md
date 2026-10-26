# Two local LLM agents: Git handoff test

Requires Docker Compose and sufficient RAM for Ollama qwen2.5-coder:1.5b. First model pull requires internet; inference is local afterward. No API key required.

```bash
docker compose up -d ollama
docker compose run --rm pull
docker compose run --rm lab
```

Results: `out/results.json`, `out/metrics.csv`, `out/events.jsonl`, `out/frozen_manifest.json`, `out/final-repo/`.

The controller freezes 10 checks and common per-agent call/action/output-token/time limits, starts A, commits the seven-field handoff, clones into a **new** B workspace, and executes B with a **new chat history**. B never receives A's chat or working directory. Tool selection is restricted by `config/tool_policy.json`: agents may only read/write allowlisted files; the controller alone runs Git and checks. `metrics.csv` uses blind IDs P01/P02; `results.json` contains the audit mapping by order. Output tokens are reported by Ollama where possible.

The model may fail to solve the task; this is recorded, not hidden. Docker isolates the controller from the host but **generated Python is not securely sandboxed**. Only run with trusted models and fixtures; do not use this prototype for adversarial code. Both agents share one Ollama inference service, but have independent conversations and Git workspaces. A failed run returns nonzero and still writes a report.
