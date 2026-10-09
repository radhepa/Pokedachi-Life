using SPICA.Formats.CtrGfx;
using SPICA.Formats.CtrGfx.Model;
using SPICA.Formats.CtrGfx.Model.Mesh;

using System;
using System.IO;
using System.Linq;
using System.Numerics;

namespace PokeTool
{
    // Debug builds that put several variants side by side in ONE body model, so a single in-game
    // screenshot compares them under identical lighting.
    static class Experiments
    {
        // matgrid <template> <pokemon> <out> <animCm> <look,look,...> [spacing]
        public static void MatGrid(string template, string poke, string outPath, string animCm, int[] looks, float spacing)
        {
            string tmp = Path.Combine(Path.GetTempPath(), "pokedachi_grid");
            Directory.CreateDirectory(tmp);
            Gfx baseFile = null;
            GfxModel baseModel = null;

            for (int i = 0; i < looks.Length; i++)
            {
                string p = Path.Combine(tmp, $"v{i}.bin");
                Convert.Run(template, poke, p, new Convert.Options { RestAnimFile = animCm, Look = looks[i], Height = 0.8f, MaterialTemplate = template });
                Gfx g = Gfx.Open(p);
                GfxModel m = g.Models[0];
                float dx = (i - (looks.Length - 1) / 2f) * spacing;

                foreach (GfxShape sh in m.Shapes) ShiftX(sh, dx);
                foreach (var mat in m.Materials) mat.Name = mat.Name + "_v" + i;

                if (baseFile == null)
                {
                    baseFile = g;
                    baseModel = m;
                    continue;
                }

                foreach (var tex in g.Textures.ToList())
                {
                    if (!baseFile.Textures.Contains(tex.Name)) baseFile.Textures.Add(tex);
                }
                int shapeBase = baseModel.Shapes.Count, matBase = baseModel.Materials.Count;
                foreach (GfxShape sh in m.Shapes) baseModel.Shapes.Add(sh);
                foreach (var mat in m.Materials.ToList()) baseModel.Materials.Add(mat);
                foreach (GfxMesh mesh in m.Meshes.ToList())
                {
                    mesh.ShapeIndex += shapeBase;
                    mesh.MaterialIndex += matBase;
                    mesh.Parent = baseModel;
                    baseModel.Meshes.Add(mesh);
                }
            }

            // Material anim groups reference material names; drop them for the grid.
            if (baseModel.AnimationsGroup.Contains("MaterialAnimation"))
                baseModel.AnimationsGroup.Remove(baseModel.AnimationsGroup["MaterialAnimation"]);

            Gfx.Save(outPath, baseFile);
            Console.WriteLine($"grid of {looks.Length} looks -> {outPath}");
        }

        static void ShiftX(GfxShape sh, float dx)
        {
            var il = sh.VertexBuffers.OfType<GfxVertexBufferInterleaved>().First();
            var pos = il.Attributes.First(a => a.AttrName == SPICA.PICA.Commands.PICAAttributeName.Position);
            int n = il.RawBuffer.Length / il.VertexStride;
            for (int i = 0; i < n; i++)
            {
                int o = i * il.VertexStride + pos.Offset;
                float x = BitConverter.ToSingle(il.RawBuffer, o) + dx;
                BitConverter.GetBytes(x).CopyTo(il.RawBuffer, o);
            }
            var c = sh.BoundingBox.Center;
            sh.BoundingBox.Center = new Vector3(c.X + dx, c.Y, c.Z);
        }
    }
}
