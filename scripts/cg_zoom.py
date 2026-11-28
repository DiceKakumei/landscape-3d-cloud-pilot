# 寄り続けるCGアニメ（海の貝の真珠 → 夜の街の洋菓子店の窓 → お菓子のテーブルの苺の水滴 → 海…の縦型ループ）
# blender --background --python scripts/cg_zoom.py -- <出力dir> <フレーム "0,60" or "0-23"> [横px=720] [samples=24]
# 仕組み：次の世界は、今の世界にある物（真珠・店の窓・水滴）の中に映る。寄りは3Dを毎回描き直す
#   （焦点距離とシフトで画面の一部だけを実解像度で描画）ので拡大してもぼけない。重ね合わせはnumpy。
import math
import os
import random
import sys
import tempfile

import bmesh
import bpy
import numpy as np
from mathutils import Vector, noise

argv = sys.argv[sys.argv.index("--") + 1:]
OUT = os.path.abspath(argv[0])
if argv[1] == "blend":         # .blendファイルの書き出し
    FRAMES = None
elif "-" in argv[1]:
    a, b = map(int, argv[1].split("-"))
    FRAMES = range(a, b + 1)
else:
    FRAMES = [int(v) for v in argv[1].split(",")]
W = int(argv[2]) if len(argv) > 2 else 720
H = W * 16 // 9
SAMPLES = int(argv[3]) if len(argv) > 3 else 24

FPS = 24
PER = [120, 120, 168]          # 世界ごとのフレーム数（海5秒・夜5秒・お菓子7秒）
# 次の世界が入る物。pos/大きさは画面の横幅=1の座標（原点は中央、上が+）。seenは引きの状態で中が見える濃さ
PORTALS = [
    dict(kind="pearl", pos=(0.0, -0.22), r=0.11, seen=0.10),
    dict(kind="window", pos=(0.0, -0.29), w=0.21, seen=1.0),
    dict(kind="drop", pos=(0.075, -0.25), r=0.0055, seen=0.08),
]
# 次の世界の縮尺。丸は寄り切ると画面の対角(1.02)を覆う。窓は画面と同じ縦横比なので幅そのもの
for q in PORTALS:
    q["s"] = q["w"] if q["kind"] == "window" else q["r"] / 1.12
    assert q["kind"] == "window" or q["r"] / q["s"] > math.hypot(0.5, 8 / 9)
CAM_D, LENS = 30.0, 108.0      # 距離30で画面の横幅=10

TAU = math.tau
rnd = random.Random(7)


# ---------- 部品 ----------
def lin(hexcode):
    return tuple((int(hexcode[i:i + 2], 16) / 255) ** 2.2 for i in (0, 2, 4)) + (1,)


_mats = {}


def mat(color, rough=0.45, emit=0.0, metal=0.0, alpha=1.0, coat=0.0, sss=0.0):
    key = (color, rough, emit, metal, alpha, coat, sss)
    if key not in _mats:
        m = bpy.data.materials.new(color)
        m.use_nodes = True
        p = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        for name, v in (("Base Color", lin(color)), ("Roughness", rough), ("Metallic", metal),
                        ("Alpha", alpha), ("Coat Weight", coat), ("Subsurface Weight", sss),
                        ("Emission Color", lin(color)), ("Emission Strength", emit)):
            p.inputs[name].default_value = v
        _mats[key] = m
    return _mats[key]


def link(sc, ob, loc=(0, 0, 0), scale=(1, 1, 1), rot=(0, 0, 0), parent=None):
    ob.location, ob.scale, ob.rotation_euler, ob.parent = loc, scale, rot, parent
    sc.collection.objects.link(ob)
    return ob


_meshes = {}


def mesh(key, m, build, sharp=40):
    if (key, m.name_full) not in _meshes:
        me = bpy.data.meshes.new(key)
        bm = bmesh.new()
        build(bm)
        bm.to_mesh(me)
        bm.free()
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(sharp))
        me.materials.append(m)
        _meshes[(key, m.name_full)] = me
    return _meshes[(key, m.name_full)]


def add(sc, me, bevel=0, **kw):
    ob = link(sc, bpy.data.objects.new(me.name, me), **kw)
    if bevel:
        mod = ob.modifiers.new("bevel", "BEVEL")
        mod.width, mod.segments = bevel, 4
    return ob


def ball(sc, m, loc, r, scale=(1, 1, 1), **kw):
    me = mesh("ball", m, lambda bm: bmesh.ops.create_icosphere(bm, subdivisions=4, radius=1))
    return add(sc, me, loc=loc, scale=tuple(r * s for s in scale), **kw)


def cyl(sc, m, loc, r1, r2, depth, bevel=0.06, **kw):
    me = mesh(f"cyl{r1}_{r2}_{depth}", m, lambda bm: bmesh.ops.create_cone(
        bm, cap_ends=True, segments=64, radius1=r1, radius2=r2, depth=depth))
    return add(sc, me, bevel=bevel if r2 else 0, loc=loc, **kw)


def box(sc, m, loc, size, bevel=0.08, **kw):
    def build(bm):
        bmesh.ops.create_cube(bm, size=1)
        bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    return add(sc, mesh(f"box{size}", m, build), bevel=bevel, loc=loc, **kw)


def torus(sc, m, loc, major, minor, **kw):
    def build(bm):
        nu, nv = 64, 20
        vs = [[bm.verts.new(((major + minor * math.cos(TAU * j / nv)) * math.cos(TAU * i / nu),
                             (major + minor * math.cos(TAU * j / nv)) * math.sin(TAU * i / nu),
                             minor * math.sin(TAU * j / nv))) for j in range(nv)] for i in range(nu)]
        for i in range(nu):
            for j in range(nv):
                bm.faces.new((vs[i][j], vs[(i + 1) % nu][j], vs[(i + 1) % nu][(j + 1) % nv], vs[i][(j + 1) % nv]))
    return add(sc, mesh(f"torus{major}_{minor}", m, build, sharp=80), loc=loc, **kw)


def tube(sc, m, pts, r, taper=1.0, **kw):
    cu = bpy.data.curves.new("tube", "CURVE")
    cu.dimensions, cu.bevel_depth, cu.bevel_resolution, cu.use_fill_caps = "3D", r, 6, True
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for i, (p, c) in enumerate(zip(sp.points, pts)):
        p.co = (*c, 1)
        p.radius = 1 - (1 - taper) * i / (len(pts) - 1)
    cu.materials.append(m)
    return link(sc, bpy.data.objects.new("tube", cu), **kw)


def empty(sc, **kw):
    return link(sc, bpy.data.objects.new("empty", None), **kw)


def ground(sc, m, z, bump, freq):
    def build(bm):
        bmesh.ops.create_grid(bm, x_segments=220, y_segments=220, size=80)
        for v in bm.verts:
            v.co.y += 45
            v.co.z = bump * noise.noise(Vector((v.co.x * freq, v.co.y * freq, 0.3)))
    add(sc, mesh(f"ground{z}", m, build, sharp=80), loc=(0, 0, z))


