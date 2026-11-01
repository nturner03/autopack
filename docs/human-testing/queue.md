# Human test queue

Requests for checks only the owner can do. Agents append to **Pending** and
keep working on whatever doesn't depend on the answer. The owner fills in
**Results**. The orchestrator turns results into work and moves the request
to **Done**. Setup and reporting are described in [README.md](README.md).

## Request template

Copy this under Pending. Ids are `HT-NNN`, numbered in sequence and never
reused.

```markdown
### HT-NNN: <short title>

- **Queued:** YYYY-MM-DD by <agent / session>
- **Build:** pack <version> (git tag `v<version>`). Pack host started: yes/no
- **Feeds decision:** <what this result decides; decision record or roadmap item>
- **Time needed:** ~<minutes>
- **Setup:** <instance changes, world/coords, items or commands to start from>
- **Steps:**
  1. <exact action>
  2. ...
- **Look for:**
  - <specific question, e.g. "Is the act 2 gate clear without the quest book?">
- **Results** (owner):
  <!-- build played, time taken, what you saw per "look for" point, other notes -->
```

## Pending

None.

## Done

None.
