using SPICA.Formats.CtrGfx;
using SPICA.Formats.CtrGfx.Animation;
using SPICA.Formats.CtrGfx.Model;
using SPICA.Formats.CtrGfx.Model.Mesh;
using SPICA.Formats.CtrGfx.Texture;
using SPICA.Math3D;
using SPICA.PICA.Commands;

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Numerics;

namespace PokeTool
{
    // Turns a Pokémon Rumble Blast model into a Tomodachi Life body model.
    //
    // The output keeps the Tomodachi file's identity (model name, 26-bone skeleton, bone names and
    // hierarchy, skeletal anim group, mesh node name) so the game and all 2701 body animations treat it
    // as a normal Mii body, but every mesh, material and texture is the Pokémon's. Each Rumble part
    // (rigid toy piece) is skinned 100% to one Mii bone, and the Mii joints are moved onto the
    // Pokémon's own pivots. Tomodachi animations only rotate those joints, so moving them is safe.
    //
    // Rest pose = bodyCmWaitStop00 (Tomodachi's standing pose): when a Mii stands still, the Pokémon
    // looks exactly as authored.
    static class Convert
    {
        public class Options
        {
            public float Height = 1.1f;             // target height in Tomodachi units (a Mii is ~1.6 with its head)
            public string RestAnimFile;             // body_common_animCm.bin
            public string RestAnimName = "bodyCmWaitStop00";
            public bool KeepSkeleton;               // debug: leave the Mii skeleton untouched
            public bool TemplateMaterial;           // debug: draw the Pokémon with the outfit's own material/textures
            public int Look = 5;                    // material preset, see ApplyLook; 5 = clone of Mii clothes material
            public string MaterialTemplate;         // body file whose mtBdDef is cloned for Look 5 (body_body000.bin)
            public float HeadTop = float.NaN;       // if set: scale so the top of the head is here (Height = max height)
        }

        // Look 5: every Pokémon material becomes a copy of Tomodachi's own outfit material (mtBdDef), so it
        // reacts to all of the game's lights and runtime effects exactly like Mii clothes do. Slots:
        //   Texture0 = flat normal map (bump stage leaves the vertex normal alone)
        //   Texture1 = the Pokémon's texture, with its own sampler and UV transform
        //   Texture2 = colour mask: r=g=0 (no favourite-colour regions), a=1 (no darkening)
        // Unique per Pokémon: the game shares textures by name across loaded models, and a model
        // swapped in while the old one is freed would otherwise bind to the freed copies.
        [ThreadStatic] static string FlatNormalTex;
        [ThreadStatic] static string MaskTex;

        static SPICA.Formats.CtrGfx.Model.Material.GfxMaterial CloneMiiMaterial(
            string materialTemplate, SPICA.Formats.CtrGfx.Model.Material.GfxMaterial pmat, string name)
        {
            Gfx t = Gfx.Open(materialTemplate);
            var m = t.Models[0].Materials["mtBdDef"];
            m.Name = name;
            m.TextureMappers[1] = pmat.TextureMappers[0];
            m.TextureCoords[1] = pmat.TextureCoords[0];
            m.TextureMappers[0].Texture.Path = FlatNormalTex;
            m.TextureMappers[2].Texture.Path = MaskTex;

            // Alpha straight from the Pokémon texture (stage 3 feeds stages 4 and 5).
            var s3 = m.FragmentShader.TextureEnvironments[3].Stage;
            s3.Source.Alpha[0] = PICATextureCombinerSource.Texture1;
            s3.Operand.Alpha[0] = PICATextureCombinerAlphaOp.Alpha;

            // See-through parts (wings, flames, ghosts) keep their blending / alpha test / layer / culling.
            bool translucent = pmat.FragmentOperation.Blend.Mode != SPICA.Formats.CtrGfx.Model.Material.GfxFragOpBlendMode.None ||
                               pmat.FragmentShader.AlphaTest.Test.Enabled;
            if (translucent)
            {
                m.FragmentOperation = pmat.FragmentOperation;
                m.FragmentShader.AlphaTest = pmat.FragmentShader.AlphaTest;
                m.TranslucencyKind = pmat.TranslucencyKind;
            }
            m.Rasterization = pmat.Rasterization;
            return m;
        }

        static void AddHelperTextures(Gfx outFile, string materialTemplate)
        {
            if (outFile.Textures.Contains(FlatNormalTex)) return;
            Gfx t = Gfx.Open(materialTemplate);
            GfxTexture nrm = t.Textures.First(x => x.HwFormat == PICATextureFormat.HiLo8);
            GfxTexture mask = t.Textures.First(x => x.HwFormat == PICATextureFormat.RGBA4);
            MakeSolid(nrm, FlatNormalTex, new byte[] { 0x80, 0x80 });
            MakeSolid(mask, MaskTex, new byte[] { 0x0F, 0x00 });  // RGBA4: r=g=b=0, a=15
            outFile.Textures.Add(nrm);
            outFile.Textures.Add(mask);
        }