def new_scene(name, low, high, strength, sun, sun_color, sun_dir=(50, 25, 0)):
    sc = bpy.data.scenes.new(name)
    wd = bpy.data.worlds.new(name)
    sc.world = wd
    wd.use_nodes = True
    nt = wd.node_tree
    nt.nodes.clear()
    co, sep, rng, ramp, bg, out = (nt.nodes.new("ShaderNode" + n) for n in
                                   ("TexCoord", "SeparateXYZ", "MapRange", "ValToRGB", "Background", "OutputWorld"))
    rng.inputs["From Min"].default_value, rng.inputs["From Max"].default_value = -0.08, 0.36
    ramp.color_ramp.elements[0].color, ramp.color_ramp.elements[1].color = lin(low), lin(high)
    bg.inputs["Strength"].default_value = strength
    for a_, b_ in ((co.outputs["Generated"], sep.inputs[0]), (sep.outputs["Z"], rng.inputs["Value"]),
                   (rng.outputs["Result"], ramp.inputs[0]), (ramp.outputs[0], bg.inputs[0]),
                   (bg.outputs[0], out.inputs[0])):
        nt.links.new(a_, b_)
    cam = bpy.data.cameras.new(name)
    cam.lens, cam.sensor_width, cam.sensor_fit = LENS, 36, "HORIZONTAL"
    sc.camera = link(sc, bpy.data.objects.new(name + "cam", cam), loc=(0, -CAM_D, 0), rot=(math.pi / 2, 0, 0))
    lamp = bpy.data.lights.new(name, "SUN")
    lamp.energy, lamp.color, lamp.angle = sun, lin(sun_color)[:3], math.radians(12)
    link(sc, bpy.data.objects.new(name + "sun", lamp), rot=tuple(map(math.radians, sun_dir)))
    sc.render.engine = "CYCLES"
    sc.cycles.device, sc.cycles.samples = "CPU", SAMPLES
    sc.cycles.use_denoising, sc.cycles.denoiser = True, "OPENIMAGEDENOISE"
    sc.cycles.max_bounces, sc.cycles.transparent_max_bounces = 5, 12
    sc.cycles.sample_clamp_indirect = 4
    sc.render.use_persistent_data = True
    sc.render.image_settings.file_format = "PNG"
    sc.view_settings.view_transform = "Standard"
    return sc


def point(sc, loc, color, energy, size=1.0):
    lamp = bpy.data.lights.new("p", "POINT")
    lamp.energy, lamp.color, lamp.shadow_soft_size = energy, lin(color)[:3], size
    link(sc, bpy.data.objects.new("p", lamp), loc=loc)


# ---------- 世界1：水滴の中（水中） ----------
def underwater():
    sc = new_scene("water", "1f8fb0", "06245c", 0.9, 3.2, "bff4ff", (35, 20, 0))
    anim = []
    ground(sc, mat("c9b489", 0.9), -6.4, 1.1, 0.16)
    for _ in range(46):  # 岩
        x, y = rnd.uniform(-16, 16), rnd.uniform(-5, 24)
        ball(sc, mat(rnd.choice(["3f5f73", "52707d", "2f4a66"]), 0.8), (x, y, -6.3), rnd.uniform(0.4, 1.5),
             scale=(1.3, 1, rnd.uniform(0.5, 0.9)), rot=(0, 0, rnd.uniform(0, 3)))

    def branch(base, d, length, r, depth, m):
        end = base + d * length
        tube(sc, m, [base, base.lerp(end, 0.5) + Vector((rnd.uniform(-.2, .2), rnd.uniform(-.2, .2), 0)), end], r, 0.7)
        if depth:
            for _ in range(rnd.randint(2, 3)):
                nd = (d + Vector((rnd.uniform(-.8, .8), rnd.uniform(-.5, .5), rnd.uniform(0, .5)))).normalized()
                branch(end, nd, length * 0.75, r * 0.7, depth - 1, m)
        else:
            ball(sc, m, tuple(end), r * 1.15)

    for x, y, c, L in [(-3.9, -3, "ff6f91", 1.2), (3.8, -1, "ff9a4d", 1.35), (-6.5, 6, "c77dff", 1.9),
                       (6.8, 9, "ff5d73", 2.0), (1.8, -5.2, "ffd166", 0.6), (-1.9, 8, "ff8fab", 1.3),
                       (11, 3, "c77dff", 1.6), (-11, 1, "ff9a4d", 1.6)]:
        branch(Vector((x, y, -6.3)), Vector((0, 0, 1)), L, L * 0.17, 3, mat(c, 0.35, 0.12, sss=0.3))

    kelp = []
    for i in range(54):  # 海藻
        x = rnd.choice([-1, 1]) * rnd.uniform(3.6, 17)
        y, h = rnd.uniform(-1, 26), rnd.uniform(3, 9.5)
        m = mat(rnd.choice(["2fbf71", "1f9e6e", "7ad65b"]), 0.5, 0.06)
        kelp.append((tube(sc, m, [(x, y, -6.4)] * 14, rnd.uniform(.09, .2), 0.15), x, y, h, rnd.uniform(0, TAU)))

    def sway(t):
        for ob, x, y, h, ph in kelp:
            for i, p in enumerate(ob.data.splines[0].points):
                f = i / 13
                p.co = (x + math.sin(TAU * 3 * t + ph + f * 4) * 0.9 * f, y, -6.4 + h * f, 1)
    anim.append(sway)

    # 岩の上で開いた貝と真珠
    def valve(hinge, along, up, length, spread, cup, color):
        def build(bm):
            nu, nv = 24, 120
            rows = []
            for i in range(nu + 1):
                u = i / nu
                row = []
                for j in range(nv + 1):
                    a_ = (j / nv - .5) * spread
                    rib = abs(math.sin(j / nv * math.pi * 13))
                    L = length * u * (1 + .05 * rib * u)
                    h = cup * u * u + .22 * rib * u
                    p = Vector(hinge) + Vector((math.sin(a_) * L, 0, 0)) + Vector(along) * (math.cos(a_ * .75) * L) + Vector(up) * h
                    row.append(bm.verts.new(p))
                rows.append(row)
            for i in range(nu):
                for j in range(nv):
                    bm.faces.new((rows[i][j], rows[i][j + 1], rows[i + 1][j + 1], rows[i + 1][j]))
        ob = add(sc, mesh(f"valve{hinge}{along}", mat(color, .3, coat=.7, sss=.2), build, sharp=60))
        mod = ob.modifiers.new("thick", "SOLIDIFY")
        mod.thickness, mod.offset = .14, 0

    valve((0, 1.7, -3.9), Vector((0, -1, .02)).normalized(), (0, 0, 1), 3.5, 2.5, .55, "c98aa6")
    valve((0, 1.9, -3.8), Vector((0, .35, 1)).normalized(), (0, 1, -.35), 3.8, 2.5, .75, "a9759c")
    ball(sc, mat("f3ecf4", .14, .05, metal=.35, coat=1), (0, 0, -2.2), 1.1)
    for x, y, z, r in ((0, .8, -5.5, 1.7), (-2.1, .2, -5.7, 1.3), (2.2, .6, -5.7, 1.35), (-.9, -1.4, -6.0, .9), (1.2, -1.6, -6.1, .85)):
        ball(sc, mat("35546a", .85), (x, y, z), r, scale=(1.25, 1, .75), rot=(0, 0, x))
    point(sc, (-1.2, -3.0, -.6), "fff0f6", 110)

    for c, belly, n, cx, cy, cz, rx, rz, size, speed in [
            ("ffb000", "fff1b8", 7, 0, 3, 2.6, 5.2, 1.0, 0.55, 1), ("ff5a36", "ffd6c2", 4, 0.5, 4, 0.9, 5.0, .5, .55, -1),
            ("39e0d0", "d9fffb", 9, -1, 9, 5.5, 7.0, 1.4, .5, 2)]:
        for j in range(n):
            g = empty(sc)
            ball(sc, mat(c, 0.3, 0.15, coat=.5), (0, 0, 0), size, scale=(1.4, .55, .85), parent=g)
            ball(sc, mat(belly, 0.35, 0.1), (0.05, 0, -0.18 * size), size * .8, scale=(1.5, .6, .6), parent=g)
            tail = cyl(sc, mat(c, 0.4, 0.15), (-1.75 * size, 0, 0), .75 * size, 0, 1.0 * size,
                       scale=(1, .18, 1), rot=(0, math.pi / 2, 0), parent=g)
            for side in (-1, 1):
                ball(sc, mat("ffffff", 0.2, .3), (.85 * size, .44 * size * side, .17 * size), .2 * size, parent=g)
                ball(sc, mat("081224", 0.1), (.93 * size, .59 * size * side, .17 * size), .11 * size, parent=g)
            ph, jit = j / n * (0.55 if abs(speed) == 1 else 1) + rnd.uniform(-.03, .03), rnd.uniform(-1, 1)

            def swim(t, g=g, tail=tail, ph=ph, jit=jit, a_=(cx, cy, cz, rx, rz, speed)):
                cx, cy, cz, rx, rz, speed = a_
                q = TAU * (speed * t + ph)
                g.location = (cx + rx * math.cos(q) + jit * .6, cy + 3 * math.sin(q), cz + rz * math.sin(2 * q) * .4 + jit)
                dx, dy = -rx * math.sin(q) * speed, 3 * math.cos(q) * speed
                g.rotation_euler = (0, 0, math.atan2(dy, dx))
                tail.rotation_euler = (0, math.pi / 2, 0.5 * math.sin(TAU * 30 * t + ph * 20))
            anim.append(swim)

    for x, y, z, s, ph in [(-3.3, 1, 4.9, 1.0, 0), (3.6, 4, 6.4, 1.25, .35), (-6.5, 12, 1.5, 1.1, .7)]:  # クラゲ
        g = empty(sc, scale=(s, s, s))
        jm = mat("ff9ff3", 0.2, 0.75, alpha=0.55)
        dome = ball(sc, jm, (0, 0, 0), 1.0, scale=(1, 1, .72), parent=g)
        ball(sc, mat("ffe6ff", 0.2, 1.6), (0, 0, -.1), .38, parent=g)
        tens = [tube(sc, jm, [(0, 0, 0)] * 12, .06, .2, parent=g) for _ in range(9)]

        def pulse(t, g=g, dome=dome, tens=tens, base=(x, y, z), ph=ph):
            q = TAU * (4 * t + ph)
            g.location = (base[0], base[1], base[2] + .6 * math.sin(q - 1.2))
            dome.scale = (1 - .14 * math.sin(q), 1 - .14 * math.sin(q), .72 + .12 * math.sin(q))
            for k, ob in enumerate(tens):
                a_ = TAU * k / len(tens)
                for i, p in enumerate(ob.data.splines[0].points):
                    f = i / 11
                    rr = .62 * (1 - .14 * math.sin(q)) * (1 - .4 * f)
                    p.co = (rr * math.cos(a_) + .25 * f * math.sin(q * 2 - f * 5 + k),
                            rr * math.sin(a_), -.35 - 2.6 * f, 1)
        anim.append(pulse)

    bub = mat("dff8ff", 0.05, 0.9, alpha=0.3)
    bubbles = [(ball(sc, bub, (0, 0, 0), rnd.uniform(.05, .26) ** 1.1), rnd.uniform(-12, 12), rnd.uniform(-5, 20),
                rnd.random(), rnd.randint(1, 3)) for _ in range(170)]

    def rise(t):
        for ob, x, y, ph, sp in bubbles:
            z = (ph + sp * t) % 1
            ob.location = (x + .3 * math.sin(TAU * (z * 3 + ph)), y, -8 + 21 * z)
    anim.append(rise)
    return sc, anim


