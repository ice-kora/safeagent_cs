# Checkpoint / Resume Architecture

Checkpoint is created when `/api/chat` or workflow mode produces a `pending_action`.

Resume flow:

```text
GET /api/checkpoints
-> POST /api/checkpoints/{checkpoint_id}/resume
-> create child run
-> validate pending_action ownership/session/status
-> ActionPlanValidator
-> PolicyService
-> return RESUME_READY
-> user calls /api/confirm
-> ToolGateway executes if policy allows
```

Resume does not execute tools. It only restores the user to a safe confirmation point.

Runtime tables:

- `checkpoints`
- `checkpoint_events`
- `resume_attempts`

Important states:

- `WAITING_CONFIRMATION`
- `RESUMABLE`
- `RESUMED`
- `EXPIRED`
- `CANCELLED`
- `FAILED`
- `COMPLETED`
