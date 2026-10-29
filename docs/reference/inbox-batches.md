# Queued Codex message batches

Opt-in shim feature; no new receiver, model, service or dependency. Existing `serve` processes and model settings stay in place. Only Codex JSON executions containing a Reason message are eligible.

## Enable and inspect

After updating the checkout, refresh the shared shim with `python -c "import launcher; launcher.shim_dir('codex'); assert launcher.shim_current('codex')"`. If a running turn holds the executable open, wait for it to finish; do not kill it.

```powershell
python inbox_batch.py enable --settings "$env:USERPROFILE/.reason-network-chat/worker-settings/my-lead.json" --recipient me/my-lead --person me/terminal --room ROOM_ID
python inbox_batch.py status --settings "$env:USERPROFILE/.reason-network-chat/worker-settings/my-lead.json"
python inbox_batch.py disable --settings "$env:USERPROFILE/.reason-network-chat/worker-settings/my-lead.json"
```

Custom installations also pass `--chat-home` and `--reason-home` when enabling. Only configure a Codex worker. `enable` preserves model arguments and sends nothing; `disable` retains existing receipts. Never delete the settings entry or journal to disable batching.

## Contract

- At the next turn, snapshot the current request and pending requests in the **same allowed room**. Cross-room messages and DMs remain separate; active turns are not interrupted.
- Validate ID, sender, recipient and complete body against read-only Reason SQLite; room membership and human provenance come from local relay records. Quoted names do not grant priority.
- Verified human requests come first, newest first; agent reports follow chronologically. The default limit is 24 messages / 160 KB of records. Always retain the active request and newest pending human instruction even if those two exceed the byte limit, so a large old report cannot hide a stop instruction. Never truncate a body; leave other overflow in Reason's queue.
- Preserve originals, timestamps and IDs before invoking Codex once. Journal commits fsync file contents and POSIX ancestor directories, or use Windows write-through replacement. A failed persistence step prevents model execution. The model must consider each request, honor newer instructions/stop conditions, and return a receipt listing every included ID.
- Model input stores identical envelope lines once in `wrapper_lines`, with ordered references per message. Identical history blocks share a `contexts` entry; different histories, delivery IDs, routing rules and complete message bodies remain intact. Local relay core metadata establishes the boundaries. Each expanded message must equal its journal original exactly; unknown formats remain verbatim. This reduces repeated text, not the original record or its authority checks.
- Cache a successful answer before emitting it. Later included deliveries invoke no model and return `-`; they never republish old decisions. The full answer must explicitly mention members who need a new decision; per-message implicit returns cannot route the whole batch.
- Model failure, missing receipt or interrupted execution becomes **held**, retaining all originals and any captured answer. Never automatically rerun work whose effects are uncertain. A model receipt proves acknowledged input, not that every requested task succeeded.
- Reason owns its queue and database throughout. No queue edit, synthetic database receipt, worker restart or automatic development resumption occurs.

## Recovery

`status` lists held batches and completed-but-unpublished results. `export --batch ID --settings PATH` prints the full private journal entry for inspection. Check actual side effects and Reason replies before manually resuming only unfinished work or publishing a cached result through the normal authorized room flow. There is deliberately no blind retry command. Keep the held entry as evidence; never delete it to force execution. A crash after the final queued delivery can leave an unpublished cached result requiring this operator action.

Journals contain original private messages; keep them local, out of Git. Snapshots exclude later arrivals. Batching reduces repeated turns; it cannot fix provider latency within a turn or guarantee exactly-once external side effects across crashes.

## Verified publication and history

Pass `--publisher PATH_TO_NATIVE_REASON_NETWORK` when enabling to send the first fresh answer through native stdin. The journal records intent before sending and verifies the exact reply in the read-only database. An uncertain send is retained without automatic retry. The normal serve response is only `-`. Without this option the first answer still uses serve.

API22 exposes `batchReceipts`: each verified input points to its representative reply or a locally saved/held result. The UI keeps saved answers as escaped, non-routing history, separate from unanswered requests. Batch inputs cannot be resent through `/api/resend`; no old instruction or answer is replayed. Missing/corrupt evidence leaves requests visible.
