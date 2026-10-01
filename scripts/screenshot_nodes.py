# ノードグループ「Miniature」の中身とコンポジター全体をGUIでスクショして終了する
# クラウド: xvfb-run blender -p 0 0 2560 1440 --factory-startup --python scripts/screenshot_nodes.py -- <入力画像> <出力フォルダ>
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import miniature_nodes as bm  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
IMG, OUT = os.path.abspath(argv[0]), os.path.abspath(argv[1])
g = bm.build()
bm.setup_scene(IMG, os.path.join(OUT, "_tmp.png"))


def node_area():
    win = bpy.context.window_manager.windows[0]
    area = max(win.screen.areas, key=lambda a: a.width * a.height)
    area.ui_type = "CompositorNodeTree"
    return win, area


def shot(win, area, path):
    # Blender内蔵のscreenshotはXvfbでは真っ黒になるため、外部(ImageMagick import)に撮らせる。
    # <path>.ready を置き、シェル側が撮影して <path>.done を置くまで待つ
    region = next(r for r in area.regions if r.type == "WINDOW")
    with bpy.context.temp_override(window=win, area=area, region=region):
        bpy.ops.node.view_all()
    bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=3)
    open(path + ".ready", "w").close()
    print("ready", path)


def wait_done(path):
    return os.path.exists(path + ".done")


state = {"step": 0}


def tick():
    win, area = node_area()
    space = area.spaces.active
    step = state["step"]
    if step == 0:
        # 他のエリアを隠してノードエディタを全画面に
        with bpy.context.temp_override(window=win, area=area):
            bpy.ops.screen.screen_full_area(use_hide_panels=True)
    elif step == 1:
        shot(win, node_area()[1], os.path.join(OUT, "nodes_compositor.png"))
    elif step == 2:
        if not wait_done(os.path.join(OUT, "nodes_compositor.png")):
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
            return 0.5
    elif step == 3:
        # グループの中に入る
        space = node_area()[1].spaces.active
        space.path.append(g)
    elif step == 4:
        shot(win, node_area()[1], os.path.join(OUT, "nodes_miniature_group.png"))
    elif step == 5:
        if not wait_done(os.path.join(OUT, "nodes_miniature_group.png")):
            bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=1)
            return 0.5
    else:
        bpy.ops.wm.quit_blender()
        return None
    state["step"] += 1
    return 1.0


def safe_tick():
    try:
        return tick()
    except Exception:
        import traceback
        traceback.print_exc()
        bpy.ops.wm.quit_blender()
        return None


bpy.app.timers.register(safe_tick, first_interval=2.0)
