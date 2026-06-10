# Weekly Review / Memory Compaction Prompt

<!-- TODO (Phase 4): Write the full weekly review prompt. -->
<!-- This prompt drives: observation promotion/expiry, stale thesis flagging, self-review note. -->

You are reviewing your own work from the past week for the topic: {topic_name}.

## Tasks

1. **Promote durable observations.** Review active observations that are importance=3, have been referenced across multiple days, or underpin an active thesis. Merge them into the dossier. Mark them `promoted`.

2. **Expire stale observations.** Mark `expired` any observation older than 30 days (importance 1) or 90 days (importance 2) that has not been promoted.

3. **Flag untouched theses.** Identify any active thesis with `updated_at` older than 30 days. Add it to your `open_questions` with a note: "Thesis [ID] untouched for 30 days — revisit or retire."

4. **Write a self-review note.** One short paragraph appended to the dossier: what you got right this week, what you got wrong, what you're watching. Keep it under 200 words.

Return a `WeeklyReviewOutput` JSON object (to be defined).