        static void MakeSolid(GfxTexture tex, string name, byte[] texel)
        {
            var img = (GfxTextureImage)tex;
            img.Name = name;
            img.Width = img.Height = 8;
            img.MipmapSize = 1;
            img.Image.Width = img.Image.Height = 8;
            var buf = new byte[8 * 8 * texel.Length];
            for (int i = 0; i < buf.Length; i++) buf[i] = texel[i % texel.Length];
            img.Image.RawBuffer = buf;
        }

        // ETC1 textures came out as noise on Tomodachi bodies (Geodude) back when the IMAG block was
        // misaligned; they're re-encoded uncompressed anyway (ETC1 -> RGB565, ETC1A4 -> RGBA4), the
        // path every working species already used.
        static void TranscodeEtc1(GfxTexture tex)
        {
            if (!(tex is GfxTextureImage img)) return;
            bool a4 = tex.HwFormat == PICATextureFormat.ETC1A4;
            if (!a4 && tex.HwFormat != PICATextureFormat.ETC1) return;
            var fmt = a4 ? PICATextureFormat.RGBA4 : PICATextureFormat.RGB565;
            byte[] abgr;  // SPICA only encodes RGBA8: swizzled texels as A,B,G,R bytes
            using (var bmp = SPICA.PICA.Converters.TextureConverter.DecodeBitmap(img.Image.RawBuffer, tex.Width, tex.Height, tex.HwFormat))
                abgr = SPICA.PICA.Converters.TextureConverter.Encode(bmp, PICATextureFormat.RGBA8);
            var buf = new byte[abgr.Length / 2];
            for (int i = 0, o = 0; i < abgr.Length; i += 4, o += 2)
            {
                int a = abgr[i], b = abgr[i + 1], g = abgr[i + 2], r = abgr[i + 3];
                int v = a4 ? (r >> 4) << 12 | (g >> 4) << 8 | (b >> 4) << 4 | a >> 4
                           : (r >> 3) << 11 | (g >> 2) << 5 | b >> 3;
                buf[o] = (byte)v;
                buf[o + 1] = (byte)(v >> 8);
            }
            img.Image.RawBuffer = buf;
            tex.HwFormat = fmt;
            tex.GLFormat = a4 ? 0x6752u : 0x6754u;
            tex.GLType = a4 ? 0x8033u : 0x8363u;
            tex.MipmapSize = 1;
            img.Image.BitsPerPixel = 16;
        }

        // Lighting presets for Pokémon materials inside Tomodachi's scenes.
        //  0: Tomodachi character light set (2), Rumble specular 128      (first test: washed out)
        //  1: light set 2, no specular
        //  2: Rumble's own light set index (0), no specular
        //  3: item light set (3) + hemisphere, no specular
        //  4: light set 2 + hemisphere, combiner (fragDiffuse + hemisphere) * texture + 1/4 specular
        public static void ApplyLook(SPICA.Formats.CtrGfx.Model.Material.GfxMaterial mat, int look)
        {
            var c = mat.Colors;
            if (look >= 1) { c.Specular0 = new RGBA(0, 0, 0, 0); c.Specular1 = new RGBA(0, 0, 0, 0); }
            if (look == 4) c.Specular0 = new RGBA(64, 64, 64, 0);
            mat.Colors = c;
            mat.LightSetIndex = look == 2 ? 0 : look == 3 ? 3 : 2;
            if (look == 3 || look == 4)
            {
                mat.Flags |= SPICA.Formats.CtrGfx.Model.Material.GfxMaterialFlags.IsHemiSphereLightingEnabled;
            }
            if (look == 4)
            {
                var te = mat.FragmentShader.TextureEnvironments;
                var s0 = te[0].Stage;
                s0.Source.Color[0] = PICATextureCombinerSource.FragmentPrimaryColor;
                s0.Source.Color[1] = PICATextureCombinerSource.PrimaryColor;
                s0.Operand.Color[0] = PICATextureCombinerColorOp.Color;
                s0.Operand.Color[1] = PICATextureCombinerColorOp.Color;
                s0.Combiner.Color = PICATextureCombinerMode.Add;
                var s1 = te[1].Stage;
                s1.Source.Color[0] = PICATextureCombinerSource.Previous;
                s1.Source.Color[1] = PICATextureCombinerSource.Texture0;
                s1.Operand.Color[0] = PICATextureCombinerColorOp.Color;
                s1.Operand.Color[1] = PICATextureCombinerColorOp.Color;
                s1.Combiner.Color = PICATextureCombinerMode.Modulate;
                s1.Source.Alpha[0] = PICATextureCombinerSource.Texture0;
                s1.Operand.Alpha[0] = PICATextureCombinerAlphaOp.Alpha;
                s1.Combiner.Alpha = PICATextureCombinerMode.Replace;
                var s2 = te[2].Stage;
                s2.Source.Color[0] = PICATextureCombinerSource.Previous;
                s2.Source.Color[1] = PICATextureCombinerSource.FragmentSecondaryColor;
                s2.Operand.Color[0] = PICATextureCombinerColorOp.Color;
                s2.Operand.Color[1] = PICATextureCombinerColorOp.Color;
                s2.Combiner.Color = PICATextureCombinerMode.Add;
                s2.Source.Alpha[0] = PICATextureCombinerSource.Previous;
                s2.Operand.Alpha[0] = PICATextureCombinerAlphaOp.Alpha;
                s2.Combiner.Alpha = PICATextureCombinerMode.Replace;
            }
        }