# ---------- 世界2：夜の街と宇宙 ----------
def night():
    sc = new_scene("night", "6b3fa0", "050722", 0.75, 0.9, "9fb4ff")
    anim = []
    ground(sc, mat("171c38", 0.3), -6.5, 0.0, 0.1)

    wins = [mat(c, 0.5, e) for c, e in (("ffd37a", 2.6), ("ffe9b0", 2.0), ("8fd8ff", 1.6))]
    dark = mat("0c1030", 0.2)

    def house(cx, y, w, h, color):
        body = mat(color, .6)
        box(sc, body, (cx, y, -6.5 + h / 2), (round(w, 2), 1.4, round(h, 2)))
        def roof(bm):
            v = [bm.verts.new(p) for dy in (-.8, .8) for p in ((-w / 2 - .18, dy, 0), (w / 2 + .18, dy, 0), (0, dy, w * .42))]
            for f in ((0, 1, 2), (3, 5, 4), (0, 2, 5, 3), (1, 4, 5, 2), (0, 3, 4, 1)):
                bm.faces.new([v[k] for k in f])
        add(sc, mesh(f"roof{w:.2f}", mat("2a1d48", .5), roof), bevel=.05, loc=(cx, y, -6.5 + h))
        nx = max(1, int(w / .8))
        for i in range(nx):
            for k in range(int((h - .6) / 1.0)):
                pos = (cx + (i - (nx - 1) / 2) * .72, y - .73, -5.7 + k * 1.0)
                m = rnd.choice(wins) if rnd.random() < .45 else dark
                box(sc, mat("463a6e", .6), pos, (.48, .05, .66), bevel=.02)
                box(sc, m, (pos[0], pos[1] - .04, pos[2]), (.36, .04, .54), bevel=0)
                box(sc, mat("463a6e", .6), (pos[0], pos[1] - .08, pos[2]), (.04, .03, .54), bevel=0)

    palette = ["232a5e", "3a2c66", "1d3a62", "47285a"]
    for row, y in enumerate((9.0, 16.0, 25.0)):
        x = -22
        while x < 22:
            w = rnd.uniform(1.6, 2.8)
            house(x + w / 2, y, w, rnd.uniform(2.2, 4.4) + row * .9, rnd.choice(palette))
            x += w + rnd.uniform(.1, .5)
    for cx, w, h, y in ((-4.9, 2.6, 5.4, 1.6), (4.9, 2.5, 4.7, 1.5), (-8.1, 3.0, 6.6, 2.6), (8.2, 3.1, 6.2, 2.4), (-11.8, 3.2, 5.0, 3.5), (12, 3.2, 5.6, 3.4)):
        house(cx, y, w, h, rnd.choice(palette))

    # 洋菓子店（中央の大きな窓がお菓子の世界）
    wall, trim, gold = mat("7a3f5e", .7), mat("f3dcc0", .45), mat("e8b45a", .3, .15, metal=.7)
    q = PORTALS[1]
    ww, wz = q["w"] * 10, q["pos"][1] * 10
    wh = ww * 16 / 9
    top, bot = wz + wh / 2, wz - wh / 2
    for sx in (-1, 1):
        box(sc, wall, (sx * (ww / 2 + .75), .8, -2.7), (1.5, 1.4, 7.6))
        box(sc, trim, (sx * (ww / 2 + .07), 0, wz), (.14, .3, wh + .28), bevel=.04)
        box(sc, trim, (sx * (ww / 2 + 1.42), .05, -2.7), (.2, .25, 7.6), bevel=.05)
        cyl(sc, mat("2f7d52", .8), (sx * 1.75, -.35, -5.55), .26, .26, .5)
        for k in range(14):
            ball(sc, mat(rnd.choice(["3a8f5c", "2f7d52", "ff8fab"]), .8), (sx * 1.75 + rnd.uniform(-.28, .28), -.4 + rnd.uniform(-.15, .15), -5.15 + rnd.uniform(-.1, .4)), rnd.uniform(.1, .2))
        # 壁のランタン
        box(sc, gold, (sx * 1.75, -.05, -1.7), (.3, .2, .08), bevel=.02)
        ball(sc, mat("ffcf70", .5, 5), (sx * 1.75, -.1, -2.0), .17, scale=(1, 1, 1.3))
        point(sc, (sx * 1.75, -.7, -2.0), "ffb45a", 45, .2)
    box(sc, wall, (0, .8, (1.1 + top) / 2), (ww, 1.4, 1.1 - top))
    box(sc, wall, (0, .8, (bot - 6.5) / 2), (ww, 1.4, bot + 6.5))
    box(sc, trim, (0, -.05, top + .08), (ww + .28, .35, .16), bevel=.04)
    box(sc, trim, (0, -.15, bot - .1), (ww + .6, .55, .2), bevel=.05)
    for k in range(11):  # ひさし
        x = (k - 5) * .47
        m = mat("fff3e2" if k % 2 else "d9486c", .6)
        box(sc, m, (x, -.45, top + .75), (.47, 1.25, .09), bevel=.01, rot=(math.radians(28), 0, 0))
        cyl(sc, m, (x, -1.0, top + .42), .235, .235, .07, bevel=.01, rot=(math.pi / 2, 0, 0))
    box(sc, mat("2b1b3d", .5), (0, 0, 1.75), (4.5, .2, .85), bevel=.08)
    for z in (1.33, 2.17):
        box(sc, gold, (0, -.12, z), (4.5, .06, .06), bevel=.02)
    cu = bpy.data.curves.new("sign", "FONT")
    cu.body, cu.size, cu.align_x, cu.align_y, cu.extrude = "PÂTISSERIE", .55, "CENTER", "CENTER", .02
    cu.materials.append(mat("ffd98a", .4, 2.4))
    link(sc, bpy.data.objects.new("sign", cu), loc=(0, -.17, 1.75), rot=(math.pi / 2, 0, 0))
    def gable(bm):
        v = [bm.verts.new(p) for dy in (-.8, .9) for p in ((-3.1, dy, 0), (3.1, dy, 0), (0, dy, 1.7))]
        for f in ((0, 1, 2), (3, 5, 4), (0, 2, 5, 3), (1, 4, 5, 2), (0, 3, 4, 1)):
            bm.faces.new([v[k] for k in f])
    box(sc, wall, (0, .9, 1.7), (5.2, 1.3, 1.3))
    add(sc, mesh("gable", mat("33224f", .5), gable), bevel=.08, loc=(0, .8, 2.35))
    ball(sc, mat("ffd98a", .5, 3), (0, -.05, 2.95), .3, scale=(1, .3, 1))
    point(sc, (0, -1.6, bot + .3), "ffc27a", 130, .6)

    # 手前の道と街灯
    box(sc, mat("2a2f55", .35), (0, -1.9, -6.48), (60, .25, .12), bevel=.03)
    for x in (-3.7, 3.8):
        cyl(sc, mat("11152e", .3, metal=.6), (x, -.8, -4.7), .09, .07, 3.6)
        ball(sc, mat("ffd58a", .5, 6), (x, -.8, -2.75), .24)
        cyl(sc, mat("11152e", .3, metal=.6), (x, -.8, -2.45), .34, 0, .28)
        point(sc, (x, -1.2, -2.9), "ffb860", 70, .25)
    cars = []
    for j in range(3):
        g = empty(sc)
        box(sc, mat(["e8ecff", "ff7aa2", "46c8ff"][j], .25, coat=.6), (0, 0, 0), (1.5, .7, .36), bevel=.16, parent=g)
        box(sc, mat("101840", .1), (-.1, 0, .3), (.75, .62, .3), bevel=.13, parent=g)
        for sx in (-.48, .48):
            cyl(sc, mat("07080f", .5), (sx, -.34, -.18), .19, .19, .14, rot=(math.pi / 2, 0, 0), parent=g)
        ball(sc, mat("fff2c0", .5, 7), (.76, -.2, 0), .09, parent=g)
        ball(sc, mat("ff3b5c", .5, 5), (-.76, -.2, 0), .09, parent=g)
        cars.append((g, j / 3 + .05))

    def drive(t):
        for g, ph in cars:
            g.location = ((ph + t) % 1 * 44 - 22, -3.6, -6.1)
    anim.append(drive)

    # 星
    stars = []
    for _ in range(420):
        s = rnd.uniform(.03, .1)
        stars.append((ball(sc, mat(rnd.choice(["ffffff", "bcd4ff", "ffe3b0"]), .5, 5), (rnd.uniform(-34, 34), 45,
                      rnd.uniform(-2, 33)), s), s, rnd.random(), rnd.randint(3, 9)))

    def twinkle(t):
        for ob, s, ph, sp in stars:
            k = s * (0.65 + 0.55 * math.sin(TAU * (sp * t + ph)))
            ob.scale = (k, k, k)
    anim.append(twinkle)

    # 月（クレーター付き）
    moon = empty(sc, loc=(3.3, 4, 5.6))

    def moon_mesh(bm):
        bmesh.ops.create_icosphere(bm, subdivisions=6, radius=1)
        craters = [(Vector((rnd.gauss(0, 1), rnd.gauss(0, 1), rnd.gauss(0, 1))).normalized(), rnd.uniform(.08, .3))
                   for _ in range(60)]
        for v in bm.verts:
            n_ = v.co.normalized()
            h = 0.015 * noise.noise(n_ * 4)
            for c, r in craters:
                d = (n_ - c).length / r
                if d < 1.4:
                    h += r * (0.12 * math.exp(-((d - 1) * 4) ** 2) - 0.14 * max(0, 1 - d * d))
            v.co = n_ * (1 + h)
    add(sc, mesh("moon", mat("fff0c9", 0.9, 0.42), moon_mesh, sharp=80), scale=(1.5, 1.5, 1.5), parent=moon)
    point(sc, (3.3, 1.2, 5.6), "ffe9b0", 220, 1.5)
    anim.append(lambda t: setattr(moon, "rotation_euler", (0, 0, TAU * t)))

    # 輪のある惑星
    pl = empty(sc, loc=(-3.7, 6, 6.9), rot=(math.radians(18), math.radians(-22), 0))
    body = ball(sc, mat("ff8e72", 0.55, 0.12), (0, 0, 0), 1.15, parent=pl)
    for k, (z, c) in enumerate(((.45, "ffd6a5"), (.05, "c9556e"), (-.4, "ffb48a"))):
        torus(sc, mat(c, .6, .12), (0, 0, z), math.sqrt(1 - (z / 1.15) ** 2) * 1.12, .09, parent=pl)
    for r, c in ((1.75, "b8a1ff"), (2.05, "7ae8ff"), (2.3, "b8a1ff")):
        torus(sc, mat(c, .4, .8), (0, 0, 0), r, .07, scale=(1, 1, .3), parent=pl)
    moonlet = ball(sc, mat("9bffd0", .5, .6), (0, 0, 0), .24, parent=pl)
    anim.append(lambda t: setattr(moonlet, "location", (2.8 * math.cos(TAU * 3 * t), 2.8 * math.sin(TAU * 3 * t), 0)))

    # 流れ星
    shoot = tube(sc, mat("dff4ff", .5, 7), [(0, 0, 0), (4.0, 0, 1.7)], .09, 0.02)

    def meteor(t):
        f = (t * 3 + .15) % 1
        shoot.location = (11 - 24 * f * 2.2, 30, 22 - 10 * f * 2.2)
    anim.append(meteor)
    return sc, anim


