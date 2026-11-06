# Native Codex queue wakes

Lookup-only implementation contract. [Manual](../manual.md#wake).

- Eligibility: local resumable UUID, an existing writer lock, live idle status, unread IDs. A lock does not identify app versus CLI ownership.
- Run the selected native executable with argv `queue --thread UUID --message WAKE_PROMPT`; never `--resume`, a shell, a new exec or a writer-lock bypass. Probe `queue --help` once per binary version; unsupported binaries fail explicitly.
- `queue-wakes.json` is private local state under `REASON_CHAT_HOME`. A cross-process lock serializes dispatch. Atomic write-through stores the complete ID batch and `intent` **before** invoking the queue command. Keep this journal; deleting it loses duplicate protection.
- States: `intent → queued → done`; crash, timeout, nonzero exit or 10 minutes unread produces `held`. No automatic/manual resend of any recorded ID. One outstanding batch per address; new IDs wait for its read confirmation.
- `queued` means the command returned success, with bounded stdout retained as a receipt. Only every exact original ID having `read_at != null` in the read-only Reason DB proves `done`. Missing rows do not prove reading. A held batch can become done on later read evidence.
- Completed IDs remain in the journal. Corrupt/unreadable history blocks dispatch and surfaces `wakeError`; chats and unrelated controls remain available. Restore access or repair the preserved history, never delete it to retry. Failed intent persistence blocks dispatch; a failed receipt write leaves the durable intent held on recovery.
- Auto-wake remains opt-in, 60 seconds apart, 12 per hour. Queue attempts count before dispatch and survive restart. FYI/held Reason messages do not trigger a batch. Metadata polling never calls a model.
- Unlocked threads retain detached exec-resume recovery in `wakes.json`. An outstanding queue batch blocks that fallback too. No existing workers are restarted or changed.

`tests/test_queue_wake.py` covers receipt/read separation, restart/manual deduplication, batches, busy/remote rejection, crash/timeout/disk failures, unsupported queue, missing rows, limits and concurrent dispatch. Queue calls are faked; the SQLite fixture is opened with `mode=ro` by Waker. Installed CLI capability is checked separately without sending a message.
