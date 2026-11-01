# Human testing

The agents verify everything they can themselves on the dev server and the
headless client. The owner is asked only for what a person has to judge: fun,
pacing over real hours, difficulty feel, visual taste, readability on a normal
client, and performance on real hardware. Requests and results go in
[queue.md](queue.md).

## One-time client setup (Prism Launcher)

1. Create a new instance with **Minecraft 1.21.1** and **NeoForge** at the
   build in `packwiz/pack.toml` → `[versions] neoforge` (21.1.265 in the
   template; each request names the build).
2. Download `packwiz-installer-bootstrap.jar` from
   <https://github.com/packwiz/packwiz-installer-bootstrap/releases> and put
   it in the instance's game folder (Prism: right-click the instance →
   *Folder* → `minecraft/`, or `.minecraft/`).
3. Instance → *Edit* → *Settings* → *Custom commands*: enable them and set
   the **pre-launch command** to

   ```
   "$INST_JAVA" -jar packwiz-installer-bootstrap.jar http://<LAN_HOST>:<SERVE_PORT>/pack.toml
   ```

   `LAN_HOST` and `SERVE_PORT` are in `infrastructure/project.env` (a blank
   `LAN_HOST` means the host's first address, `hostname -I`); `scripts/serve.sh`
   prints the full URL when it starts. Each launch then updates the instance to the build the agents are serving.
   If the pack host isn't running, the update fails and the launch stops.
   Re-launch once the request says the host is up.
4. Give the instance enough memory (*Settings* → *Java*, e.g. 6-8 GB) once the
   pack has real content.

If a request says the NeoForge build changed, set the instance's NeoForge
version to match before launching.

## Joining the dev server

- Address: `<LAN_HOST>:<GAME_PORT>` (`infrastructure/project.env`).
- The server runs in offline mode, so any username works.
- The world is the agents' disposable test world. It can be reset between
  builds, and agents won't restart it while a non-bot player is online.
- `PexpBot` is the agents' headless client. You may see it in the player
  list.

## When requests are queued

When an agent queues a request, it bumps the pack version, tags the commit
`v<version>`, and starts the pack host (`scripts/serve.sh`, `SERVE_PORT`) so
your launch picks up that build. Requests say which build they need. Check
the pack version on the title screen or in `packwiz/pack.toml`.

## Reporting results

1. Open [queue.md](queue.md) and find the request by its id.
2. Fill in its **Results** field:
   - the build you played;
   - what you did and how long it took;
   - what you saw against each "look for" point;
   - anything else you noticed (bugs, confusion, things you enjoyed or
     disliked);
   - screenshot paths if useful (put images in `docs/human-testing/` next to
     this file).
3. Start the next session with `/pack-orchestrate continue` (or
   `/pack-orchestrate process my playtest notes`). The orchestrator reads
   results first and turns them into work before starting new features. It
   moves finished requests to **Done**.

Plain notes are fine; no format is enforced inside Results.
