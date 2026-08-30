"""Builds a worked example repository.

The story is a small NEMA-17 motor bracket going through a week of revisions.
It was chosen because it exercises every part of kerf. There is a parameter
edit that changes the solid, a re-export that changes nothing, two people
working in parallel on separate features, and a merge that succeeds on the
feature tree while the geometry collides.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import time

import numpy as np

from .formats import stl as stl_fmt
from .parametric import Part
from .repo import Repo

# --------------------------------------------------------------- content

BRACKET_V1 = {
    "kerf_part": 1,
    "name": "nema17-bracket",
    "units": "mm",
    "parameters": {
        "plate_w": 60, "plate_d": 46, "plate_t": 5,
        "bolt_d": 3.4, "bolt_pitch": 31, "bore_d": 22,
        "wall_t": 5, "rise": 40,
    },
    "features": [
        {"id": "base", "type": "box", "op": "add", "name": "base plate",
         "size": ["plate_w", "plate_d", "plate_t"], "center": [0, 0, "plate_t/2"],
         "round": 2},
        {"id": "riser", "type": "box", "op": "add", "name": "riser wall",
         "size": ["plate_w", "wall_t", "rise"],
         "center": [0, "plate_d/2 - wall_t/2", "rise/2"], "round": 2, "blend": 3},
        {"id": "face", "type": "box", "op": "add", "name": "motor face",
         "size": ["plate_w", "wall_t", 42],
         "center": [0, "plate_d/2 - wall_t/2", "rise - 6"], "round": 2},
        {"id": "bore", "type": "cylinder", "op": "subtract", "name": "motor bore",
         "radius": "bore_d/2", "height": 40, "axis": "y",
         "center": [0, "plate_d/2 - wall_t/2", "rise - 6"]},
        {"id": "bolt_a", "type": "cylinder", "op": "subtract", "name": "motor bolt NW",
         "radius": "bolt_d/2", "height": 40, "axis": "y",
         "center": ["-bolt_pitch/2", "plate_d/2 - wall_t/2", "rise - 6 + bolt_pitch/2"]},
        {"id": "bolt_b", "type": "cylinder", "op": "subtract", "name": "motor bolt NE",
         "radius": "bolt_d/2", "height": 40, "axis": "y",
         "center": ["bolt_pitch/2", "plate_d/2 - wall_t/2", "rise - 6 + bolt_pitch/2"]},
        {"id": "bolt_c", "type": "cylinder", "op": "subtract", "name": "motor bolt SW",
         "radius": "bolt_d/2", "height": 40, "axis": "y",
         "center": ["-bolt_pitch/2", "plate_d/2 - wall_t/2", "rise - 6 - bolt_pitch/2"]},
        {"id": "bolt_d", "type": "cylinder", "op": "subtract", "name": "motor bolt SE",
         "radius": "bolt_d/2", "height": 40, "axis": "y",
         "center": ["bolt_pitch/2", "plate_d/2 - wall_t/2", "rise - 6 - bolt_pitch/2"]},
        {"id": "mount_l", "type": "cylinder", "op": "subtract", "name": "chassis screw L",
         "radius": 2.6, "height": 30, "axis": "z", "center": [-22, -14, 0]},
        {"id": "mount_r", "type": "cylinder", "op": "subtract", "name": "chassis screw R",
         "radius": 2.6, "height": 30, "axis": "z", "center": [22, -14, 0]},
    ],
}

SPACER = {
    "kerf_part": 1,
    "name": "shaft-spacer",
    "units": "mm",
    "parameters": {"od": 16, "id": 8.2, "length": 12},
    "features": [
        {"id": "body", "type": "cylinder", "op": "add", "name": "body",
         "radius": "od/2", "height": "length", "axis": "z"},
        {"id": "bore", "type": "cylinder", "op": "subtract", "name": "shaft bore",
         "radius": "id/2", "height": "length + 4", "axis": "z"},
    ],
}


def _write(root: str, rel: str, data: bytes) -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def _part_bytes(doc: dict) -> bytes:
    return (json.dumps(doc, indent=2) + "\n").encode()


def _housing_stl(bore: float = 9.0, seed: int = 1) -> bytes:
    """A mesh part, in the form it arrives from a CAD system, as an export."""
    doc = {
        "kerf_part": 1, "name": "idler-housing", "units": "mm",
        "parameters": {"bore": bore},
        "features": [
            {"id": "body", "type": "box", "op": "add",
             "size": [34, 34, 14], "round": 4},
            {"id": "hub", "type": "cylinder", "op": "add",
             "radius": 13, "height": 20, "axis": "z", "blend": 2},
            {"id": "bore", "type": "cylinder", "op": "subtract",
             "radius": "bore", "height": 40, "axis": "z"},
            {"id": "slot", "type": "box", "op": "subtract",
             "size": [3, 40, 30], "center": [0, 0, 0]},
        ],
    }
    mesh = Part.loads(_part_bytes(doc)).evaluate(46)
    return stl_fmt.dump_binary(mesh, header=f"idler-housing export seed={seed}".encode())


def _reexport(data: bytes, jitter: float = 2e-6, seed: int = 7) -> bytes:
    """Write an unchanged part again the way a CAD system would.

    The solid is the same. The facet order is shuffled, the header carries a
    new stamp, and every coordinate moves by less than the tolerance. Git sees
    a new file and kerf sees no design change.
    """
    mesh = stl_fmt.load(data)
    rng = random.Random(seed)
    order = list(range(len(mesh.faces)))
    rng.shuffle(order)
    mesh.faces = mesh.faces[order]
    span = float(np.linalg.norm(mesh.bbox()[1] - mesh.bbox()[0]))
    noise = (np.random.default_rng(seed).random(mesh.vertices.shape) - 0.5) * span * jitter
    mesh.vertices = mesh.vertices + noise
    return stl_fmt.dump_binary(mesh, header=f"idler-housing export {time.time():.0f}".encode())


# ------------------------------------------------------------- the story


def build_demo(root: str, quiet: bool = False) -> Repo:
    def say(text: str = "") -> None:
        if not quiet:
            print(text)

    if os.path.exists(root):
        shutil.rmtree(root)
    os.makedirs(root)
    repo = Repo.init(root, author="dana")
    say(f"created {root}/.kerf  (author: dana)")

    # -- revision 1 ----------------------------------------------------
    _write(root, "parts/bracket.kpart", _part_bytes(BRACKET_V1))
    _write(root, "parts/spacer.kpart", _part_bytes(SPACER))
    housing = _housing_stl()
    _write(root, "parts/idler-housing.stl", housing)
    _write(root, "README.md", b"# Y-axis assembly\n\nNEMA-17 bracket, idler housing, spacer.\n")
    repo.add(["parts", "README.md", ".kerfignore"])
    r1 = repo.commit("initial release of the Y-axis bracket assembly")
    say(f"  r1 {r1[:10]}  initial release")

    # -- revision 2: a real design change ------------------------------
    v2 = json.loads(json.dumps(BRACKET_V1))
    v2["parameters"]["plate_t"] = 7            # thicker base
    v2["parameters"]["bolt_d"] = 3.6           # clearance for M3 socket heads
    v2["features"].insert(3, {
        "id": "gusset", "type": "box", "op": "add", "name": "corner gusset",
        "size": [8, 26, 26], "center": [0, 4, 13],
        "rotate": [0, 0, 0], "round": 1, "blend": 4,
    })
    _write(root, "parts/bracket.kpart", _part_bytes(v2))
    repo.add(["parts/bracket.kpart"])
    r2 = repo.commit(
        "stiffen the bracket\n\nPrints were flexing under belt tension: thicker base plate\n"
        "and a gusset behind the riser. Bolt holes opened up for socket heads."
    )
    say(f"  r2 {r2[:10]}  stiffen the bracket (plate_t 5->7, gusset added)")

    # -- revision 3: a re-export that changes nothing -------------------
    _write(root, "parts/idler-housing.stl", _reexport(housing))
    repo.add(["parts/idler-housing.stl"])
    r3 = repo.commit("re-export the idler housing from the updated toolchain")
    say(f"  r3 {r3[:10]}  re-export only, recorded as geometrically unchanged")

    # -- two people, two branches ---------------------------------------
    repo.create_branch("bore-fit")
    repo.create_branch("mount-slots")

    repo.checkout("bore-fit")
    v3 = json.loads(json.dumps(v2))
    v3["parameters"]["bore_d"] = 23.5          # the motor boss was a press fit
    v3["features"] = [
        dict(f, radius="bore_d/2") if f["id"] == "bore" else f for f in v3["features"]
    ]
    _write(root, "parts/bracket.kpart", _part_bytes(v3))
    repo.add(["parts/bracket.kpart"])
    b1 = repo.commit("open the motor bore to 23.5 because the boss was a press fit", author="dana")
    say(f"  bore-fit    {b1[:10]}  bore_d 22 -> 23.5")

    repo.checkout("mount-slots")
    v4 = json.loads(json.dumps(v2))
    v4["parameters"]["slot_len"] = 9
    for f in v4["features"]:                    # chassis screws become slots
        if f["id"] in ("mount_l", "mount_r"):
            f["radius"] = 3.0
    v4["features"].append({
        "id": "slot_l", "type": "box", "op": "subtract", "name": "chassis slot L",
        "size": ["slot_len", 6, 30], "center": [-22, -14, 0],
    })
    v4["features"].append({
        "id": "slot_r", "type": "box", "op": "subtract", "name": "chassis slot R",
        "size": ["slot_len", 6, 30], "center": [22, -14, 0],
    })
    _write(root, "parts/bracket.kpart", _part_bytes(v4))
    repo.add(["parts/bracket.kpart"])
    b2 = repo.commit("slot the chassis mounts so belt tension can be set", author="rui")
    say(f"  mount-slots {b2[:10]}  chassis screws become 9 mm slots")

    # -- a branch that will collide -------------------------------------
    repo.checkout("main")
    repo.create_branch("cable-tie")
    repo.checkout("cable-tie")
    v5 = json.loads(json.dumps(v2))
    v5["features"].append({
        "id": "tie_slot", "type": "box", "op": "subtract", "name": "cable tie slot",
        "size": [4, 30, 12], "center": [22, -14, 6],
    })
    _write(root, "parts/bracket.kpart", _part_bytes(v5))
    repo.add(["parts/bracket.kpart"])
    b3 = repo.commit("cable tie slot on the right hand side", author="rui")
    say(f"  cable-tie   {b3[:10]}  adds a slot right where the chassis mount lives")

    repo.checkout("main")
    say()
    say("branches: main, bore-fit, mount-slots, cable-tie")
    say("try:")
    say("  kerf log --stat")
    say("  kerf diff HEAD~1 HEAD")
    say("  kerf merge bore-fit          # one parameter, fast-forward")
    say("  kerf merge mount-slots       # parallel feature edits, merged per feature")
    say("  kerf merge cable-tie         # now collides with the slots just merged")
    say("  kerf report HEAD~2 HEAD -o report.html")
    return repo
