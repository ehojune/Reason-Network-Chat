# Task ownership gate

Use `python rnc.py assignment` for changes of implementation ownership. The local registry is shared by
Claude and Codex; it neither sends messages nor edits Reason's database/queues. Keep it outside Git.

1. Lead: `assignment list`, then `assignment claim ISSUE_URL --owner worker1 --revision 0 --path src --repo-root WORKTREE`.
   Use the current revision for an existing task. A claim returns a new revision. Default scope `.` reserves
   the repository; literal relative files/directories permit disjoint work in separate tasks. No globs.
2. Dispatch once with the task URL, returned revision, owner and scope. A failed claim is not a new assignment.
3. Worker: run from the registered checkout, then `assignment begin ISSUE_URL --owner worker1 --revision 1 --repo-root WORKTREE` **before editing**. Refusal means stop
   and report to the lead. A stale queued assignment or duplicate begin cannot acquire the task again.
4. Before each file edit and before commit/push: `assignment check ISSUE_URL --owner worker1 --revision 1 --path src/file.py --repo-root WORKTREE`
   for the files being changed. Finish only after all writes/processes end:
   `assignment finish ISSUE_URL --owner worker1 --revision 1 --note "PR URL; preserved local changes"`.
5. Lead: claim with the current revision and a handoff note. Handoff is refused while the previous assignment
   is working, an active former owner or the new owner is busy/unavailable, or their queues contain requests (including cancellation).
   Drain/reconcile those requests first; do not delete a queue or force a restart to pass the check.
   A completed former owner need not still be running; its old revision cannot begin again.

Claims use one file lock, durable atomic replacement, monotonic revisions and overlap checks across the same
GitHub repository, regardless of worktree location. State is `assigned → working → done`; no timeout silently
releases ownership. A crash leaves the claim held. Inspect saved work/processes before an authorized operator
records finish; it is not evidence that the work succeeded. Prior transitions remain in `assignments.json`.
Overlap checks conservatively ignore case and Unicode composition on every platform, so aliased scopes are refused even
on case-sensitive volumes. File containment retains exact case outside Windows. Claims require a managed
launcher's verified PID/birth/serve identity, stable native status and empty queues. Persistent Claude agent
processes and Windows console hosts are not themselves busy evidence. Before a listener has native status,
only its console host may be present; an agent child makes that fallback unavailable.
Queue checks count unanswered requests, preserve answered history, and accept a missing first-use queue;
unreadable or malformed existing queues are refused. The native session needs no web-only worker flag.
Scoped parallel claims require the worker's checkout root and a matching GitHub origin. Scope ancestors and
contents must be free of symlinks, Windows reparse points and hard-linked files; begin/check revalidate them.
Existing Windows 8.3 aliases are expanded to their long paths before overlap and file-containment checks.
The registered checkout is retained in the claim. A whole-repository `.` claim needs no checkout argument.
For scoped claims, begin/check require both an explicit matching checkout argument and that checkout as cwd;
they cannot silently inspect a different worktree. Worker launch folders may differ from their code checkout.

This is a **cooperative coordination gate**, not an OS sandbox or authenticated user boundary. Plain chat,
direct editor writes, and commands that omit the gate are not intercepted. Leads must use it for assignments
and workers must call begin/check. It cannot retract an instruction from a model already running. For such
turns, preserve work and wait for a verified stop before transferring ownership.