        class Vtx
        {
            public Vector3 Pos;       // model space, after scaling
            public Vector3 Nrm;
            public Vector4 Col = Vector4.One;
            public Vector2 Uv0;
            public string RumbleBone;
            public string MiiBone;
        }

        public static void Run(string templatePath, string pokePath, string outPath, Options opt)
        {
            Gfx tFile = Gfx.Open(templatePath);
            Gfx pFile = Gfx.Open(pokePath);
            string tag = Path.GetFileNameWithoutExtension(pokePath);
            FlatNormalTex = "pkNrm_" + tag;
            MaskTex = "pkMsk_" + tag;
            var tm = (GfxModelSkeletal)tFile.Models[0];
            var pm = (GfxModelSkeletal)pFile.Models[0];

            var miiBones = tm.Skeleton.Bones.ToList();
            var miiByName = miiBones.ToDictionary(b => b.Name);
            var pBones = pm.Skeleton.Bones.ToList();

            // Pokémon bone world matrices (row-vector convention, like SPICA/System.Numerics).
            var pWorld = new Matrix4x4[pBones.Count];
            for (int i = 0; i < pBones.Count; i++) pWorld[i] = WorldOf(pBones, i);

            // ---- 1. Decode every Pokémon vertex into model space with its Rumble bone.
            var shapeVerts = new List<Vtx[]>();
            foreach (GfxShape shape in pm.Shapes)
            {
                shapeVerts.Add(DecodeShape(shape, pBones, pWorld));
            }

            // ---- 2. Scale and ground the Pokémon.
            var all = shapeVerts.SelectMany(v => v).ToList();
            float minY = all.Min(v => v.Pos.Y), maxY = all.Max(v => v.Pos.Y);
            float s = opt.Height / Math.Max(1e-4f, maxY - minY);
            if (!float.IsNaN(opt.HeadTop))
            {
                // Miis are picked up by touching the top of the head and sliding up; the game looks for that
                // touch at a fixed height (a Mii's head top), not on the model. Scale so the top of the
                // Pokémon's head (HEAD part, else everything) reaches HeadTop, without growing past Height
                // (Pokémon with tall ears or leaves are then grabbed by those).
                var headPart = all.Where(v => v.RumbleBone == "HEAD").ToList();
                float rawHeadTop = (headPart.Count > 0 ? headPart : all).Max(v => v.Pos.Y) - minY;
                s = Math.Min(opt.HeadTop / Math.Max(1e-4f, rawHeadTop), s);
            }
            foreach (var v in all) v.Pos = new Vector3(v.Pos.X * s, (v.Pos.Y - minY) * s, v.Pos.Z * s);
            Vector3 PokeJoint(string name)
            {
                int i = pBones.FindIndex(b => b.Name == name);
                if (i < 0) return new Vector3(float.NaN);
                Vector3 p = pWorld[i].Translation;
                return new Vector3(p.X * s, (p.Y - minY) * s, p.Z * s);
            }

            // ---- 3. Rest pose of the Mii skeleton (rotations from bodyCmWaitStop00).
            var restRot = new Dictionary<string, Vector3>();
            Vector3? bodyRestT = null;
            if (opt.RestAnimFile != null)
            {
                Gfx animFile = Gfx.Open(opt.RestAnimFile);
                GfxAnimation rest = animFile.SkeletalAnimations[opt.RestAnimName];
                foreach (GfxAnimationElement e in rest.Elements)
                {
                    if (!(e.Content is GfxAnimTransform t) || !miiByName.ContainsKey(e.Name)) continue;
                    GfxBone b = miiByName[e.Name];
                    if (t.RotationExists)
                    {
                        restRot[e.Name] = new Vector3(
                            ValueAt0(t.RotationX, b.Rotation.X),
                            ValueAt0(t.RotationY, b.Rotation.Y),
                            ValueAt0(t.RotationZ, b.Rotation.Z));
                    }
                    if (e.Name == "body" && t.TranslationExists)
                    {
                        bodyRestT = new Vector3(
                            ValueAt0(t.TranslationX, b.Translation.X),
                            ValueAt0(t.TranslationY, b.Translation.Y),
                            ValueAt0(t.TranslationZ, b.Translation.Z));
                    }
                }
            }

            // Template world positions in the rest pose (used to know which side is "L" and as defaults).
            var restWorld = new Dictionary<string, Matrix4x4>();
            foreach (GfxBone b in miiBones)
            {
                Vector3 r = restRot.TryGetValue(b.Name, out Vector3 rr) ? rr : b.Rotation;
                Vector3 t = b.Name == "body" && bodyRestT.HasValue ? bodyRestT.Value : b.Translation;
                Matrix4x4 local = Local(b.Scale, r, t);
                restWorld[b.Name] = b.ParentIndex < 0 ? local : local * restWorld[miiBones[b.ParentIndex].Name];
            }
            float leftSign = Math.Sign(restWorld["L_shoulder"].Translation.X);
            if (leftSign == 0) leftSign = 1;

            // ---- 4. Assign Mii bones.
            foreach (var v in all) v.MiiBone = MapBone(v.RumbleBone, v.Pos.X * leftSign >= 0);

            // ---- 5. Joint pivots (model space).
            var target = new Dictionary<string, Vector3>();
            Vector3 body = bodyRestT ?? miiByName["body"].Translation;
            Vector3 pBody = Or(PokeJoint("BODY"), Center(all));
            Vector3 pHead = Or(PokeJoint("HEAD"), Or(PokeJoint("NECK"), pBody));
            var headVerts = all.Where(v => v.MiiBone == "neck").ToList();

            target["all_root"] = Vector3.Zero;
            target["body"] = body;
            target["waist"] = pBody;
            target["hips"] = pBody;
            target["neck"] = pHead;
            // 'head' = centre of the head itself (HEAD part, without ears): face close-ups and bubbles aim here.
            var headPartVerts = all.Where(v => v.RumbleBone == "HEAD").ToList();
            target["head"] = headPartVerts.Count > 0 ? Center(headPartVerts) : headVerts.Count > 0 ? Center(headVerts) : pHead;
            target["waistItem"] = pBody;
            target["shadow"] = Vector3.Zero;

            foreach (string side in new[] { "L", "R" })
            {
                var arm = all.Where(v => v.MiiBone == side + "_shoulder").ToList();
                Vector3 armJoint = Or(PokeJoint(side == "L" ? "LEFT_WING" : "RIGHT_WING"), Or(PokeJoint("ARM"), pBody));
                Vector3 shoulder = armJoint;
                if (arm.Count > 0 && !float.IsNaN(PokeJoint("ARM").X))
                {
                    float inner = arm.Min(v => Math.Abs(v.Pos.X));
                    shoulder = new Vector3(inner * (side == "L" ? leftSign : -leftSign), armJoint.Y, armJoint.Z);
                }
                Vector3 hand = arm.Count > 0 ? arm.OrderByDescending(v => (v.Pos - shoulder).LengthSquared()).First().Pos : shoulder;
                target[side + "_shoulder"] = shoulder;
                target[side + "_elbow"] = Vector3.Lerp(shoulder, hand, 0.5f);
                target[side + "_hand1"] = hand;
                target[side + "_handItem"] = hand;

                var leg = all.Where(v => v.MiiBone == side + "_leg").ToList();
                Vector3 legJoint = Or(PokeJoint("LEG"), pBody);
                Vector3 hip = legJoint;
                if (leg.Count > 0)
                {
                    Vector3 c = Center(leg);
                    hip = new Vector3(c.X, legJoint.Y, c.Z);
                }
                Vector3 foot = leg.Count > 0 ? new Vector3(hip.X, leg.Min(v => v.Pos.Y), hip.Z) : new Vector3(hip.X, 0, hip.Z);
                target[side + "_leg"] = hip;
                target[side + "_knee"] = Vector3.Lerp(hip, foot, 0.5f);
                target[side + "_ankle"] = foot;
            }
            foreach (string sk in new[] { "back_skirt1", "back_skirt2", "front_skirt1", "front_skirt2" }) target[sk] = target["hips"];

            // ---- 6. Rewrite the Mii skeleton: rest rotations, translations that put joints on the pivots.
            var newWorld = new Dictionary<string, Matrix4x4>();
            foreach (GfxBone b in opt.KeepSkeleton ? new List<GfxBone>() : miiBones)
            {
                Vector3 rot = restRot.TryGetValue(b.Name, out Vector3 rr) ? rr : b.Rotation;
                Matrix4x4 parentW = b.ParentIndex < 0 ? Matrix4x4.Identity : newWorld[miiBones[b.ParentIndex].Name];
                Vector3 want = target.TryGetValue(b.Name, out Vector3 tw) ? tw : (restWorld[b.Name].Translation);
                Vector3 local;
                if (b.Name == "body") local = body;
                else
                {
                    Matrix4x4.Invert(parentW, out Matrix4x4 invP);
                    local = Vector3.Transform(want, invP);
                }
                Matrix4x4 l = Local(Vector3.One, rot, local);
                Matrix4x4 w = l * parentW;
                newWorld[b.Name] = w;
                Matrix4x4.Invert(w, out Matrix4x4 invW);

                b.Scale = Vector3.One;
                b.Rotation = rot;
                b.Translation = local;
                b.LocalTransform = new Matrix3x4(l);
                b.WorldTransform = Matrix3x4.Identity; // runtime-filled; files store identity
                b.InvWorldTransform = new Matrix3x4(invW);

                GfxBoneFlags f = b.Flags & (GfxBoneFlags.IsSegmentScaleCompensate | GfxBoneFlags.IsLocalMtxCalculate | GfxBoneFlags.IsWorldMtxCalculate);
                f |= GfxBoneFlags.IsScaleVolumeOne | GfxBoneFlags.IsScaleUniform;
                if (local == Vector3.Zero) f |= GfxBoneFlags.IsTranslationZero;
                if (rot == Vector3.Zero) f |= GfxBoneFlags.IsRotationZero;
                if (local == Vector3.Zero && rot == Vector3.Zero) f |= GfxBoneFlags.IsIdentity;
                b.Flags = f;
            }

            var used = new HashSet<string>(all.Select(v => v.MiiBone));
            foreach (GfxBone b in miiBones)
            {
                if (used.Contains(b.Name)) b.Flags |= GfxBoneFlags.IsNeededRendering | GfxBoneFlags.HasSkinningMtx;
            }

            // ---- 7. Re-encode Pokémon shapes: canonical float layout, one Mii bone per vertex.
            for (int si = 0; si < pm.Shapes.Count; si++)
            {
                EncodeShape(pm.Shapes[si], shapeVerts[si], miiBones, opt.Look == 5 && !opt.TemplateMaterial);
            }

            // ---- 8. Move geometry, materials and textures into the Tomodachi model.
            string meshNode = tm.Meshes.Count > 0 ? tm.Meshes[0].MeshNodeName : "ankleModel";
            int mainMat = MainMaterial(pm);
            var rename = new Dictionary<string, string>();
            for (int i = 0; i < pm.Materials.Count; i++)
            {
                string n = i == mainMat ? "mtBdDef" : "mtPk" + i;
                rename[pm.Materials[i].Name] = n;
            }

            bool miiMat = opt.Look == 5 && !opt.TemplateMaterial;
            if (miiMat)
            {
                string mt = opt.MaterialTemplate ?? templatePath;
                var clones = pm.Materials.Select(pmat => CloneMiiMaterial(mt, pmat, rename[pmat.Name])).ToList();
                pm.Materials.Clear();
                foreach (var c in clones) pm.Materials.Add(c);
            }

            foreach (var mat in pm.Materials)
            {
                if (miiMat) continue;
                mat.Name = rename[mat.Name];
                ApplyLook(mat, opt.Look);
                var luts = mat.FragmentShader.LUTs;
                // Same assignment as Tomodachi's own mtBdDef (SPICA's field names are swapped vs. meaning).
                if (luts.Dist0 != null) { luts.Dist0.Sampler.TableName = "defSpc0"; luts.Dist0.Sampler.SamplerName = "lutCommon"; }
                if (luts.Dist1 != null) { luts.Dist1.Sampler.TableName = "defSpc1"; luts.Dist1.Sampler.SamplerName = "lutCommon"; }
                foreach (GfxFragLightLUT x in new[] { luts.ReflecR, luts.ReflecG, luts.ReflecB, luts.Fresnel })
                {
                    if (x != null) { x.Sampler.TableName = "defSpc0"; x.Sampler.SamplerName = "lutCommon"; }
                }
            }

            tm.Shapes.Clear();
            foreach (GfxShape sh in pm.Shapes) tm.Shapes.Add(sh);
            tm.Meshes.Clear();
            foreach (GfxMesh m in pm.Meshes)
            {
                m.Parent = tm;
                m.MeshNodeName = meshNode;
                // Tomodachi outfits have no MeshNodeVisibilities table; the mesh must not index into one.
                m.MeshNodeIndex = tm.MeshNodeVisibilities.Count > 0 ? (short)0 : (short)-1;
                tm.Meshes.Add(m);
            }
            if (opt.TemplateMaterial)
            {
                foreach (GfxMesh m in tm.Meshes) m.MaterialIndex = 0;
            }
            else
            {
                tm.Materials.Clear();
                foreach (var mat in pm.Materials) tm.Materials.Add(mat);
            }

            // Material + visibility anim groups come from the Pokémon (names fixed), skeletal from the template.
            // With cloned Mii materials the template's own groups already describe mtBdDef correctly.
            foreach (var g in opt.TemplateMaterial || miiMat ? new List<SPICA.Formats.CtrGfx.AnimGroup.GfxAnimGroup>() : pm.AnimationsGroup.ToList())
            {
                if (g.Name == "SkeletalAnimation") continue;
                foreach (var e in g.Elements.ToList())
                {
                    foreach (var kv in rename) e.Name = e.Name.Replace("[\"" + kv.Key + "\"]", "[\"" + kv.Value + "\"]");
                    if (e.Name.StartsWith("MeshNodeVisibilities") && tm.MeshNodeVisibilities.Count == 0) g.Elements.Remove(e);
                }
                if (tm.AnimationsGroup.Contains(g.Name)) tm.AnimationsGroup.Remove(tm.AnimationsGroup[g.Name]);
                tm.AnimationsGroup.Add(g);
            }

            if (!opt.TemplateMaterial)
            {
                tFile.Textures.Clear();
                foreach (GfxTexture tex in pFile.Textures) { TranscodeEtc1(tex); tFile.Textures.Add(tex); }
                if (miiMat) AddHelperTextures(tFile, opt.MaterialTemplate ?? templatePath);
            }

            Gfx.Save(outPath, tFile);

            Console.WriteLine($"{Path.GetFileName(pokePath)} -> {Path.GetFileName(outPath)}: scale={s:0.###} verts={all.Count} " +
                $"bones=[{string.Join(",", used)}] mats=[{string.Join(",", rename.Values)}]");
        }

