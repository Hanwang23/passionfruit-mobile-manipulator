import argparse
from pathlib import Path
from struct import unpack

from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.IFSelect import IFSelect_RetDone
from OCP.IMeshTools import IMeshTools_Parameters, IMeshTools_MeshAlgoType_Delabella
from OCP.OCP.collections import Sequence_TDF_Label
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.StlAPI import StlAPI_Writer
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import TopAbs_FACE, TopAbs_FORWARD, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool


def mesh_missing_face(face):
    # Retry the exact trimmed surface with a second meshing algorithm.
    # Work in its local CAD coordinates so the assembly pose is preserved.
    local = TopoDS.Face(face.Located(TopLoc_Location()).Oriented(TopAbs_FORWARD))
    copy = TopoDS.Face(BRepBuilderAPI_Copy(local, False, False).Shape())
    parameters = IMeshTools_Parameters()
    parameters.Deflection = 0.04
    parameters.Angle = 0.25
    parameters.MeshAlgo = IMeshTools_MeshAlgoType_Delabella
    BRepMesh_IncrementalMesh(copy, parameters)
    triangles = BRep_Tool.Triangulation_s(copy, TopLoc_Location())
    if triangles is None:
        raise RuntimeError("Could not tessellate a trimmed spline face")
    BRep_Builder().UpdateFace(local, triangles)


def export_mesh(shape, path, linear_deflection, angular_deflection):
    print(f"Meshing {path.name}", flush=True)
    mesh = BRepMesh_IncrementalMesh(shape, linear_deflection, False, angular_deflection, True)
    if not mesh.IsDone():
        raise RuntimeError(f"Tessellation failed for {path}")
    faces = TopExp_Explorer(shape, TopAbs_FACE)
    while faces.More():
        face = TopoDS.Face(faces.Current())
        if BRep_Tool.Triangulation_s(face, TopLoc_Location()) is None:
            mesh_missing_face(face)
            print("Retessellated one original trimmed spline face", flush=True)
        faces.Next()
    writer = StlAPI_Writer()
    writer.ASCIIMode = False
    if not writer.Write(shape, str(path)):
        raise RuntimeError(f"STL write failed for {path}")
    with path.open("rb") as stream:
        stream.seek(80)
        count, = unpack("<I", stream.read(4))
    if count == 0:
        raise RuntimeError(f"Empty tessellation for {path}")
    print(f"{path.name} has {count:,} triangles", flush=True)


def name(label):
    attribute = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attribute):
        return attribute.Get().ToExtString()
    return ""


def find_component(label, location, product):
    if name(label) == product:
        return XCAFDoc_ShapeTool.GetShape_s(label).Moved(location)
    instances = Sequence_TDF_Label()
    XCAFDoc_ShapeTool.GetComponents_s(label, instances)
    for instance in instances:
        referent = TDF_Label()
        XCAFDoc_ShapeTool.GetReferredShape_s(instance, referent)
        match = find_component(referent, location * XCAFDoc_ShapeTool.GetLocation_s(instance), product)
        if match is not None:
            return match
    return None


def main(step_file, output):
    doc = TDocStd_Document(TCollection_ExtendedString("XmlXCAF"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    if reader.ReadFile(str(step_file)) != IFSelect_RetDone or not reader.Transfer(doc):
        raise RuntimeError(f"STEP import failed for {step_file}")
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    roots = Sequence_TDF_Label()
    tool.GetFreeShapes(roots)
    if roots.Length() != 1:
        raise RuntimeError(f"Expected one Gemini 336L assembly in {step_file}")

    root = roots.Value(1)
    assembly = tool.GetShape_s(root)
    builder = BRep_Builder()
    envelope = TopoDS_Compound()
    builder.MakeCompound(envelope)
    # Outer housing and front window, in the manufacturer's assembly coordinates.
    for product in ("1111_3_1", "0002_2_1"):
        part = find_component(root, TopLoc_Location(), product)
        if part is None:
            raise RuntimeError(f"Gemini 336L STEP component {product} is missing")
        builder.Add(envelope, part)

    # Keep the physical solids in their original assembly placements.
    # The STEP also has unclosed optical reference surfaces.
    solids = TopoDS_Compound()
    builder.MakeCompound(solids)
    explorer = TopExp_Explorer(assembly, TopAbs_SOLID)
    while explorer.More():
        builder.Add(solids, explorer.Current())
        explorer.Next()
    output.mkdir(parents=True, exist_ok=True)
    export_mesh(envelope, output / "gemini_336l_housing_collision.stl", 0.08, 0.35)
    export_mesh(solids, output / "gemini_336l_assembly.stl", 0.04, 0.25)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tessellate the original Gemini 336L STEP assembly in millimeters.")
    parser.add_argument("step_file", type=Path)
    parser.add_argument("output_directory", type=Path)
    args = parser.parse_args()
    main(args.step_file, args.output_directory)
