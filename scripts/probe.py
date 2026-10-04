import bpy
t = bpy.data.node_groups.new("p", "CompositorNodeTree")
for ty in ("CompositorNodeTransform", "CompositorNodeImageInfo", "CompositorNodeTranslate", "CompositorNodeScale"):
    try:
        n = t.nodes.new(ty)
        print("PROBE", ty, "IN", [(s.name, s.bl_idname) for s in n.inputs], "OUT", [s.name for s in n.outputs])
    except Exception as e:
        print("PROBE", ty, "ERR", e)
