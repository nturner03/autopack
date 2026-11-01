# art/

Sources for every image the pack ships. `scripts/texture.py build` turns
them into `packwiz/kubejs/assets/`; nothing in this folder ships itself.
Method, formats and the quality bar: the `pack-art` skill
(`.claude/skills/pack-art/`). Whether the pack uses agent-made art is set in
`docs/charter.md`.

| Path | Holds | Owner |
|---|---|---|
| `palette.json` | art direction ramps and limits (`docs/design/art.md` explains them). Ships empty: pack-designer adds the pack namespace to `namespaces` and the ramps when it writes the art direction | pack-designer |
| `assets/<ns>/textures/<path>.grid` | a texture as a text grid | pack-artist |
| `assets/<ns>/textures/<path>.derive.json` | a texture derived from another (recolour, layers) | pack-artist |
| `assets/<ns>/textures/<path>.compose.json` | UI art layered from captures and textures | pack-artist |
| `assets/<ns>/textures/<path>.png` | a finished image copied as is (e.g. panorama faces) | pack-artist |
| `captures/<name>.png` | studio captures used by `.compose.json` sources | pack-artist |

```sh
python3 -I scripts/texture.py build          # sources -> packwiz/kubejs/assets
python3 -I scripts/texture.py lint           # also run by scripts/check_pack.py
```