        static string MapBone(string rumble, bool leftSide)
        {
            switch (rumble)
            {
                case "HEAD": case "EAR": case "NECK": return "neck";
                case "TAIL": case "TAILEND": return "hips";
                case "ARM": return leftSide ? "L_shoulder" : "R_shoulder";
                case "LEFT_WING": return "L_shoulder";
                case "RIGHT_WING": return "R_shoulder";
                case "LEG": return leftSide ? "L_leg" : "R_leg";
                default: return "waist";
            }
        }

        static int MainMaterial(GfxModel pm)
        {
            // The material drawn by the mesh with the most vertices.
            int best = 0, bestCount = -1;
            foreach (GfxMesh m in pm.Meshes)
            {
                GfxShape sh = pm.Shapes[m.ShapeIndex];
                int n = sh.SubMeshes.Sum(x => x.Faces.Sum(f => f.FaceDescriptors.Sum(d => d.Indices.Length)));
                if (n > bestCount) { bestCount = n; best = m.MaterialIndex; }
            }
            return best;
        }

        static Vtx[] DecodeShape(GfxShape shape, List<GfxBone> bones, Matrix4x4[] world)
        {
            var il = shape.VertexBuffers.OfType<GfxVertexBufferInterleaved>().FirstOrDefault();
            if (il == null) throw new InvalidDataException("shape without interleaved buffer");
            int count = il.RawBuffer.Length / il.VertexStride;
            var verts = new Vtx[count];
            for (int i = 0; i < count; i++) verts[i] = new Vtx();

            var fixedIdx = shape.VertexBuffers.OfType<GfxVertexBufferFixed>().FirstOrDefault(f => f.AttrName == PICAAttributeName.BoneIndex);
            var fixedNrm = shape.VertexBuffers.OfType<GfxVertexBufferFixed>().FirstOrDefault(f => f.AttrName == PICAAttributeName.Normal);
            var fixedCol = shape.VertexBuffers.OfType<GfxVertexBufferFixed>().FirstOrDefault(f => f.AttrName == PICAAttributeName.Color);
            var boneIdx = new float[count][];
            var boneW = new float[count][];

            foreach (GfxAttribute a in il.Attributes)
            {
                for (int i = 0; i < count; i++)
                {
                    float[] x = ReadAttr(il.RawBuffer, i * il.VertexStride + a.Offset, a);
                    switch (a.AttrName)
                    {
                        case PICAAttributeName.Position: verts[i].Pos = new Vector3(x[0], x[1], x[2]); break;
                        case PICAAttributeName.Normal: verts[i].Nrm = new Vector3(x[0], x[1], x[2]); break;
                        case PICAAttributeName.TexCoord0: verts[i].Uv0 = new Vector2(x[0], x[1]); break;
                        case PICAAttributeName.Color: verts[i].Col = new Vector4(x[0], x[1], x[2], x.Length > 3 ? x[3] : 1); break;
                        case PICAAttributeName.BoneIndex: boneIdx[i] = x; break;
                        case PICAAttributeName.BoneWeight: boneW[i] = x; break;
                    }
                }
            }
            if (fixedNrm != null) foreach (var v in verts) v.Nrm = new Vector3(fixedNrm.Vector[0], fixedNrm.Vector[1], fixedNrm.Vector[2]);
            if (fixedCol != null) foreach (var v in verts) v.Col = new Vector4(fixedCol.Vector[0], fixedCol.Vector[1], fixedCol.Vector[2], fixedCol.Vector.Length > 3 ? fixedCol.Vector[3] : 1);

            // Which Rumble bone owns each vertex: walk the faces of every submesh with its palette.
            var owner = new int[count];
            for (int i = 0; i < count; i++) owner[i] = -1;
            var skinning = new GfxSubMeshSkinning[count];
            foreach (GfxSubMesh sm in shape.SubMeshes)
            {
                foreach (GfxFace face in sm.Faces)
                {
                    foreach (GfxFaceDescriptor d in face.FaceDescriptors)
                    {
                        foreach (ushort vi in d.Indices)
                        {
                            if (owner[vi] >= 0) continue;
                            int slot = 0;
                            if (boneIdx[vi] != null)
                            {
                                float[] w = boneW[vi];
                                slot = (int)boneIdx[vi][0];
                                if (w != null && boneIdx[vi].Length > 1 && w.Length > 1 && w[1] > w[0]) slot = (int)boneIdx[vi][1];
                            }
                            else if (fixedIdx != null) slot = (int)fixedIdx.Vector[0];
                            owner[vi] = sm.BoneIndices.Count > 0 ? sm.BoneIndices[Math.Min(slot, sm.BoneIndices.Count - 1)] : 0;
                            skinning[vi] = sm.Skinning;
                        }
                    }
                }
            }

            for (int i = 0; i < count; i++)
            {
                int b = Math.Max(0, owner[i]);
                verts[i].RumbleBone = bones[b].Name;
                if (skinning[i] != GfxSubMeshSkinning.Smooth)
                {
                    // Rigid / none: positions are in bone space.
                    verts[i].Pos = Vector3.Transform(verts[i].Pos, world[b]);
                    verts[i].Nrm = Vector3.Normalize(Vector3.TransformNormal(verts[i].Nrm, world[b]));
                }
            }
            return verts;
        }

