# Examples

Two sample parts, taken from the worked demo.

- `nema17-bracket.kpart` is the part the demo revises. It has a base plate, a riser, a motor face, a bore, four motor bolts, and two chassis screws.
- `shaft-spacer.kpart` is the smallest useful part, which is a tube with a bore through it.

Render one to an HTML page.

```bash
kerf view examples/nema17-bracket.kpart -o bracket.html
```

Or build the whole demo repository, which includes branches and a merge that collides.

```bash
kerf demo my-demo
```

The same parts drive the [browser playground](https://pragyaangaur.github.io/Kerf/), where they live in `web/parts`.
