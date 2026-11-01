# Status

The orchestrator's one-page dashboard. It is the first file each session
reads. Keep it current and under ~80 lines. History belongs in git, handoffs
and decision records, not here.

## Current

- **Phase:** 0 - Foundations, not started. The platform is pinned and the
  pack is initialised (template); the runtime is not set up yet.
- **Item:** none.
- **Pack:** "Untitled Pack" 0.0.1 (placeholder name), Minecraft 1.21.1,
  NeoForge 21.1.265, no mods. Namespace undecided.

## Deployed

- **Ports:** not allocated (`infrastructure/project.env` is blank).
- **Dev server:** not installed.
- **Headless client:** not installed.
- **Pack host (`scripts/serve.sh`):** stopped.
- **Recipe index:** not built.

## Open debt

- None.

## Waiting on owner

- Nothing.

## Last session

- None yet: this repo was copied from the experiment template.

## Next action

Start Phase 0 (`docs/roadmap.md` → "Phase 0 - Foundations") with the
runtime setup item: allocate ports, install the dev server and headless
client, and boot the empty pack.