        static void EncodeShape(GfxShape shape, Vtx[] verts, List<GfxBone> miiBones, bool tangent)
        {
            var il = shape.VertexBuffers.OfType<GfxVertexBufferInterleaved>().First();
            bool hasUv = il.Attributes.Any(a => a.AttrName == PICAAttributeName.TexCoord0);
            bool hasCol = il.Attributes.Any(a => a.AttrName == PICAAttributeName.Color) ||
                          shape.VertexBuffers.OfType<GfxVertexBufferFixed>().Any(f => f.AttrName == PICAAttributeName.Color);

            // One palette for the whole shape (a handful of Mii bones at most).
            var palette = verts.Select(v => v.MiiBone).Distinct().ToList();
            var paletteIdx = palette.Select(n => miiBones.FindIndex(b => b.Name == n)).ToList();

            var attrs = new List<(PICAAttributeName name, GfxGLDataType fmt, int el, float scale)>
            {
                (PICAAttributeName.Position, GfxGLDataType.GL_FLOAT, 3, 1f),
                (PICAAttributeName.Normal, GfxGLDataType.GL_FLOAT, 3, 1f),
            };
            if (hasCol) attrs.Add((PICAAttributeName.Color, GfxGLDataType.GL_UNSIGNED_BYTE, 4, 1f / 255));
            if (hasUv) attrs.Add((PICAAttributeName.TexCoord0, GfxGLDataType.GL_FLOAT, 2, 1f));
            if (tangent) attrs.Add((PICAAttributeName.Tangent, GfxGLDataType.GL_FLOAT, 3, 1f));
            attrs.Add((PICAAttributeName.BoneIndex, GfxGLDataType.GL_UNSIGNED_BYTE, 2, 1f));
            attrs.Add((PICAAttributeName.BoneWeight, GfxGLDataType.GL_UNSIGNED_BYTE, 2, 0.01f));

            GfxAttribute template = il.Attributes[0];
            var newAttrs = new List<GfxAttribute>();
            int offset = 0;
            foreach (var a in attrs)
            {
                var ga = new GfxAttribute
                {
                    AttrName = a.name,
                    Type = template.Type,
                    Format = a.fmt,
                    Elements = a.el,
                    Scale = a.scale,
                    Offset = offset,
                };
                newAttrs.Add(ga);
                offset += a.el * (a.fmt == GfxGLDataType.GL_FLOAT ? 4 : a.fmt == GfxGLDataType.GL_SHORT ? 2 : 1);
            }
            int stride = (offset + 3) & ~3;

            var ms = new MemoryStream();
            var w = new BinaryWriter(ms);
            foreach (Vtx v in verts)
            {
                long start = ms.Position;
                w.Write(v.Pos.X); w.Write(v.Pos.Y); w.Write(v.Pos.Z);
                Vector3 n = v.Nrm.LengthSquared() > 0 ? Vector3.Normalize(v.Nrm) : Vector3.UnitY;
                w.Write(n.X); w.Write(n.Y); w.Write(n.Z);
                if (hasCol)
                {
                    w.Write(ToByte(v.Col.X)); w.Write(ToByte(v.Col.Y)); w.Write(ToByte(v.Col.Z)); w.Write(ToByte(v.Col.W));
                }
                if (hasUv) { w.Write(v.Uv0.X); w.Write(v.Uv0.Y); }
                if (tangent)
                {
                    // Any unit vector perpendicular to the normal: with a flat normal map the bump stage
                    // returns the vertex normal whatever the tangent is, it only has to be valid.
                    Vector3 t = Vector3.Cross(n, Math.Abs(n.Y) < 0.9f ? Vector3.UnitY : Vector3.UnitX);
                    t = Vector3.Normalize(t);
                    w.Write(t.X); w.Write(t.Y); w.Write(t.Z);
                }
                w.Write((byte)palette.IndexOf(v.MiiBone)); w.Write((byte)0);
                w.Write((byte)100); w.Write((byte)0);
                while (ms.Position - start < stride) w.Write((byte)0);
            }

            il.RawBuffer = ms.ToArray();
            il.VertexStride = stride;
            il.Attributes.Clear();
            il.Attributes.AddRange(newAttrs);
            shape.VertexBuffers.RemoveAll(b => b is GfxVertexBufferFixed f &&
                (f.AttrName == PICAAttributeName.BoneIndex || f.AttrName == PICAAttributeName.BoneWeight ||
                 f.AttrName == PICAAttributeName.Normal || f.AttrName == PICAAttributeName.Color));

            foreach (GfxSubMesh sm in shape.SubMeshes)
            {
                sm.Skinning = GfxSubMeshSkinning.Smooth;
                sm.BoneIndices.Clear();
                sm.BoneIndices.AddRange(paletteIdx);
            }

            shape.PositionOffset = Vector3.Zero;
            Vector3 min = new Vector3(verts.Min(v => v.Pos.X), verts.Min(v => v.Pos.Y), verts.Min(v => v.Pos.Z));
            Vector3 max = new Vector3(verts.Max(v => v.Pos.X), verts.Max(v => v.Pos.Y), verts.Max(v => v.Pos.Z));
            shape.BoundingBox.Center = (min + max) * 0.5f;
            shape.BoundingBox.Size = max - min;
            shape.BoundingBox.Orientation = new Matrix3x3(1, 0, 0, 0, 1, 0, 0, 0, 1);
        }

