# Art source formats

Examples use the made-up namespace `mypack`; use the pack namespace.

`scripts/texture.py` reads these. A source's path under `art/assets/`
decides where it builds (same path under `packwiz/kubejs/assets/`, as
`.png`). Wherever a format takes a texture (`from`), it accepts a texture
id (`minecraft:block/tuff`, `mypack:item/example_item`), a PNG path, or
another art source path (rendered first).

## `.grid`: a texture as text

```
# mypack:item/example_item - body from the copper ingot, swirl inlay
frametime 4            # optional: animated, ticks per frame
interpolate false      # optional
. = transparent        # '.' is transparent unless redefined
a = #2f527f            # one symbol per colour, dark to light by convention
b = #576c9d
c = #b5a5ca
d = #e3826c80          # 8 hex digits = with alpha (items avoid partial alpha)

................
......aaaa......
.....abbcba.....
...                    (16 rows of 16 symbols)
---                    # next animation frame, same size
...
```

- Header lines (`#` comments, `symbol = colour`, `frametime`,
  `interpolate`) come before the first row. `#`, `=` and spaces can't be
  symbols.
- Every row has the same width; every frame the same size. 16x16 for
  vanilla-scale items and blocks.
- `to-grid` assigns `a`, `b`, `c`... from darkest to lightest, so `a` is
  the outline or deepest shadow and later letters are highlights. Keep
  that order when you add colours: it makes the shading readable in the
  text.
- Edit a few rows at a time and re-preview. Re-read the whole grid after
  big edits to catch row-length mistakes (`render` reports the frame,
  row and column of a bad symbol).

## `.derive.json`: recolour and layer

```json
{
  "from": "minecraft:item/copper_ingot",
  "frame": 0,
  "ops": [
    {"op": "ramp", "ramp": "storm"},
    {"op": "overlay", "from": "art/assets/mypack/textures/item/_inlay.grid", "x": 0, "y": 0}
  ]
}
```

`frame` (optional) takes one frame of an animated base; otherwise every
frame gets the ops and the base's `.mcmeta` is kept (or set `"mcmeta"`).

| Op | Fields | Does |
|---|---|---|
| `ramp` | `ramp` (name in `art/palette.json`, or a list of hex), `only` (list of hex, optional), `mode` (`rank` or `luma`) | gradient-maps the source's colours, dark to light, onto the ramp. `rank` (default when the ramp has enough shades) keeps every source shade distinct; `luma` maps by brightness |
| `hsv` | `h` (degrees), `s`, `v` (multipliers) | shifts hue, scales saturation and value |
| `replace` | `map` `{"#from": "#to"}` | exact colour swaps |
| `overlay` / `underlay` | `from`, `x`, `y`, `ops` (applied to the layer first) | draws a layer over (or under) the image |
| `mask` | `from`, `keep` (`opaque` or `transparent`) | keeps only pixels where the mask is opaque (or transparent) |
| `outline` | `color`, `diagonal` | adds a 1 px outline around opaque pixels |
| `flip` | `axis` (`x` or `y`) | mirrors |
| `rotate` | `turns` (quarter turns clockwise) | rotates |
| `shift` | `x`, `y` | moves the pixels, filling with transparency |
| `set` / `erase` | `pixels` `[[x, y], ...]`, `color` | single-pixel fixes |

Small fixes on a derive can use `set`/`erase`; more than a handful means
it's time to `to-grid` it and edit the grid instead.

Layer detail you'll reuse (an inlay, a rune, a glow) can go in helper
sources whose names start with `_` (e.g. `_inlay.grid`). They build to the
pack like any source; keep them small.

## `.compose.json`: UI art

```json
{
  "size": [512, 256],
  "background": {"gradient": ["#1d2430", "#0c0f14"]},
  "layers": [
    {"from": "art/captures/scene.png", "fit": "cover", "brightness": 0.55, "saturation": 0.7, "blur": 1},
    {"from": "art/captures/subject_cutout.png", "scale": 2, "anchor": "center", "x": 140, "y": 10},
    {"from": "<ns>:item/<name>", "scale": 6, "x": 24, "y": 150, "opacity": 0.8}
  ],
  "vignette": 0.5,
  "pixelate": 2,
  "quantize": "palette"
}
```

- `background`: a colour, `transparent`, or `{"gradient": [top, bottom]}`.
- Layers draw in order. `fit` (`cover` or `contain`) scales to the canvas;
  otherwise `scale`. `resample` is `nearest` (default; keeps pixels crisp)
  or `smooth` (for downscaling captures). Position: `x`, `y` is the
  top-left corner, or an offset from the centre with `"anchor": "center"`
  (the default for fitted layers). Optional per layer: `crop` `[l, t, r, b]`,
  `ops` (derive ops), `brightness`, `saturation`, `tint` +
  `tint_strength`, `blur`, `opacity`.
- Whole image: `vignette` (0-1), `pixelate` (block size, for a pixel-art
  look), `quantize` (a colour count, or `"palette"` for `art/palette.json`).
- Text is not drawn: titles and labels belong in lang files and the
  quest book, where they can be translated and stay readable.

## `.png`: copied as is

For finished images that need no processing: studio panorama faces, or a
capture already the right size. Keep its `.png.mcmeta` beside it if it's
animated.

## `art/palette.json` (pack-designer)

```json
{
  "max_colors": 24,
  "namespaces": ["mypack"],
  "ramps": {
    "ramp_a": ["#6d3421", "#9c4529", "#c15a36", "#e77c56", "#fc9982"],
    "ramp_b": ["#2f527f", "#3e5e87", "#576c9d", "#7a82c4", "#b5a5ca"]
  },
  "extra": ["#1b1b1f"]
}
```

`ramps` are dark-to-light lists. `lint` warns when a texture in one of the
`namespaces` uses a colour outside the ramps and `extra`, or more than
`max_colors` colours. Sample vanilla ramps with
`texture.py ramp <texture-id> -n 5`.
