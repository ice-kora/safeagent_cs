# Product Architecture

SafeAgent-CS v1.0 exposes a visible customer-support loop:

```text
Channel/Console
-> /api/chat
-> Intent
-> Planner
-> ActionPlanValidator
-> PolicyService
-> ToolGateway
-> ToolAdapter
-> Response / PendingAction / Checkpoint
```

Workflow mode uses the same service boundaries through LangGraph or the local workflow runner. Manual mode keeps the deterministic dev path.

Key APIs:

- `POST /api/chat`
- `POST /api/confirm`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/traces`
- `GET /api/checkpoints`
- `POST /api/checkpoints/{checkpoint_id}/resume`
- `POST /api/channels/feishu/events`

MCP and Feishu are skeleton integrations. They demonstrate placement and contracts without external production coupling.