# ---------- 世界3：お菓子 ----------
def sweets():
    sc = new_scene("sweets", "ffe3d0", "ffc9d6", 0.45, 1.9, "fff0dc", (48, -35, 0))
    anim = []
    cream = mat("fff4e4", .45, sss=.4)
    colors = ["ff6f91", "ffd36b", "8fd8c8", "b9a0ff", "ff9a5a"]
    box(sc, mat("f6e6da", .8, sss=.1), (0, 5, -5.4), (60, 22, 1.0), bevel=.1)          # テーブル(クロス)
    for k in range(-14, 15):
        box(sc, mat("f0b9c4", .85), (k * 2.2, 5, -4.895), (.75, 21.5, .012), bevel=0)
    box(sc, mat("e9b7a8", .9), (0, 17, 4), (70, .5, 30))                                # 奥の壁
    wood = mat("8a5436", .55)
    for z in (-1.2, 3.2, 7.4):                                                          # 棚と瓶
        box(sc, wood, (0, 15.6, z), (40, 2.0, .28))
        x = -15.0
        while x < 15:
            h, r = rnd.uniform(1.1, 2.2), rnd.uniform(.5, .85)
            c = rnd.choice(colors)
            for k in range(int(h / .34)):
                for dx in (-.28, .28):
                    ball(sc, mat(c, .4), (x + dx * r * 1.4 + rnd.uniform(-.05, .05), 14.9, z + .35 + k * .34), .2 * r * 1.4)
            cyl(sc, mat("fff8f0", .08, alpha=.22), (x, 15.0, z + .15 + h / 2), r, r, h, bevel=.2)
            cyl(sc, mat("c98a4b", .35, metal=.6), (x, 15.0, z + .28 + h), r * .8, r * .8, .25)
            x += r * 2 + rnd.uniform(.25, .8)
    for k in range(34):                                                                 # つり電球
        x = -13 + k * .8
        z = 6.3 - .9 * abs(math.sin(k * math.pi / 11))
        ball(sc, mat("ffdf9a", .5, 4), (x, 12.5, z), .11)

    def plate(x, y, z, r):
        cyl(sc, mat("ffffff", .15, coat=1), (x, y, z), r * .85, r, .14, bevel=.05)
        torus(sc, mat("e8b45a", .25, metal=.8), (x, y, z + .08), r * .94, .035)

    def skin():
        """苺の皮。大きく寄っても赤一色にならないよう、細かい凹凸と色むらを入れる。"""
        m = mat("e5173f", .24, coat=1, sss=.15)
        nt = m.node_tree
        if not nt.nodes.get("pores"):
            p = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
            co, nz, ramp, bump = (nt.nodes.new("ShaderNode" + n) for n in ("TexCoord", "TexNoise", "ValToRGB", "Bump"))
            nz.name = "pores"
            for name, v in (("Scale", 14.0), ("Detail", 10.0), ("Roughness", .68)):
                nz.inputs[name].default_value = v
            lo, hi = ramp.color_ramp.elements[0], ramp.color_ramp.elements[1]
            lo.position, lo.color, hi.position, hi.color = .35, lin("c20f33"), .68, lin("f5294f")
            bump.inputs["Strength"].default_value, bump.inputs["Distance"].default_value = .5, .035
            for a_, b_ in ((co.outputs["Object"], nz.inputs["Vector"]), (nz.outputs["Fac"], ramp.inputs["Fac"]),
                           (ramp.outputs["Color"], p.inputs["Base Color"]), (nz.outputs["Fac"], bump.inputs["Height"]),
                           (bump.outputs["Normal"], p.inputs["Normal"])):
                nt.links.new(a_, b_)
        return m

    def berry(c, r, seeds, skip=None):
        g = empty(sc, loc=c, scale=(r, r, r))

        def shape(n):
            w = .84 + .24 * n.z
            return Vector((n.x * w, n.y * w, n.z * 1.15))

        def build(bm):
            bmesh.ops.create_icosphere(bm, subdivisions=5, radius=1)
            for v in bm.verts:
                v.co = shape(v.co.normalized())
        add(sc, mesh("berry", skin(), build, sharp=80), parent=g)
        for k in range(seeds):  # 種（黄金角で均等に）
            h = .72 - 1.64 * (k + .5) / seeds
            a_ = k * 2.39996
            n_ = Vector((math.sqrt(1 - h * h) * math.cos(a_), math.sqrt(1 - h * h) * math.sin(a_), h))
            p_ = shape(n_)
            if skip and (Vector(c) + p_ * r - Vector(skip)).length < .15:
                continue
            ob = ball(sc, mat("f7d65a", .35), tuple(p_ * 1.005), .042, scale=(1, 1, 1.4), parent=g)
        for k in range(7):
            a_ = k * TAU / 7
            tube(sc, mat("3f9e46", .55), [(0, 0, 1.12), (.3 * math.cos(a_), .3 * math.sin(a_), 1.2),
                                          (.7 * math.cos(a_), .7 * math.sin(a_), 1.0 + .12 * (k % 2))], .11, .05, parent=g)
        tube(sc, mat("4f8a34", .6), [(0, 0, 1.12), (.08, 0, 1.45), (.24, 0, 1.62)], .07, .7, parent=g)

    # 手前の主役の苺（水滴がつく）
    plate(.5, 1.2, -4.82, 3.0)
    berry((.75, 1.32, -2.95), 1.58, 170, skip=(.75, 0, -2.5))  # 水滴の下だけ種を抜く
    berry((-1.25, .6, -4.1), .66, 70)
    for x, y, rz in ((-1.9, -.4, .4), (2.5, .2, -.5)):
        tube(sc, mat("52a84a", .5), [(x, y, -4.68), (x + .6 * math.cos(rz), y + .6 * math.sin(rz), -4.55),
                                     (x + 1.1 * math.cos(rz), y + 1.1 * math.sin(rz), -4.66)], .2, .08)

    # 苺のホールケーキ
    cx, cy = -3.0, 6.0
    cyl(sc, mat("ffffff", .15, coat=1), (cx, cy, -4.3), .55, .3, 1.2)
    plate(cx, cy, -3.65, 3.1)
    cyl(sc, cream, (cx, cy, -2.35), 2.55, 2.55, 2.45, bevel=.22)
    for z in (-2.9, -2.0):
        torus(sc, mat("ff8fa8", .35), (cx, cy, z), 2.54, .09)
    for k in range(26):
        a_ = TAU * k / 26
        px, py = cx + 2.25 * math.cos(a_), cy + 2.25 * math.sin(a_)
        ball(sc, cream, (px, py, -1.08), .27, scale=(1, 1, .8))
        tube(sc, cream, [(px, py, -1.0), (px, py, -.72)], .13, .1)
    for k in range(9):
        a_ = TAU * k / 9 + .2
        berry((cx + 1.5 * math.cos(a_), cy + 1.5 * math.sin(a_), -.65), .36, 24)
    for k, (dx, h) in enumerate(((-.5, 1.3), (.2, 1.6), (.85, 1.15))):
        cyl(sc, mat(colors[k + 1], .4), (cx + dx, cy, -1.1 + h / 2), .09, .09, h, bevel=.02)
        flame = ball(sc, mat("ffb030", .5, 8), (cx + dx, cy, -1.1 + h + .22), .12, scale=(1, 1, 1.9))

        def flick(t, f=flame, ph=k):
            v = 1 + .18 * math.sin(TAU * (31 * t + ph * .37))
            f.scale = (.12, .12, .228 * v)
        anim.append(flick)

    # マカロンの皿とクッキー、カップ
    plate(3.7, 4.6, -4.82, 2.1)
    z = -4.55
    for k, n in enumerate((3, 2, 1)):
        for j in range(n):
            x = 3.7 + (j - (n - 1) / 2) * 1.2
            c = colors[(k * 2 + j) % 5]
            for dz in (-.19, .19):
                ball(sc, mat(c, .55, sss=.2), (x, 4.6, z + dz + k * .62), .6, scale=(1, 1, .36))
            cyl(sc, cream, (x, 4.6, z + k * .62), .52, .52, .16)
    for x, y, r in ((-4.4, .8, .95), (-3.9, -1.2, .75), (3.8, -.9, .85), (5.6, 1.2, .9)):
        cyl(sc, mat("d99a52", .8, sss=.2), (x, y, -4.72), r, r * .95, .3, bevel=.12)
        for k in range(9):
            a_, d = rnd.uniform(0, TAU), rnd.uniform(0, r * .75)
            ball(sc, mat("4a2616", .35), (x + d * math.cos(a_), y + d * math.sin(a_), -4.56), rnd.uniform(.07, .13), scale=(1, 1, .6))
    cup = mat("a8d8d0", .18, coat=1)
    cyl(sc, cup, (6.0, 8.0, -3.7), .9, 1.25, 2.2, bevel=.2)
    torus(sc, cup, (7.35, 8.0, -3.6), .6, .18, rot=(math.pi / 2, 0, 0))
    cyl(sc, mat("8a4b2a", .1), (6.0, 8.0, -2.58), 1.1, 1.1, .05)
    steam = [tube(sc, mat("ffffff", .9, .6, alpha=.12), [(0, 0, 0)] * 16, .16, .2) for _ in range(3)]

    def smoke(t):
        for k, ob in enumerate(steam):
            for i, p in enumerate(ob.data.splines[0].points):
                f = i / 15
                p.co = (6.0 + (k - 1) * .4 + .45 * f * math.sin(TAU * (4 * t + k * .3) - f * 7), 8.0, -2.5 + 3.2 * f, 1)
    anim.append(smoke)
    point(sc, (-5, -5, 2), "ffdcb4", 380, 2)
    return sc, anim


