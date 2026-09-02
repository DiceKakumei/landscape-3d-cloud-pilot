"""
自動リトポロジー: 高ポリglb -> Voxel Remesh(manifold化) -> QuadriFlow Remesh(自動リトポ) -> 低ポリglb。
GitHub Actions上でのheadless実行を想定(blender --background --python このファイル)。

retopo_mt.py(手動専用アドオン、マウスでのquad描画)はheadlessでは動かせないため使わない。
Blender標準のQuadriFlow Remeshで代替する(参照: cloud_render/README.mdの「retopo_mt.pyについて」)。

入力: $GITHUB_WORKSPACE/assets/*.glb (複数可。ファイルごとに1つずつリトポする)
出力: $GITHUB_WORKSPACE/output/<元のファイル名>_retopo.glb
環境変数 TARGET_FACES で目標面数を指定可能(デフォルト5000)。
"""
import bpy
import glob
import os

WORKSPACE = os.environ.get("GITHUB_WORKSPACE", os.getcwd())
ASSET_DIR = os.path.join(WORKSPACE, "assets")
OUTPUT_DIR = os.path.join(WORKSPACE, "output")
TARGET_FACES = int(os.environ.get("TARGET_FACES", "5000"))
os.makedirs(OUTPUT_DIR, exist_ok=True)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in list(bpy.data.meshes):
        if block.users == 0:
            bpy.data.meshes.remove(block)


def import_glb_as_single_mesh(filepath):
    """glbをインポートし、軸変換用の親Emptyのtransformを子に焼き込んでから外し、
    複数メッシュがあれば1つに結合して返す。風景3DCG再現スキルのimport_glb_scaledと
    同じ理由(親のscaleぶん後続計算がズレるのを防ぐ)でtransform_applyしておく。
    """
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=filepath)
    imported = [o for o in bpy.data.objects if o not in before]
    meshes = [o for o in imported if o.type == "MESH"]
    if not meshes:
        raise RuntimeError(f"{filepath}: メッシュが見つかりません")

    for o in imported:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")

    for o in bpy.context.selected_objects:
        if o.type != "MESH":
            o.select_set(False)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return obj


def retopo(obj, target_faces):
    """Voxel Remeshでmanifold化してからQuadriFlow Remeshで目標面数にリトポする。
    どちらもObject modeのオペレータ(Edit modeに入る必要はない)。
    """
    before_faces = len(obj.data.polygons)

    # Voxel Remesh: メッシュサイズに対して十分細かいvoxelで一旦manifold化する。
    # 対角線の長さを基準に、全体を概ね128分割になるサイズを目安にする。
    dims = obj.dimensions
    diag = (dims.x ** 2 + dims.y ** 2 + dims.z ** 2) ** 0.5
    obj.data.remesh_voxel_size = max(diag / 128.0, 1e-4)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.voxel_remesh()

    after_voxel_faces = len(obj.data.polygons)

    # QuadriFlow Remeshは、bmeshのis_manifoldチェックでは検出できない程度の
    # 微小な重複頂点があるだけでも「manifoldでない」と判定して黙って何もせず
    # 終了する(面数が変化しない・例外も出ない)。実際にMeshy生成キャラクターで
    # このバグを踏んだ(重複頂点2つが原因)。事前にmerge by distance + 縮退ジオメトリ
    # 除去 + 法線統一をかけておくこと。
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.0001)
    bpy.ops.mesh.dissolve_degenerate(threshold=0.0001)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")

    # QuadriFlow Remesh: 目標面数に自動リトポ(quad primitive)。
    bpy.ops.object.quadriflow_remesh(
        mode="FACES",
        target_faces=target_faces,
        use_mesh_symmetry=False,
        use_preserve_sharp=False,
        use_preserve_boundary=False,
        smooth_normals=True,
    )

    after_quadriflow_faces = len(obj.data.polygons)
    print(
        f"[check] {obj.name}: faces before={before_faces} "
        f"after_voxel={after_voxel_faces} after_quadriflow={after_quadriflow_faces} "
        f"(target={target_faces})"
    )
    # QuadriFlow Remeshはmanifoldでないメッシュに対して警告を出すだけで面数を
    # 変えずに黙って終了することがある(上記コメント参照)。面数がvoxel remesh後と
    # 変わっていなければ検出漏れとみなしてここで確実に落とす。
    if after_quadriflow_faces == after_voxel_faces:
        raise RuntimeError(
            f"{obj.name}: QuadriFlow Remeshが実行されなかった可能性があります "
            f"(面数がVoxel Remesh後から変化していません: {after_quadriflow_faces})"
        )


glb_files = sorted(glob.glob(os.path.join(ASSET_DIR, "*.glb")))
if not glb_files:
    raise RuntimeError(f"{ASSET_DIR} にglbファイルが見つかりません")

for filepath in glb_files:
    clear_scene()
    obj = import_glb_as_single_mesh(filepath)
    retopo(obj, TARGET_FACES)

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    base_name = os.path.splitext(os.path.basename(filepath))[0]
    out_path = os.path.join(OUTPUT_DIR, f"{base_name}_retopo.glb")
    bpy.ops.export_scene.gltf(filepath=out_path, use_selection=True, export_format="GLB")
    print("DONE:", out_path)