        static byte ToByte(float f) => (byte)Math.Max(0, Math.Min(255, (int)Math.Round(f * 255)));

        static float[] ReadAttr(byte[] buf, int off, GfxAttribute a)
        {
            var r = new float[a.Elements];
            for (int j = 0; j < a.Elements; j++)
            {
                float v;
                switch (a.Format)
                {
                    case GfxGLDataType.GL_BYTE: v = (sbyte)buf[off + j]; break;
                    case GfxGLDataType.GL_UNSIGNED_BYTE: v = buf[off + j]; break;
                    case GfxGLDataType.GL_SHORT: v = BitConverter.ToInt16(buf, off + j * 2); break;
                    default: v = BitConverter.ToSingle(buf, off + j * 4); break;
                }
                r[j] = v * a.Scale;
            }
            return r;
        }

        static float ValueAt0(GfxFloatKeyFrameGroup g, float fallback)
        {
            if (g == null || g.KeyFrames.Count == 0) return fallback;
            return g.KeyFrames.OrderBy(k => k.Frame).First().Value;
        }

        public static Matrix4x4 Local(Vector3 s, Vector3 r, Vector3 t)
        {
            return Matrix4x4.CreateScale(s) *
                   Matrix4x4.CreateRotationX(r.X) *
                   Matrix4x4.CreateRotationY(r.Y) *
                   Matrix4x4.CreateRotationZ(r.Z) *
                   Matrix4x4.CreateTranslation(t);
        }

        static Matrix4x4 WorldOf(List<GfxBone> bones, int i)
        {
            Matrix4x4 m = Local(bones[i].Scale, bones[i].Rotation, bones[i].Translation);
            int p = bones[i].ParentIndex;
            return p < 0 ? m : m * WorldOf(bones, p);
        }

        static Vector3 Center(IEnumerable<Vtx> vs)
        {
            var l = vs.ToList();
            Vector3 min = new Vector3(l.Min(v => v.Pos.X), l.Min(v => v.Pos.Y), l.Min(v => v.Pos.Z));
            Vector3 max = new Vector3(l.Max(v => v.Pos.X), l.Max(v => v.Pos.Y), l.Max(v => v.Pos.Z));
            return (min + max) * 0.5f;
        }

        static Vector3 Or(Vector3 a, Vector3 b) => float.IsNaN(a.X) ? b : a;
    }
}