bpy.ops.wm.read_factory_settings(use_empty=True)
WORLDS = [underwater(), night(), sweets()]
TOTAL = sum(PER)
TMP = tempfile.mkdtemp()


# ---------- 描画と合成 ----------
def load(path):
    img = bpy.data.images.load(path)
    w, h = img.size
    arr = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(arr)
    bpy.data.images.remove(img)
    return arr.reshape(h, w, 4)[..., :3]  # 下の行が先頭


def render(sc, x0, y0, x1, y1, center, scale):
    """画面のピクセル矩形[x0,x1)x[y0,y1)に見える、世界scの部分を実解像度で描く。"""
    pw, ph = x1 - x0, y1 - y0
    a = (x0 + x1) / 2 / W - 0.5
    b = ((y0 + y1) / 2 - H / 2) / W
    w = pw / W / scale
    cam = sc.camera.data
    cam.lens = LENS / w
    cam.shift_x = (a - center[0]) / scale / w
    cam.shift_y = (b - center[1]) / scale / w
    sc.render.resolution_x, sc.render.resolution_y = pw, ph
    sc.render.filepath = os.path.join(TMP, "r.png")
    bpy.ops.render.render(write_still=True, scene=sc.name)
    return load(sc.render.filepath)


def smooth(e0, e1, v):
    v = np.clip((v - e0) / (e1 - e0), 0, 1)
    return v * v * (3 - 2 * v)


