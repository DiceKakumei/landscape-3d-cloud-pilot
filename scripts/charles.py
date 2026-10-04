# シャルルMV風フィルターを画像にかけるエントリスクリプト（Blender 5.0 headless）
# blender --background --python scripts/charles.py -- <入力画像> <出力PNG> '<上書きパラメータJSON>' [被写体マスク画像]
# ノードの中身は scripts/charles_nodes.py（原本: 1_アプリ開発/シャルルフィルター/charles_nodes.py）
import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import charles_nodes as cn  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
image_path, out_path = os.path.abspath(argv[0]), os.path.abspath(argv[1])
overrides = json.loads(argv[2]) if len(argv) > 2 and argv[2].strip() else {}

params = dict(cn.DEFAULTS)
unknown = set(overrides) - set(params)
if unknown:
    raise SystemExit(f"未知のパラメータ: {sorted(unknown)} / 使えるもの: {sorted(params)}")
for k, v in overrides.items():
    params[k] = cn.lin(v) if k in cn.COLOR_KEYS else v  # 色は "#RRGGBB" で指定

mask_path = os.path.abspath(argv[3]) if len(argv) > 3 and argv[3].strip() and os.path.exists(argv[3]) else None
if mask_path is None:
    params["Shadow Strength"] = 0.0  # マスクが無いと全面が影になるため
elif "Ground Y" not in overrides:
    # マスクの最下端を「接地の高さ」にする（Blenderの画像は下の行から並ぶ）
    import numpy as np
    mi = bpy.data.images.load(mask_path, check_existing=True)
    w, h = mi.size
    a = np.array(mi.pixels[:], dtype=np.float32).reshape(h, w, 4)[:, :, 0]
    rows = np.where((a > 0.5).any(axis=1))[0]
    gy = float(rows.min()) / h if len(rows) else 0.0
    params["Ground Y"] = gy
    if gy < 0.03:  # 被写体が下端に接している（花など）なら影は付けない
        params["Shadow Strength"] = 0.0
    print("ground y:", gy)
g = cn.build(defaults=params)
ng = cn.setup_scene(image_path, out_path, mask_path=mask_path)
sc = bpy.context.scene
try:
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 1
except (TypeError, AttributeError) as e:
    print("engine fallback:", e)
if hasattr(sc.render, "compositor_device"):
    sc.render.compositor_device = "CPU"
if hasattr(sc.render, "compositor_precision"):
    sc.render.compositor_precision = "FULL"

bpy.ops.render.render(write_still=True)
print("wrote", out_path)

# 線画マスクも出力（確認用）
tree = sc.compositing_node_group
o = next(n for n in tree.nodes if n.type == "GROUP_OUTPUT")
tree.links.new(ng.outputs["Lines"], o.inputs["Image"])
sc.render.filepath = os.path.splitext(out_path)[0] + "_lines.png"
bpy.ops.render.render(write_still=True)
print("wrote", sc.render.filepath)

tree.links.new(ng.outputs["Tone"], o.inputs["Image"])
sc.render.filepath = os.path.splitext(out_path)[0] + "_tone.png"
bpy.ops.render.render(write_still=True)

# 配布用に node group を .blend にも保存（Appendして使える）
blend_path = os.path.splitext(out_path)[0] + ".blend"
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print("saved", blend_path)
