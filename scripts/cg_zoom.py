# 寄り続けるCGアニメ（水中 → 夜の街と宇宙 → お菓子 → 水中…の縦型ループ、Blender 5.0 headless / Cycles CPU）
# blender --background --python scripts/cg_zoom.py -- <出力dir> <フレーム "0,60" or "0-23"> [横px=720] [samples=24]
# 仕組み：各世界の一点に「泡（ポータル）」があり、中に次の世界が入っている。寄りは3Dを毎回描き直す
#   （焦点距離とシフトで画面の一部だけを実解像度で描画）ので、拡大してもぼけない。泡の縁と光のにじみはnumpyで合成。
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
if "-" in argv[1]:
    a, b = map(int, argv[1].split("-"))
    FRAMES = range(a, b + 1)
else:
    FRAMES = [int(v) for v in argv[1].split(",")]
W = int(argv[2]) if len(argv) > 2 else 720
H = W * 16 // 9
SAMPLES = int(argv[3]) if len(argv) > 3 else 24

FPS = 24
PER = 120                      # 1世界あたりのフレーム数（5秒）
R = 0.19                       # 泡の半径（画面の横幅=1）
S = R / 1.12                   # 泡の中の世界の縮尺。寄り切ると泡が画面の対角(1.02)を覆う
PORTAL = [(0.05, -0.02), (-0.04, 0.13), (0.0, 0.03)]
CAM_D, LENS = 30.0, 108.0      # 距離30で画面の横幅=10
assert R / S > math.hypot(0.5, 8 / 9)

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

    # 泡の下の大きな貝
    shell = mat("ffd9e8", 0.25, 0.05, coat=0.8)
    for k in range(-5, 6):
        a_ = k * 0.26
        tube(sc, shell, [(0.5, -0.2, -5.4), (0.5 + math.sin(a_) * 1.6, 0.4, -5.1 + math.cos(a_) * 0.5),
                         (0.5 + math.sin(a_) * 2.7, 1.2, -4.9 + math.cos(a_) * 1.5)], 0.36, 1.1)
    ball(sc, shell, (0.5, -0.5, -5.7), 2.3, scale=(1, 0.8, 0.28))
    point(sc, (0.5, -2.5, -3.2), "ffe3f1", 160)

    for c, belly, n, cx, cy, cz, rx, rz, size, speed in [
            ("ffb000", "fff1b8", 7, 0, 3, 2.6, 5.2, 1.0, 0.55, 1), ("ff5a36", "ffd6c2", 4, 0.5, -2, -2.7, 4.4, .6, .62, -1),
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
    sc = new_scene("night", "6b3fa0", "050722", 0.75, 1.1, "9fb4ff")
    anim = []
    ground(sc, mat("141a35", 0.35), -6.5, 0.0, 0.1)

    wins = [mat(c, 0.5, e) for c, e in (("ffd37a", 3.2), ("7ae8ff", 2.6), ("ff7ac8", 2.4))]
    dark = mat("0c1030", 0.2)
    for row, y in enumerate((2.0, 8.0, 15.0, 24.0)):
        x = -19 - row
        while x < 19 + row:
            w = rnd.uniform(1.2, 2.3)
            h = rnd.uniform(1.2, 3.2) + row * 0.75
            if row == 0 and abs(x) < 2.5:
                h *= 0.6
            cx = x + w / 2
            body = mat(rnd.choice(["1b2352", "2a2a68", "18305c", "33255e"]), 0.4)
            box(sc, body, (cx, y, -6.5 + h / 2), (round(w, 1), 1.4, round(h, 1)))
            if rnd.random() < .6:
                box(sc, body, (cx, y, -6.5 + h + .25), (round(w * .55, 1), 1.0, 0.6))
                ball(sc, mat("ff4d6d", 0.5, 6), (cx, y, -6.5 + h + .75), .09)
            m = rnd.choice(wins)
            nx = int(w / 0.42)
            for i in range(nx):
                for k in range(int(h / 0.52)):
                    pos = (cx + (i - (nx - 1) / 2) * 0.4, y - 0.72, -6.2 + k * 0.5)
                    box(sc, m if rnd.random() < .5 else dark, pos, (0.2, 0.06, 0.26), bevel=0)
            x += w + rnd.uniform(0.15, 0.6)

    # 泡を支える塔
    tm = mat("3a3f85", 0.25, metal=0.6)
    cyl(sc, tm, (-0.4, 0.8, -4.0), .75, .22, 5.0)
    for z, r in ((-3.0, .95), (-1.5, .75)):
        torus(sc, mat("62f2ff", 0.4, 4), (-0.4, 0.8, z), r, .07)
    torus(sc, tm, (-0.4, 0.8, -0.85), 1.05, .13)

    # 道路と車の光
    cars = []
    for lane, (y, c, d) in enumerate(((-3.6, "ff3b5c", 1), (-1.8, "fff2c0", -1))):
        box(sc, mat("5b6bd6", 0.5, 0.5), (0, y - .75, -6.45), (60, .08, .05), bevel=0)
        for j in range(9):
            g = empty(sc)
            box(sc, mat(rnd.choice(["e8ecff", "ff7aa2", "46c8ff"]), .25, coat=.6), (0, 0, 0), (1.0, .55, .28), parent=g)
            box(sc, mat("101840", .1), (-.08 * d, 0, .22), (.5, .5, .22), parent=g)
            ball(sc, mat(c, .5, 8), (-.52 * d, -.2, 0), .11, parent=g)
            tube(sc, mat(c, .5, 2.2, alpha=.5), [(-.55 * d, -.2, 0), (-2.2 * d, -.2, 0)], .06, 0.05, parent=g)
            cars.append((g, y, d, j / 9 + rnd.uniform(-.03, .03) + lane * .05))

    def drive(t):
        for g, y, d, ph in cars:
            g.location = (((ph + 2 * t) % 1 * 40 - 20) * d, y, -6.2)
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

    # ロケット：泡の周りを回る
    rk = empty(sc)
    cyl(sc, mat("f4f6ff", .25, .08, coat=.8), (0, 0, 0), .34, .34, 1.1, parent=rk)
    cyl(sc, mat("ff4d6d", .3, .15), (0, 0, .82), .34, 0, .55, parent=rk)
    for k in range(3):
        a_ = TAU * k / 3
        box(sc, mat("ff4d6d", .3, .15), (.38 * math.cos(a_), .38 * math.sin(a_), -.45), (.36, .09, .45), rot=(0, 0, a_), parent=rk)
    ball(sc, mat("62f2ff", .1, 1.5), (0, -.31, .15), .16, parent=rk)
    flame = cyl(sc, mat("ffb020", .5, 9), (0, 0, -.95), .24, 0, .85, rot=(math.pi, 0, 0), parent=rk)
    puffs = [ball(sc, mat("ffd9a0", .8, 1.2, alpha=.45), (0, 0, 0), .1) for _ in range(26)]

    def orbit(q):
        return Vector((-0.4 + 3.9 * math.cos(q), 1.0 + 3.0 * math.sin(q), 1.5 + 1.9 * math.sin(q + .6)))

    def fly(t):
        q = TAU * 2 * t + 3.6
        rk.location = orbit(q)
        rk.rotation_euler = (orbit(q + .02) - orbit(q)).to_track_quat("Z", "Y").to_euler()
        flame.scale = (1, 1, 1 + .35 * math.sin(TAU * 60 * t))
        for i, p in enumerate(puffs):
            back = orbit(q - .09 - i * .05)
            p.location = back
            k = .2 * (1 - i / len(puffs)) + .02
            p.scale = (k, k, k)
    anim.append(fly)

    # 流れ星
    shoot = tube(sc, mat("dff4ff", .5, 7), [(0, 0, 0), (4.0, 0, 1.7)], .09, 0.02)

    def meteor(t):
        f = (t * 3 + .15) % 1
        shoot.location = (11 - 24 * f * 2.2, 30, 22 - 10 * f * 2.2)
    anim.append(meteor)
    point(sc, (0, -4, -3), "ff6fd0", 260, 2)
    return sc, anim


# ---------- 世界3：お菓子 ----------
def sweets():
    sc = new_scene("sweets", "ffd7e6", "8fd8ff", 0.8, 2.6, "fff1dd", (45, -30, 0))
    anim = []
    ground(sc, mat("ffb3cd", 0.5, sss=.3), -6.5, 0.9, 0.12)
    cream = mat("fff6ea", 0.4, sss=.4)
    colors = ["ff5d8f", "ffd23f", "5ad1e8", "9d7bff", "7ee081", "ff9248"]

    def swirl(x, y, z, s):  # ホイップ
        for k in range(5):
            torus(sc, cream, (x, y, z + k * .3 * s), (0.62 - k * .12) * s, (.27 - k * .035) * s, rot=(.06 * (k % 2), 0, 0))
        cyl(sc, cream, (x, y, z + 1.65 * s), .14 * s, 0, .55 * s)

    def berry(x, y, z, s):
        ball(sc, mat("ff2d55", .22, coat=1), (x, y, z), s, scale=(1, 1, 1.15))
        for k in range(14):
            a_, h = rnd.uniform(0, TAU), rnd.uniform(-.7, .7)
            rr = math.sqrt(1 - h * h) * s
            ball(sc, mat("ffe66d", .4), (x + rr * math.cos(a_), y + rr * math.sin(a_), z + h * s * 1.15), s * .07)
        for k in range(5):
            ball(sc, mat("38b24a", .5), (x + .35 * s * math.cos(k * 1.26), y + .35 * s * math.sin(k * 1.26), z + 1.12 * s),
                 .3 * s, scale=(1, .55, .25), rot=(0, 0, k * 1.26))

    # ケーキ（泡はこの上）
    for z, r, h, c in ((-5.55, 3.4, 1.9, "ffe0a8"), (-3.8, 2.5, 1.6, "ff9ebb"), (-2.4, 1.6, 1.2, "fff0c2")):
        cyl(sc, mat(c, .55, sss=.2), (0, 1.0, z), r, r, h, bevel=.18)
        cyl(sc, mat("ff5d8f", .2, coat=1), (0, 1.0, z - .1), r + .03, r + .03, .22, bevel=.1)
        top = z + h / 2
        torus(sc, cream, (0, 1.0, top), r - .06, .22)
        for k in range(int(r * 9)):
            a_ = TAU * k / int(r * 9)
            drop = rnd.uniform(.15, .65)
            px, py = (r - .02) * math.cos(a_), 1.0 + (r - .02) * math.sin(a_)
            tube(sc, cream, [(px, py, top), (px, py, top - drop)], .15, .85)
            ball(sc, cream, (px, py, top - drop), .15)
        for k in range(int(r * 3.2)):
            a_ = TAU * k / int(r * 3.2) + .3
            berry((r - .4) * math.cos(a_), 1.0 + (r - .4) * math.sin(a_), top + .42, .3)

    for x, y, z, s in ((-4.1, -2.6, -6.1, 1.0), (4.3, -1.5, -6.1, 1.25), (-7.5, 7, -6, 2.0), (8.0, 11, -6, 2.3), (2.7, -5, -6.3, .65)):
        swirl(x, y, z, s)

    # マカロンの塔
    for bx, by, n, sz in ((-3.7, -.5, 5, .95), (3.9, 2.2, 6, 1.0), (-8.5, 2, 4, 1.2)):
        z = -5.9
        for k in range(n):
            c = colors[(k + int(bx)) % len(colors)]
            ox = rnd.uniform(-.14, .14)
            for dz in (-.2, .2):
                ball(sc, mat(c, .5, sss=.2), (bx + ox, by, z + dz * sz), sz * .82, scale=(1, 1, .32))
            cyl(sc, cream, (bx + ox, by, z), sz * .74, sz * .74, sz * .17)
            z += .62 * sz

    # ドーナツ（浮いて回る）
    for x, y, z, s, c, ph in ((-3.2, .5, 3.9, 1.15, "ff5d8f", 0), (3.5, 2, 5.6, 1.3, "6a3d2a", .3), (3.6, -1.5, .4, .75, "5ad1e8", .6),
                              (-6.5, 12, 7.5, 1.6, "ffd23f", .8), (.5, 18, 11, 1.8, "9d7bff", .15)):
        g = empty(sc, scale=(s, s, s))
        torus(sc, mat("e0a15c", .6, sss=.2), (0, 0, 0), 1.0, .46, parent=g)
        torus(sc, mat(c, .18, coat=1), (0, 0, .13), 1.0, .42, scale=(1.02, 1.02, .92), parent=g)
        for k in range(48):
            a_, off = rnd.uniform(0, TAU), rnd.uniform(-.26, .26)
            rr = 1.02 + off
            zz = .13 + .39 * math.sqrt(max(0, 1 - (off / .43) ** 2))
            tube(sc, mat(rnd.choice(colors + ["ffffff"]), .3, .15), [(-.08, 0, 0), (.08, 0, 0)], .032,
                 loc=(rr * math.cos(a_), rr * math.sin(a_), zz), rot=(0, 0, rnd.uniform(0, 3)), parent=g)

        def spin(t, g=g, base=(x, y, z), ph=ph):
            g.location = (base[0], base[1], base[2] + .55 * math.sin(TAU * (3 * t + ph)))
            g.rotation_euler = (math.radians(62) + .35 * math.sin(TAU * (2 * t + ph)),
                                .4 * math.cos(TAU * (2 * t + ph)), TAU * (t + ph))
        anim.append(spin)

    # ぐるぐるキャンディ
    for x, y, h, s, sp in ((-5.0, 3, 7.4, 1.5, 3), (5.4, 5, 6.2, 1.35, -3), (-11, 13, 10, 2.2, 2), (11.5, 16, 11, 2.4, -2), (6.4, -.5, 3.2, .85, 2)):
        tube(sc, mat("ffffff", .3), [(x, y, -6.5), (x, y, -6.5 + h)], .17)
        g = empty(sc, loc=(x, y, -6.5 + h + s * .8))
        c1, c2 = rnd.sample(colors, 2)
        cyl(sc, mat(c1, .15, coat=1), (0, 0, 0), s, s, .45, bevel=.2, rot=(math.pi / 2, 0, 0), parent=g)
        for arm in range(4):
            pts = [(s * .93 * f * math.cos(f * 5 + arm * TAU / 4), -.24, s * .93 * f * math.sin(f * 5 + arm * TAU / 4))
                   for f in (i / 40 for i in range(41))]
            tube(sc, mat(c2 if arm % 2 else "ffffff", .15, .1, coat=1), pts, .11 * s, parent=g)
        anim.append(lambda t, g=g, sp=sp: setattr(g, "rotation_euler", (0, TAU * sp * t, 0)))

    # キャンディケイン
    for x, y, s, flip in ((-2.9, -4.6, .75, 1), (4.9, -3.6, 1.0, -1), (-5.8, -1.8, 1.25, 1), (9.5, 4, 1.6, -1)):
        path = [(0, 0, i * .3) for i in range(11)] + \
               [(.8 - .8 * math.cos(a_), 0, 3 + .8 * math.sin(a_)) for a_ in (math.pi * i / 12 for i in range(1, 13))]
        for i in range(len(path) - 1):
            tube(sc, mat("ff2d55" if i % 2 else "ffffff", .15, coat=1), path[i:i + 2], .24,
                 loc=(x, y, -6.5), scale=(s * flip, s, s))

    for k in range(34):  # 綿あめの雲
        cx = [-6.5, 6.8, -2.0, 9.5, -10][k % 5] + rnd.uniform(-1.8, 1.8)
        cz = [9.5, 10.5, 14.5, 3.5, 3.0][k % 5] + rnd.uniform(-.5, .5)
        ball(sc, mat(["ffffff", "ffd1ec", "d9f4ff"][k % 3], .9, .22), (cx, 22 + rnd.uniform(-1, 1), cz), rnd.uniform(.7, 1.6))

    flakes = []
    for _ in range(190):  # 降るチョコスプレー
        ob = tube(sc, mat(rnd.choice(colors), .3, .3), [(-.13, 0, 0), (.13, 0, 0)], .05)
        flakes.append((ob, rnd.uniform(-11, 11), rnd.uniform(-3, 18), rnd.random(), rnd.randint(1, 3)))

    def fall(t):
        for ob, x, y, ph, sp in flakes:
            z = (ph - sp * t) % 1
            ob.location = (x + .4 * math.sin(TAU * (2 * z + ph)), y, -7 + 21 * z)
            ob.rotation_euler = (TAU * (z * 3 + ph), TAU * z * 2, ph * 6)
    anim.append(fall)
    return sc, anim


bpy.ops.wm.read_factory_settings(use_empty=True)
WORLDS = [underwater(), night(), sweets()]
TOTAL = PER * len(WORLDS)
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
    """levelの世界(中心center・倍率scale)の中にある泡と、その中の次の世界を重ねる。"""
    px, py = PORTAL[level % 3]
    c = (center[0] + px * scale, center[1] + py * scale)
    r = R * scale
    rp, cx, cy = r * W, (c[0] + 0.5) * W, c[1] * W + H / 2
    halo = 1.18
    x0, y0 = max(0, int(cx - rp * halo)), max(0, int(cy - rp * halo))
    x1, y1 = min(W, int(cx + rp * halo) + 2), min(H, int(cy + rp * halo) + 2)
    if depth > 2 or rp < 3 or x1 - x0 < 4 or y1 - y0 < 4:
        return
    child = (level + 1) % 3
    inner = render(WORLDS[child][0], x0, y0, x1, y1, c, scale * S)
    sub = np.zeros((H, W, 3), np.float32)
    sub[y0:y1, x0:x1] = inner
    portal(sub, child, c, scale * S, depth + 1)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    dx, dy = (xx + .5 - cx) / rp, (yy + .5 - cy) / rp
    d = np.sqrt(dx * dx + dy * dy)
    mask = np.clip((1 - d) * rp + .5, 0, 1)[..., None]
    fade = float(1 - smooth(0.3, 0.95, r))  # 寄るほど泡の縁は消える
    area = canvas[y0:y1, x0:x1]
    glow = (np.exp(-((d - 1) / .06) ** 2) * (d > 1) * .45 * fade)[..., None]
    area += glow * (np.array([.75, .92, 1.0], np.float32) - area)
    body = sub[y0:y1, x0:x1].copy()
    rim = smooth(.72, 1.0, d) * .55 * fade
    hue = np.arctan2(dy, dx)
    film = np.stack([.75 + .25 * np.cos(hue + k) for k in (0, 2.1, 4.2)], -1)  # シャボン膜の虹色
    body += rim[..., None] * (film - body)
    spec = np.exp(-(((dx + .46) * .8 + (dy - .52) * -.2) ** 2 / .018 + ((dy - .52) ** 2) / .008))
    spec += .7 * np.exp(-((dx - .5) ** 2 + (dy + .56) ** 2) / .003)
    body += (np.clip(spec, 0, 1) * .9 * fade)[..., None] * (1 - body)
    area += mask * (body - area)


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


os.makedirs(OUT, exist_ok=True)
for f in FRAMES:
    t = f / TOTAL
    for _, anim in WORLDS:
        for fn in anim:
            fn(t)
    i, u = (f // PER) % 3, (f % PER) / PER
    u -= 0.6 * math.sin(TAU * u) / TAU  # 世界を見せる所はゆっくり、くぐる所は速く
    k = S ** u
    p = PORTAL[i]
    scale = 1 / k
    center = (-p[0] * (1 - k) / (1 - S) / k, -p[1] * (1 - k) / (1 - S) / k)
    canvas = render(WORLDS[i][0], 0, 0, W, H, center, scale).copy()
    portal(canvas, i, center, scale, 0)
    rgba = np.ones((H, W, 4), np.float32)
    rgba[..., :3] = np.clip(bloom(canvas), 0, 1)
    out = bpy.data.images.new("out", W, H, alpha=True)
    out.pixels.foreach_set(rgba.ravel())
    out.filepath_raw, out.file_format = os.path.join(OUT, f"{f:04d}.png"), "PNG"
    out.save()
    bpy.data.images.remove(out)
    print("frame", f, flush=True)