def portal(canvas, level, center, scale, depth):
    """levelの世界(中心center・倍率scale)にある物の中に、次の世界を映し込む。"""
    q = PORTALS[level % 3]
    c = (center[0] + q["pos"][0] * scale, center[1] + q["pos"][1] * scale)
    window = q["kind"] == "window"
    size = (q["w"] if window else 2 * q["r"]) * scale          # 画面上の幅
    hw = size / 2 * W
    hh = hw * 16 / 9 if window else hw
    cx, cy = (c[0] + 0.5) * W, c[1] * W + H / 2
    pad = 1.0 if window else 1.65                              # 水滴は外側に影を落とす
    x0, y0 = max(0, int(cx - hw * pad)), max(0, int(cy - hh * pad))
    x1, y1 = min(W, int(math.ceil(cx + hw * pad)) + 1), min(H, int(math.ceil(cy + hh * pad)) + 1)
    if depth > 2 or hw < 2 or x1 - x0 < 4 or y1 - y0 < 4:
        return
    child = (level + 1) % 3
    inner = render(WORLDS[child][0], x0, y0, x1, y1, c, scale * q["s"])
    sub = np.zeros((H, W, 3), np.float32)
    sub[y0:y1, x0:x1] = inner
    if child == 2:
        dew(sub, c, scale * q["s"])
    portal(sub, child, c, scale * q["s"], depth + 1)
    inner = sub[y0:y1, x0:x1]
    area = canvas[y0:y1, x0:x1]
    # 引き(p=0)→寄り切り(p=1)。物の大きさだけで決めるので、世界の切り替わりでも連続する
    base_size = q["w"] if window else 2 * q["r"]
    p = float(smooth(0, 1, math.log(max(size / base_size, 1)) / math.log(1 / q["s"]) / .8))
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dx, dy = (xx + .5 - cx) / hw, (yy + .5 - cy) / hh
    if window:
        mask = (np.clip((1 - np.abs(dx)) * hw + .5, 0, 1) * np.clip((1 - np.abs(dy)) * hh + .5, 0, 1))[..., None]
        shine = np.exp(-((dx + dy * .8 + .5) / .16) ** 2) + .6 * np.exp(-((dx + dy * .8 - .35) / .06) ** 2)
        inner = inner + (shine * .13 * (1 - p))[..., None] * (1 - inner)       # ガラスの反射
        area += mask * (inner - area)
        return
    d = np.sqrt(dx * dx + dy * dy)
    mask = np.clip((1 - d) * hw + .5, 0, 1)
    seen = q["seen"] + (1 - q["seen"]) * float(smooth(.05, .75, p))
    keep = float(1 - smooth(.5, .98, hw / W))                 # 縁と光は縁が画面の外へ出るまで残す
    if q["kind"] == "pearl":
        alpha = (mask * seen * (1 - smooth(.6, 1.0, d) * (.35 + .65 * (1 - p)) * keep))[..., None]
        luster = np.stack([.62 + .38 * np.cos(d * 4 + dx * 2 + k) for k in (0, 2.1, 4.2)], -1)
        area += (mask * smooth(.4, 1, d) * .12 * (1 - p))[..., None] * (luster - area)
        area += alpha * (inner - area)
        area += (mask * smooth(.68, 1.0, d) * .45 * keep * smooth(0, .3, p))[..., None] * (luster - area)
        spec = np.exp(-((dx + .42) ** 2 + (dy - .48) ** 2) / .02)
        area += (mask * spec * .55 * keep * smooth(0, .3, p))[..., None] * (1 - area)
        return
    water(area, dx, dy, d, mask, hw, hh, cx - x0, cy - y0, inner, seen, p, keep)


def water(area, dx, dy, d, mask, hw, hh, ox, oy, inner, seen, p, keep):
    """areaに水滴を1つ描く。下地を拡大して透かし、影・集まった光・反射を足す。"""
    sd = np.sqrt((dx - .14) ** 2 + (dy + .24) ** 2)
    area *= 1 - (smooth(1.3, .8, sd) * (1 - mask) * .5 * keep)[..., None]
    zx = np.clip((ox + dx * hw * (.5 + .4 * d * d)).astype(int), 0, area.shape[1] - 1)
    zy = np.clip((oy + dy * hh * (.5 + .4 * d * d)).astype(int), 0, area.shape[0] - 1)
    lens = np.clip(area[zy, zx] * 1.12 + .05, 0, 1)             # 水は下地を明るく拡大する
    area += (mask * (1 - p))[..., None] * (lens - area)
    if inner is not None:
        area += (mask * seen * (1 - smooth(.6, 1.0, d) * .75 * keep))[..., None] * (inner - area)
    area *= 1 - (mask * np.exp(-((d - .93) / .09) ** 2) * smooth(-.4, .7, dy) * .45 * keep)[..., None]  # 上側の縁は暗い
    light = np.array([1.0, .93, .86], np.float32)
    crescent = np.exp(-((d - .74) / .13) ** 2) * smooth(.1, -.75, dy) * .85       # 下側に集まる光
    spec = np.exp(-((dx + .36) ** 2 / .018 + (dy - .46) ** 2 / .01)) * 1.2 + np.exp(-((dx + .62) ** 2 + (dy - .14) ** 2) / .003)
    edge = np.exp(-((d - .97) / .035) ** 2) * .3
    area += (mask * np.clip(crescent + spec + edge, 0, 1) * keep)[..., None] * (light - area)


# 苺についた、中に何も映らない小さな水滴（画面座標は泡ではなく世界のもの）
DEW = [(0.018, -0.292, .0035), (0.128, -0.222, .0025), (0.112, -0.318, .004), (0.032, -0.2, .002),
       (0.0862, -0.2415, .0014), (0.0615, -0.2605, .0009), (0.0845, -0.2625, .0006)]


def dew(canvas, center, scale):
    for x, y, r in DEW:
        hw = r * scale * W
        cx, cy = (center[0] + x * scale + .5) * W, (center[1] + y * scale) * W + H / 2
        x0, y0 = max(0, int(cx - hw * 1.65)), max(0, int(cy - hw * 1.65))
        x1, y1 = min(W, int(cx + hw * 1.65) + 2), min(H, int(cy + hw * 1.65) + 2)
        if hw < 1 or x1 - x0 < 4 or y1 - y0 < 4:
            continue
        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        dx, dy = (xx + .5 - cx) / hw, (yy + .5 - cy) / hw
        d = np.sqrt(dx * dx + dy * dy)
        water(canvas[y0:y1, x0:x1], dx, dy, d, np.clip((1 - d) * hw + .5, 0, 1), hw, hw,
              cx - x0, cy - y0, None, 0, 0.0, 1.0)


def blur(a, r):
    for axis in (0, 1):
        pad = [(r + 1, r) if i == axis else (0, 0) for i in range(a.ndim)]
        s = np.cumsum(np.pad(a, pad, mode="edge"), axis=axis, dtype=np.float64)
        n = a.shape[axis]
        a = ((np.take(s, range(2 * r + 1, n + 2 * r + 1), axis) - np.take(s, range(n), axis)) / (2 * r + 1))
    return a


