# ミニチュア（ティルトシフト）フィルターを画像にかけるエントリスクリプト（Blender 5.0 headless）
# blender --background --python scripts/miniature.py -- <入力画像> <出力PNG> '<上書きパラメータJSON>'
# ノードの中身は scripts/miniature_nodes.py（原本: 1_アプリ開発/ミニチュアフィルター/build_miniature.py）
import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import miniature_nodes as mn  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
image_path, out_path = os.path.abspath(argv[0]), os.path.abspath(argv[1])
overrides = json.loads(argv[2]) if len(argv) > 2 and argv[2].strip() else {}

# "_" で始まるキーはノード以外のシーン設定（例: "_view_transform": "Standard"）
scene_opts = {k: overrides.pop(k) for k in list(overrides) if k.startswith("_")}
params = dict(mn.DEFAULTS)
unknown = set(overrides) - set(params)
if unknown:
    raise SystemExit(f"未知のパラメータ: {sorted(unknown)} / 使えるもの: {sorted(params)}")
params.update(overrides)

g = mn.build(defaults=params)
# 切り分け用："_mute": ["CompositorNodeKuwahara", ...] で該当ノードをミュート（入力をそのまま通す）
for n in g.nodes:
    if n.bl_idname in scene_opts.get("_mute", []):
        n.mute = True
        print("muted", n.name)
ng = mn.setup_scene(image_path, out_path)
sc = bpy.context.scene

# GPUの無いランナーでも動くよう Cycles(CPU, 1サンプル) で空シーンを描画し、結果はコンポジットで置き換わる
try:
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 1
except (TypeError, AttributeError) as e:
    print("engine fallback:", e)
if hasattr(sc.render, "compositor_device"):
    sc.render.compositor_device = "CPU"
if "_view_transform" in scene_opts:
    sc.view_settings.view_transform = scene_opts["_view_transform"]
    sc.view_settings.look = "None"
img = next(i for i in bpy.data.images if i.filepath)
print("color:", sc.display_settings.display_device, sc.view_settings.view_transform,
      sc.view_settings.look, "image:", img.colorspace_settings.name, img.is_float, img.depth)

bpy.ops.render.render(write_still=True)
print("wrote", out_path)

# ぼけ量マスクも出力（確認用）
tree = sc.compositing_node_group
o = next(n for n in tree.nodes if n.type == "GROUP_OUTPUT")
tree.links.new(ng.outputs["Mask"], o.inputs["Image"])
sc.render.filepath = os.path.splitext(out_path)[0] + "_mask.png"
bpy.ops.render.render(write_still=True)
print("wrote", sc.render.filepath)
print("params", json.dumps(params, ensure_ascii=False))