def bloom(img):
    k = 8
    h, w = img.shape[0] // k * k, img.shape[1] // k * k
    small = np.clip(img[:h, :w] - .72, 0, None).reshape(h // k, k, w // k, k, 3).mean((1, 3))
    small = blur(blur(small, 2), 4)
    ys = np.clip((np.arange(img.shape[0]) + .5) / k - .5, 0, small.shape[0] - 1)
    xs = np.clip((np.arange(img.shape[1]) + .5) / k - .5, 0, small.shape[1] - 1)
    y0, x0 = ys.astype(int), xs.astype(int)
    y1, x1 = np.minimum(y0 + 1, small.shape[0] - 1), np.minimum(x0 + 1, small.shape[1] - 1)
    fy, fx = (ys - y0)[:, None, None], (xs - x0)[None, :, None]
    up = (small[y0][:, x0] * (1 - fy) * (1 - fx) + small[y1][:, x0] * fy * (1 - fx)
          + small[y0][:, x1] * (1 - fy) * fx + small[y1][:, x1] * fy * fx)
    return 1 - (1 - img) * (1 - np.clip(up * 1.5, 0, 1))


def animate(f):
    for _, anim in WORLDS:
        for fn in anim:
            fn(f / TOTAL)


def view(f):
    """fコマ目に映す世界の番号と、画面上の中心・倍率。"""
    i, start = 0, 0
    while f % TOTAL >= start + PER[i]:
        start += PER[i]
        i += 1
    u = (f % TOTAL - start) / PER[i]
    u -= 0.6 * math.sin(TAU * u) / TAU  # 世界を見せる所はゆっくり、くぐる所は速く
    S = PORTALS[i]["s"]
    k = S ** u
    p = PORTALS[i]["pos"]
    return i, (-p[0] * (1 - k) / (1 - S) / k, -p[1] * (1 - k) / (1 - S) / k), 1 / k


# ---------- .blend書き出し：次の世界をBlender内の立体(Ray Portal)で映す ----------
OFFSET = [-600.0, 600.0, 0.0]  # 3世界を1つのシーンに離して置く。200倍まで寄る苺の世界は精度のため原点


def nodes(nt):
    def new(kind, **inputs):
        n = nt.nodes.new("ShaderNode" + kind)
        for k, v in inputs.items():
            n.inputs[int(k[1:])].default_value = v
        return n

    def op(kind, a, b=None):
        n = nt.nodes.new("ShaderNodeMath")
        n.operation = kind
        for k, v in enumerate((a, b)):
            if isinstance(v, (int, float)):
                n.inputs[k].default_value = v
            elif v is not None:
                nt.links.new(v, n.inputs[k])
        return n.outputs[0]
    return new, op


def portal_material(i):
    """世界iの入口の素材。当たった視線を、次の世界のカメラから出る視線に置き換える。"""
    q, child = PORTALS[i], (i + 1) % 3
    m = bpy.data.materials.new("入口_" + q["kind"])
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    new, op = nodes(nt)
    sep = new("SeparateXYZ")
    nt.links.new(new("NewGeometry").outputs["Position"], sep.inputs[0])
    depth = op("DIVIDE", CAM_D, op("ADD", sep.outputs["Y"], CAM_D))
    fx = op("DIVIDE", op("SUBTRACT", op("MULTIPLY", op("SUBTRACT", sep.outputs["X"], OFFSET[i]), depth), q["pos"][0] * 10), q["s"])
    fz = op("DIVIDE", op("SUBTRACT", op("MULTIPLY", sep.outputs["Z"], depth), q["pos"][1] * 10), q["s"])
    direction = new("CombineXYZ", i1=CAM_D)
    nt.links.new(fx, direction.inputs[0])
    nt.links.new(fz, direction.inputs[2])
    ray = new("BsdfRayPortal")
    origin = new("CombineXYZ", i0=OFFSET[child], i1=-CAM_D)  # Positionは未接続だと当たった点のままになる
    nt.links.new(origin.outputs[0], ray.inputs["Position"])
    nt.links.new(direction.outputs[0], ray.inputs["Direction"])

    seen, keep, near = (new("Value") for _ in range(3))
    seen.name, keep.name, near.name = "seen", "keep", "near"
    facing = new("LayerWeight", i0=0.5).outputs["Facing"]
    if q["kind"] == "window":
        factor, shine = seen.outputs[0], op("MULTIPLY", op("SUBTRACT", 1.0, near.outputs[0]), 0.05)
        base = new("BsdfTransparent").outputs[0]
    else:
        rim = op("POWER", facing, 2.0)
        soft = op("ADD", 0.35, op("MULTIPLY", op("SUBTRACT", 1.0, near.outputs[0]), 0.65))
        factor = op("MULTIPLY", seen.outputs[0], op("SUBTRACT", 1.0, op("MULTIPLY", op("MULTIPLY", rim, soft), keep.outputs[0])))
        shine = op("MULTIPLY", op("ADD", 0.03, op("MULTIPLY", op("POWER", facing, 3.0), 0.35)), keep.outputs[0])
        if q["kind"] == "pearl":
            p = new("BsdfPrincipled")
            for name, v in (("Base Color", lin("f3ecf4")), ("Roughness", .14), ("Metallic", .35), ("Coat Weight", 1.0),
                            ("Emission Color", lin("f3ecf4")), ("Emission Strength", .05)):
                p.inputs[name].default_value = v
        else:
            p = new("BsdfGlass")
            p.inputs["Color"].default_value = (1, .96, .96, 1)
            p.inputs["Roughness"].default_value, p.inputs["IOR"].default_value = 0.02, 1.33
        base = p.outputs[0]
    inside = new("MixShader")
    for a_, b_ in ((factor, inside.inputs[0]), (base, inside.inputs[1]), (ray.outputs[0], inside.inputs[2])):
        nt.links.new(a_, b_)
    gloss = new("BsdfGlossy")
    gloss.inputs["Roughness"].default_value = 0.06
    final = new("MixShader")
    for a_, b_ in ((shine, final.inputs[0]), (inside.outputs[0], final.inputs[1]), (gloss.outputs[0], final.inputs[2]),
                   (final.outputs[0], new("OutputMaterial").inputs["Surface"])):
        nt.links.new(a_, b_)
    return m


def dome(sc, index):
    """世界ごとの空。元のワールド背景のグラデーションを、その世界を囲む球に置き換える。"""
    src = sc.world.node_tree.nodes
    ramp0 = next(n for n in src if n.type == "VALTORGB").color_ramp
    strength = next(n for n in src if n.type == "BACKGROUND").inputs["Strength"].default_value
    m = bpy.data.materials.new("空%d" % index)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    new, op = nodes(nt)
    sep = new("SeparateXYZ")
    nt.links.new(new("TexCoord").outputs["Object"], sep.inputs[0])
    rng = new("MapRange", i1=-0.08, i2=0.36)
    ramp = new("ValToRGB")
    for k in (0, 1):
        ramp.color_ramp.elements[k].color = ramp0.elements[k].color
    em = new("Emission")
    em.inputs["Strength"].default_value = strength
    for a_, b_ in ((sep.outputs["Z"], rng.inputs["Value"]), (rng.outputs["Result"], ramp.inputs[0]),
                   (ramp.outputs[0], em.inputs[0]), (em.outputs[0], new("OutputMaterial").inputs["Surface"])):
        nt.links.new(a_, b_)

    def build(bm):
        bmesh.ops.create_icosphere(bm, subdivisions=4, radius=1)
    ob = add(sc, mesh("dome%d" % index, m, build, sharp=180), scale=(250, 250, 250))
    ob.visible_shadow = False  # 太陽光は通す


def on_berry(berry_ob, x, z):
    """苺の表面の、正面から見て(x, z)にある点の奥行き。"""
    c, r = berry_ob.location, berry_ob.scale[0]
    skin_ob = next(o for o in berry_ob.children if o.type == "MESH" and o.data.name.startswith("berry"))
    ok, hit, _, _ = skin_ob.ray_cast(Vector(((x - c.x) / r, -20, (z - c.z) / r)), Vector((0, 1, 0)))
    assert ok, (x, z)
    return c.y + hit.y * r


def build_portals():
    sea, night_sc, sweet = (w[0] for w in WORLDS)
    mats = [portal_material(i) for i in range(3)]
    # 真珠
    pearl = next(o for o in sea.collection.objects if o.type == "MESH" and (o.location - Vector((0, 0, -2.2))).length < 1e-4)
    pearl.data = pearl.data.copy()
    pearl.data.materials[0] = mats[0]
    pearl.name = "入口_真珠"
    # 真珠の手前を通る泡は、寄り切ったときに写り込むので外す
    animate(0)
    for o in list(sea.collection.objects):
        if o.type == "MESH" and o.data.materials[0].name.startswith("dff8ff") and abs(o.location.x) < 2.8 and o.location.y < 1.5:
            sea.collection.objects.unlink(o)
    # 店の窓
    q = PORTALS[1]
    ww = q["w"] * 10

    def pane(bm):
        bm.faces.new([bm.verts.new((x * ww / 2, 0, z * ww * 8 / 9)) for x, z in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    add(night_sc, mesh("入口_窓", mats[1], pane), loc=(q["pos"][0] * 10, 0, q["pos"][1] * 10))
    # 苺の水滴（主役と、周りの小さな水滴）
    bpy.context.window.scene = sweet
    bpy.context.view_layer.update()
    berry_ob = next(o for o in sweet.collection.objects if o.type == "EMPTY" and (o.location - Vector((.75, 1.32, -2.95))).length < 1e-4)
    water_m = mat("ffffff", 0.0).copy()
    water_m.name = "水"
    wp = next(n for n in water_m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    wp.inputs["Transmission Weight"].default_value, wp.inputs["IOR"].default_value = 1.0, 1.33
    q = PORTALS[2]
    for k, (x, y, r, m) in enumerate([(q["pos"][0], q["pos"][1], q["r"], mats[2])] + [(*d, water_m) for d in DEW]):
        depth = on_berry(berry_ob, x * 10, y * 10)
        ob = ball(sweet, m, (x * 10, depth - r * 10 * .4, y * 10), r * 10, scale=(1, .7, 1))
        ob.name = "入口_水滴" if k == 0 else "水滴%d" % k
    return mats


def save_blend(path):
    """1つのシーンにまとめ、動き・カメラの寄り・入口の見え方をキーフレームにして保存する。"""
    mats = build_portals()
    for i, (sc, _) in enumerate(WORLDS):
        dome(sc, i)
    paths = ("location", "rotation_euler", "scale")
    objs = [o for sc, _ in WORLDS for o in sc.collection.objects]
    points = [p for o in objs if o.type == "CURVE" for sp in o.data.splines for p in sp.points]
    targets = [(o, n) for o in objs for n in paths] + [(p, "co") for p in points]
    track = [[] for _ in targets]
    for f in range(TOTAL):
        animate(f)
        for log, (ob, name) in zip(track, targets):
            log.append(tuple(getattr(ob, name)))
    moving = [(t, log) for t, log in zip(targets, track) if any(v != log[0] for v in log)]
    print("animated channels:", len(moving), flush=True)
    assert moving
    for (ob, name), log in moving:
        for f, v in enumerate(log):
            setattr(ob, name, v)
            ob.keyframe_insert(name, frame=f)

    for f in range(TOTAL):
        i, _, scale = view(f)
        for j, m in enumerate(mats):
            q = PORTALS[j]
            sc_ = scale if i == j else 1.0
            half = (q["w"] / 2 if q["kind"] == "window" else q["r"]) * sc_
            p = float(smooth(0, 1, math.log(sc_) / math.log(1 / q["s"]) / .8))
            vals = dict(seen=q["seen"] + (1 - q["seen"]) * float(smooth(.05, .75, p)),
                        keep=float(1 - smooth(.5, .98, half)), near=p)
            for name, v in vals.items():
                out = m.node_tree.nodes[name].outputs[0]
                out.default_value = v
                out.keyframe_insert("default_value", frame=f)

    master = bpy.data.scenes.new("寄り続けるCG")
    names = ["1_海", "2_夜の街", "3_お菓子"]
    cams, cols = [], []
    for i, (sc, _) in enumerate(WORLDS):
        col = bpy.data.collections.new(names[i])
        master.collection.children.link(col)
        cols.append(col)
        anchor = bpy.data.objects.new(names[i] + "_基準", None)
        anchor.location.x = OFFSET[i]
        col.objects.link(anchor)
        for o in sc.collection.objects:
            col.objects.link(o)
            if o.parent is None:
                o.parent = anchor
            if o.type == "LIGHT" and o.data.type == "SUN":  # 太陽は自分の世界だけを照らす
                o.light_linking.receiver_collection = col
        cam = sc.camera
        cam.name, cam.data.clip_end = names[i] + "_カメラ", 2000
        cams.append(cam)
    start = 0
    for i, cam in enumerate(cams):
        master.timeline_markers.new(names[i], frame=start).camera = cam
        for f in range(start, start + PER[i]):
            _, center, scale = view(f)
            cam.data.lens = LENS * scale                     # 画面の横幅 = 1/scale
            cam.data.shift_x, cam.data.shift_y = -center[0], -center[1]
            for name in ("lens", "shift_x", "shift_y"):
                cam.data.keyframe_insert(name, frame=f)
        start += PER[i]
    master.camera = cams[0]
    ref = WORLDS[0][0]
    master.render.engine = "CYCLES"
    for name in ("samples", "use_denoising", "denoiser", "sample_clamp_indirect", "device"):
        setattr(master.cycles, name, getattr(ref.cycles, name))
    master.cycles.max_bounces, master.cycles.transparent_max_bounces = 12, 32
    master.render.resolution_x, master.render.resolution_y, master.render.fps = W, H, FPS
    master.render.image_settings.file_format = "PNG"
    master.view_settings.view_transform = "Standard"
    master.frame_start, master.frame_end = 0, TOTAL - 1
    black = bpy.data.worlds.new("黒")
    black.use_nodes = True
    next(n for n in black.node_tree.nodes if n.type == "BACKGROUND").inputs["Color"].default_value = (0, 0, 0, 1)
    master.world = black
    bpy.context.window.scene = master
    for sc in list(bpy.data.scenes):
        if sc != master:
            bpy.data.scenes.remove(sc)
    master.frame_set(0)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=True)

    # 確認：保存したファイルを開き直し、そのまま描画する
    bpy.ops.wm.open_mainfile(filepath=path)
    sc = bpy.context.scene
    assert len(bpy.data.scenes) == 1 and len(sc.timeline_markers) == 3 and bpy.data.actions
    sc.render.resolution_percentage = 75
    for f in (0, 75, 119, 120, 240, 305, 407):
        sc.frame_set(f)
        sc.camera = [mk for mk in sorted(sc.timeline_markers, key=lambda mk: mk.frame) if mk.frame <= f][-1].camera
        sc.render.filepath = os.path.join(os.path.dirname(path), "check%04d.png" % f)
        bpy.ops.render.render(write_still=True)
        print("check", f, flush=True)


os.makedirs(OUT, exist_ok=True)
if FRAMES is None:
    save_blend(os.path.join(OUT, "cg_zoom.blend"))
for f in FRAMES or []:
    animate(f)
    i, center, scale = view(f)
    canvas = render(WORLDS[i][0], 0, 0, W, H, center, scale).copy()
    if i == 2:
        dew(canvas, center, scale)
    portal(canvas, i, center, scale, 0)
    rgba = np.ones((H, W, 4), np.float32)
    rgba[..., :3] = np.clip(bloom(canvas), 0, 1)
    out = bpy.data.images.new("out", W, H, alpha=True)
    out.pixels.foreach_set(rgba.ravel())
    out.filepath_raw, out.file_format = os.path.join(OUT, f"{f:04d}.png"), "PNG"
    out.save()
    bpy.data.images.remove(out)
    print("frame", f, flush=True)
