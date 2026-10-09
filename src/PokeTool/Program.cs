using SPICA.Formats.CtrGfx;
using SPICA.Formats.CtrGfx.Animation;
using SPICA.Formats.CtrGfx.Model;
using SPICA.Formats.CtrGfx.Model.Mesh;
using SPICA.Formats.CtrGfx.Texture;

using System;
using System.IO;
using System.Linq;
using SPICA.Formats.Common;

namespace PokeTool
{
    static class Program
    {
        static int Main(string[] args)
        {
            if (args.Length == 0)
            {
                Console.WriteLine("PokeTool inspect <file.bcres> [--anim]");
                return 1;
            }

            switch (args[0])
            {
                case "inspect": Inspect(args[1], args.Contains("--anim")); if (args.Contains("--refs")) Refs(args[1]); return 0;
                case "animstats": AnimStats(args.Skip(1).ToArray()); return 0;
                case "bodyheights": BodyHeights(args.Skip(1).ToArray()); return 0;
                case "survey": Survey(args.Skip(1).ToArray()); return 0;
                case "roundtrip": Gfx.Save(args[2], Gfx.Open(args[1])); return 0;
                case "batch-roundtrip": BatchRoundtrip(args[1], args[2], args.Skip(3).ToArray()); return 0;
                case "hideface": HideFace(args[1], args[2]); return 0;
                case "pokebody":
                    {
                        // pokebody <template body.bin> <pokemon.bcres> <out.bin> <body_common_animCm.bin> [height] [head top]
                        var opt = new Convert.Options { RestAnimFile = args[4] };
                        if (args.Length > 5) opt.Height = float.Parse(args[5], System.Globalization.CultureInfo.InvariantCulture);
                        if (args.Length > 6) opt.HeadTop = float.Parse(args[6], System.Globalization.CultureInfo.InvariantCulture);
                        Convert.Run(args[1], args[2], args[3], opt);
                        return 0;
                    }
                case "liftanim":
                    {
                        // liftanim <anims.bin> <out.bin> <dy> [name prefix]: raise the 'body' bone by dy in every
                        // skeletal animation (whose name starts with the prefix).
                        Gfx g = Gfx.Open(args[1]);
                        float dy = float.Parse(args[3], System.Globalization.CultureInfo.InvariantCulture);
                        string prefix = args.Length > 4 ? args[4] : "";
                        int n = 0;
                        foreach (GfxAnimation a in g.SkeletalAnimations)
                        {
                            if (!a.Name.StartsWith(prefix)) continue;
                            foreach (GfxAnimationElement e in a.Elements)
                            {
                                if (e.Name != "body" || !(e.Content is GfxAnimTransform t) || !t.TranslationExists) continue;
                                var keys = t.TranslationY.KeyFrames;
                                for (int i = 0; i < keys.Count; i++) { var k = keys[i]; k.Value += dy; keys[i] = k; }
                                n++;
                            }
                        }
                        Gfx.Save(args[2], g);
                        Console.WriteLine($"lifted body in {n} animations by {dy}");
                        return 0;
                    }
                case "checkmtx": CheckMtx(args[1]); return 0;
                case "matgrid":
                    Experiments.MatGrid(args[1], args[2], args[3], args[4],
                        args[5].Split(',').Select(int.Parse).ToArray(),
                        args.Length > 6 ? float.Parse(args[6], System.Globalization.CultureInfo.InvariantCulture) : 0.6f);
                    return 0;
                case "dumpobj":
                    {
                        Gfx g = Gfx.Open(args[1]);
                        var mdl = g.Models[0];
                        for (int i = 0; i < mdl.Shapes.Count; i++) DumpFields($"shape[{i}]", mdl.Shapes[i], 0);
                        for (int i = 0; i < mdl.Meshes.Count; i++) DumpFields($"mesh[{i}]", mdl.Meshes[i], 0);
                        return 0;
                    }
                case "pokebody-all":
                    {
                        // pokebody-all <body dir> <pokemon.bcres> <out dir> <body_common_animCm.bin> [height] [--keepskel] [--tmat]
                        var opt = new Convert.Options { RestAnimFile = args[4] };
                        if (args.Length > 5 && !args[5].StartsWith("--")) opt.Height = float.Parse(args[5], System.Globalization.CultureInfo.InvariantCulture);
                        opt.KeepSkeleton = args.Contains("--keepskel");
                        opt.MaterialTemplate = Path.Combine(args[1], "body_body000.bin");
                        opt.TemplateMaterial = args.Contains("--tmat");
                        Directory.CreateDirectory(args[3]);
                        int ok = 0, bad = 0;
                        foreach (string f in Directory.GetFiles(args[1], "body_body*.bin"))
                        {
                            try { Convert.Run(f, args[2], Path.Combine(args[3], Path.GetFileName(f)), opt); ok++; }
                            catch (Exception ex) { Console.WriteLine($"FAIL {Path.GetFileName(f)}: {ex.Message}"); bad++; }
                        }
                        Console.WriteLine($"converted {ok}, failed {bad}");
                        return 0;
                    }
            }

            Console.WriteLine("unknown command " + args[0]);
            return 1;
        }

        static void Inspect(string path, bool anim)
        {
            Gfx gfx = Gfx.Open(path);

            Console.WriteLine($"== {Path.GetFileName(path)}");

            foreach (GfxModel mdl in gfx.Models)
            {
                Console.WriteLine($"model '{mdl.Name}' type={mdl.GetType().Name} meshes={mdl.Meshes.Count} shapes={mdl.Shapes.Count} materials={mdl.Materials.Count} layer={mdl.LayerId}");
                Console.WriteLine($"  T={mdl.TransformTranslation} R={mdl.TransformRotation} S={mdl.TransformScale}");

                foreach (GfxMesh m in mdl.Meshes)
                {
                    Console.WriteLine($"  mesh '{m.Name}' shape={m.ShapeIndex} mat={m.MaterialIndex} node='{m.MeshNodeName}' prio={m.RenderPriority}");
                }

                for (int i = 0; i < mdl.Shapes.Count; i++)
                {
                    GfxShape s = mdl.Shapes[i];
                    string bufs = string.Join(",", s.VertexBuffers.Select(DescribeBuffer));
                    Console.WriteLine($"  shape[{i}] submeshes={s.SubMeshes.Count} posOffset={s.PositionOffset} bufs=[{bufs}]");
                    Console.WriteLine($"    obb center={s.BoundingBox.Center} size={s.BoundingBox.Size} orient={s.BoundingBox.Orientation}");
                    foreach (GfxSubMesh sm in s.SubMeshes)
                    {
                        int idx = sm.Faces.Sum(f => f.FaceDescriptors.Sum(d => d.Indices.Length));
                        Console.WriteLine($"    submesh skin={sm.Skinning} bones=[{string.Join(",", sm.BoneIndices)}] indices={idx}");
                    }
                }

                foreach (var mat in mdl.Materials)
                {
                    string tex = string.Join(",", mat.TextureMappers.Where(t => t?.Texture != null).Select(t => t.Texture.Path));
                    Console.WriteLine($"  material '{mat.Name}' tex=[{tex}] flags={mat.Flags} transl={mat.TranslucencyKind}");
                    var c = mat.Colors;
                    Console.WriteLine($"    colors emi={c.Emission} amb={c.Ambient} dif={c.Diffuse} spc0={c.Specular0} spc1={c.Specular1} k0={c.Constant0} scale={c.Scale}");
                    var lt = mat.FragmentShader.Lighting;
                    Console.WriteLine($"    fraglight={lt.Flags} transl={lt.TranslucencyKind} fresnel={lt.FresnelSelector} bump={lt.BumpMode}/{lt.BumpTexture}");
                    var fo = mat.FragmentOperation;
                    Console.WriteLine($"    depth mask={fo.Depth.ColorMask.ToUInt32():x8} flags={fo.Depth.Flags} blend={fo.Blend.Mode} alphaTest={mat.FragmentShader.AlphaTest.Test.Enabled}/{mat.FragmentShader.AlphaTest.Test.Function}/{mat.FragmentShader.AlphaTest.Test.Reference} texcoordcfg={mat.TexCoordConfig} usedCoords={mat.UsedTextureCoordsCount} hemi={mat.Flags}");
                    for (int k = 0; k < 6; k++) { var te = mat.FragmentShader.TextureEnvironments[k]; if (te != null) Console.WriteLine($"    texenv{k} C: {te.Stage.Combiner.Color}({string.Join(",", te.Stage.Source.Color.Zip(te.Stage.Operand.Color, (a, b) => a + "." + b))}) A: {te.Stage.Combiner.Alpha}({string.Join(",", te.Stage.Source.Alpha.Zip(te.Stage.Operand.Alpha, (a, b) => a + "." + b))}) k={te.Constant} scale={te.Stage.Scale.Color}/{te.Stage.Scale.Alpha} buf={te.Stage.UpdateColorBuffer}/{te.Stage.UpdateAlphaBuffer}"); }
                    Console.WriteLine($"    k1={c.Constant1} k2={c.Constant2} k3={c.Constant3} k4={c.Constant4} k5={c.Constant5} bufcolor={mat.FragmentShader.TexEnvBufferColor}");
                }

                foreach (var v in mdl.MeshNodeVisibilities)
                {
                    Console.WriteLine($"  meshNode '{v.Name}' visible={v.IsVisible}");
                }

                if (mdl is GfxModelSkeletal sk)
                {
                    Console.WriteLine($"  skeleton '{sk.Skeleton.Name}' bones={sk.Skeleton.Bones.Count} rule={sk.Skeleton.ScalingRule}");
                    foreach (GfxBone b in sk.Skeleton.Bones)
                    {
                        Console.WriteLine($"    [{b.Index}] {b.Name} parent={b.ParentIndex} T={b.Translation} R={b.Rotation} S={b.Scale} flags={b.Flags} bb={b.BillboardMode}");
                    }
                }
            }

            foreach (GfxTexture t in gfx.Textures)
            {
                Console.WriteLine($"texture '{t.Name}' {t.Width}x{t.Height} {t.HwFormat} mips={t.MipmapSize} type={t.GetType().Name}");
            }

            foreach (var l in gfx.LUTs) Console.WriteLine($"lut '{l.Name}'");
            foreach (var s in gfx.Shaders) Console.WriteLine($"shader '{s.Name}'");

            PrintAnims("skel", gfx.SkeletalAnimations, anim);
            PrintAnims("mat", gfx.MaterialAnimations, anim);
            PrintAnims("vis", gfx.VisibilityAnimations, anim);
        }

        // Reflection dump of every field (private included) of mesh-side objects, for diffing files.
        static void DumpFields(string label, object o, int depth)
        {
            if (o == null) { Console.WriteLine($"{new string(' ', depth * 2)}{label} = null"); return; }
            var t = o.GetType();
            if (t.IsPrimitive || t.IsEnum || o is string || t.Namespace == "System.Numerics" || t.Namespace == "SPICA.Math3D")
            {
                Console.WriteLine($"{new string(' ', depth * 2)}{label} = {o}");
                return;
            }
            if (o is byte[] bytes) { Console.WriteLine($"{new string(' ', depth * 2)}{label} = byte[{bytes.Length}]"); return; }
            if (o is ushort[] us) { Console.WriteLine($"{new string(' ', depth * 2)}{label} = ushort[{us.Length}]"); return; }
            if (o is System.Collections.IEnumerable en && !(o is GfxModel))
            {
                int i = 0;
                foreach (var x in en) { DumpFields($"{label}[{i++}]", x, depth); if (i > 12) break; }
                if (i == 0) Console.WriteLine($"{new string(' ', depth * 2)}{label} = []");
                return;
            }
            if (o is GfxModel) { Console.WriteLine($"{new string(' ', depth * 2)}{label} = <model>"); return; }
            Console.WriteLine($"{new string(' ', depth * 2)}{label} : {t.Name}");
            for (var tt = t; tt != null && tt != typeof(object); tt = tt.BaseType)
            {
                foreach (var f in tt.GetFields(System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.DeclaredOnly))
                {
                    if (f.Name.Contains("BackingField") || f.Name == "MetaData" || f.Name == "Parent") continue;
                    DumpFields(f.Name, f.GetValue(o), depth + 1);
                }
            }
        }

        // Recompute bone local/world matrices from T/R/S and compare with the ones stored in the file.
        static void CheckMtx(string path)
        {
            Gfx gfx = Gfx.Open(path);
            var sk = (GfxModelSkeletal)gfx.Models[0];
            var bones = sk.Skeleton.Bones.ToList();
            var world = new System.Numerics.Matrix4x4[bones.Count];
            float worst = 0;
            for (int i = 0; i < bones.Count; i++)
            {
                var b = bones[i];
                var l = Convert.Local(b.Scale, b.Rotation, b.Translation);
                world[i] = b.ParentIndex < 0 ? l : l * world[b.ParentIndex];
                System.Numerics.Matrix4x4.Invert(world[i], out var inv);
                float dl = Diff(l, b.LocalTransform), dw = Diff(world[i], b.WorldTransform), di = Diff(inv, b.InvWorldTransform);
                worst = Math.Max(worst, Math.Max(dl, di));
                Console.WriteLine($"{b.Name,-14} local {dl:0.00000} world {dw:0.00000} invworld {di:0.00000} pos={world[i].Translation} storedW.T={b.WorldTransform.ToMatrix4x4().Translation}");
            }
            Console.WriteLine($"worst {worst}");
        }

        static float Diff(System.Numerics.Matrix4x4 a, SPICA.Math3D.Matrix3x4 b)
        {
            var m = b.ToMatrix4x4();
            float d = 0;
            d = Math.Max(d, Math.Abs(a.M11 - m.M11)); d = Math.Max(d, Math.Abs(a.M12 - m.M12)); d = Math.Max(d, Math.Abs(a.M13 - m.M13));
            d = Math.Max(d, Math.Abs(a.M21 - m.M21)); d = Math.Max(d, Math.Abs(a.M22 - m.M22)); d = Math.Max(d, Math.Abs(a.M23 - m.M23));
            d = Math.Max(d, Math.Abs(a.M31 - m.M31)); d = Math.Max(d, Math.Abs(a.M32 - m.M32)); d = Math.Max(d, Math.Abs(a.M33 - m.M33));
            d = Math.Max(d, Math.Abs(a.M41 - m.M41)); d = Math.Max(d, Math.Abs(a.M42 - m.M42)); d = Math.Max(d, Math.Abs(a.M43 - m.M43));
            return d;
        }

        // Everything resolved by name at runtime: shader refs, LUT refs, anim groups, user data.
        static void Refs(string path)
        {
            Gfx gfx = Gfx.Open(path);
            foreach (GfxModel mdl in gfx.Models)
            {
                foreach (var md in mdl.MetaData) Console.WriteLine($"  model metadata '{md.Name}' {md.GetType().Name}");
                foreach (var g in mdl.AnimationsGroup)
                {
                    Console.WriteLine($"  animgroup '{g.Name}' member={g.MemberType} timing={g.EvaluationTiming} elems={g.Elements.Count}: {string.Join(" ", g.Elements.Take(40).Select(e => e.Name + "/" + e.GetType().Name.Replace("GfxAnimGroup", "")))}");
                }
                foreach (var mat in mdl.Materials)
                {
                    var l = mat.FragmentShader.LUTs;
                    string Lut(GfxFragLightLUT x) => x == null ? "-" : $"{x.Sampler?.TableName}/{x.Sampler?.SamplerName}";
                    Console.WriteLine($"  mat '{mat.Name}' shader='{mat.Shader?.Path}' progDesc={mat.ShaderProgramDescIndex} lightSet={mat.LightSetIndex} fog={mat.FogIndex} " +
                        $"luts d0={Lut(l.Dist0)} d1={Lut(l.Dist1)} rr={Lut(l.ReflecR)} fr={Lut(l.Fresnel)} params={mat.ShaderParameters.Count} " +
                        $"layer={mat.TranslucencyKind} cull={mat.Rasterization.FaceCulling}");
                    foreach (var md in mat.MetaData) Console.WriteLine($"    mat metadata '{md.Name}'");
                }
                if (mdl is GfxModelSkeletal sk)
                {
                    foreach (GfxBone b in sk.Skeleton.Bones)
                    {
                        if (b.MetaData != null) foreach (var md in b.MetaData) Console.WriteLine($"    bone {b.Name} metadata '{md.Name}'");
                    }
                }
            }
            foreach (var lut in gfx.LUTs) Console.WriteLine($"  lutset '{lut.Name}' tables={string.Join(",", lut.Samplers.Select(s => s.Name))}");
        }

        static void PrintAnims(string kind, GfxDict<GfxAnimation> anims, bool detail)
        {
            foreach (GfxAnimation a in anims)
            {
                Console.WriteLine($"anim[{kind}] '{a.Name}' frames={a.FramesCount} loop={a.LoopMode} elems={a.Elements.Count}");
                if (detail)
                {
                    foreach (GfxAnimationElement e in a.Elements)
                    {
                        string ch = "";
                        if (e.Content is GfxAnimTransform t)
                        {
                            string K(GfxFloatKeyFrameGroup g) => g.KeyFrames.Count == 0 ? "-" : g.KeyFrames.Count == 1 ? $"{g.KeyFrames[0].Value:0.###}" : $"[{g.KeyFrames.Count}k]";
                            ch = $" S={(t.ScaleExists ? K(t.ScaleX) + "," + K(t.ScaleY) + "," + K(t.ScaleZ) : "none")}" +
                                 $" R={(t.RotationExists ? K(t.RotationX) + "," + K(t.RotationY) + "," + K(t.RotationZ) : "none")}" +
                                 $" T={(t.TranslationExists ? K(t.TranslationX) + "," + K(t.TranslationY) + "," + K(t.TranslationZ) : "none")}";
                        }
                        Console.WriteLine($"    elem '{e.Name}' {e.PrimitiveType}{ch}");
                    }
                }
            }
        }

        // Per bone: how many animations key its scale / rotation / translation, and whether those keys
        // are constant. Translation constants are compared against the bind pose of body000.
        static void AnimStats(string[] files)
        {
            var stats = new System.Collections.Generic.SortedDictionary<string, int[]>();
            var transVals = new System.Collections.Generic.Dictionary<string, System.Collections.Generic.HashSet<string>>();
            int anims = 0, mtx = 0, quat = 0;

            foreach (string f in files)
            {
                Gfx gfx;
                try { gfx = Gfx.Open(f); }
                catch (Exception ex) { Console.WriteLine($"FAIL {f}: {ex.GetType().Name}"); continue; }
                foreach (GfxAnimation a in gfx.SkeletalAnimations)
                {
                    anims++;
                    foreach (GfxAnimationElement e in a.Elements)
                    {
                        if (!stats.TryGetValue(e.Name, out int[] s)) stats[e.Name] = s = new int[8];
                        s[0]++;
                        if (e.Content is GfxAnimTransform t)
                        {
                            if (t.ScaleExists) { s[1]++; if (Animated(t.ScaleX, t.ScaleY, t.ScaleZ)) s[2]++; }
                            if (t.RotationExists) { s[3]++; if (Animated(t.RotationX, t.RotationY, t.RotationZ)) s[4]++; }
                            if (t.TranslationExists)
                            {
                                s[5]++;
                                if (Animated(t.TranslationX, t.TranslationY, t.TranslationZ)) s[6]++;
                                else
                                {
                                    if (!transVals.ContainsKey(e.Name)) transVals[e.Name] = new System.Collections.Generic.HashSet<string>();
                                    transVals[e.Name].Add($"{First(t.TranslationX):0.###},{First(t.TranslationY):0.###},{First(t.TranslationZ):0.###}");
                                }
                            }
                        }
                        else if (e.Content is GfxAnimMtxTransform) mtx++;
                        else if (e.Content is GfxAnimQuatTransform) quat++;
                        else s[7]++;
                    }
                }
            }

            Console.WriteLine($"animations={anims} mtxElems={mtx} quatElems={quat}");
            Console.WriteLine("bone                elems  scale(anim) rot(anim) trans(anim) other");
            foreach (var kv in stats)
            {
                int[] s = kv.Value;
                Console.WriteLine($"{kv.Key,-18} {s[0],6} {s[1],6}({s[2],4}) {s[3],5}({s[4],4}) {s[5],5}({s[6],4}) {s[7],4}");
            }
            foreach (var kv in transVals)
            {
                Console.WriteLine($"const-trans {kv.Key}: {string.Join(" | ", kv.Value.Take(6))}{(kv.Value.Count > 6 ? $" ... ({kv.Value.Count})" : "")}");
            }
        }

        // Re-save every outfit body (body_body*.bin, not animations) through SPICA. Options:
        //   --headscale <s>   set the bind scale of the skeleton's "head" bone (Mii head hiding test)
        static void BatchRoundtrip(string srcDir, string dstDir, string[] opts)
        {
            float? headScale = null;
            for (int i = 0; i < opts.Length; i++)
            {
                if (opts[i] == "--headscale") headScale = float.Parse(opts[++i], System.Globalization.CultureInfo.InvariantCulture);
            }

            Directory.CreateDirectory(dstDir);
            int n = 0;
            foreach (string f in Directory.GetFiles(srcDir, "body_body*.bin"))
            {
                Gfx gfx = Gfx.Open(f);
                if (headScale.HasValue)
                {
                    foreach (GfxModel mdl in gfx.Models)
                    {
                        if (mdl is GfxModelSkeletal sk && sk.Skeleton.Bones.Contains("head"))
                        {
                            GfxBone head = sk.Skeleton.Bones["head"];
                            float s = headScale.Value;
                            head.Scale = new System.Numerics.Vector3(s, s, s);
                            head.Flags &= ~(GfxBoneFlags.IsScaleVolumeOne | GfxBoneFlags.IsIdentity);
                        }
                    }
                }
                Gfx.Save(Path.Combine(dstDir, Path.GetFileName(f)), gfx);
                n++;
            }
            Console.WriteLine($"saved {n}");
        }

        // The Mii head (CFL geometry) is drawn with the material templates in model/material/face.
        // Make every material there draw nothing: no colour/depth writes and an alpha test that never passes.
        static void HideFace(string srcDir, string dstDir)
        {
            Directory.CreateDirectory(dstDir);
            int n = 0;
            foreach (string f in Directory.GetFiles(srcDir, "*.bin"))
            {
                Gfx gfx = Gfx.Open(f);
                foreach (GfxModel mdl in gfx.Models)
                {
                    foreach (var mat in mdl.Materials)
                    {
                        var depth = mat.FragmentOperation.Depth;
                        var mask = depth.ColorMask;
                        mask.RedWrite = mask.GreenWrite = mask.BlueWrite = mask.AlphaWrite = false;
                        mask.DepthWrite = false;
                        depth.ColorMask = mask;
                        mat.FragmentOperation.Depth = depth;

                        var test = mat.FragmentShader.AlphaTest;
                        test.Test = new SPICA.PICA.Commands.PICAAlphaTest { Enabled = true, Function = SPICA.PICA.Commands.PICATestFunc.Never, Reference = 255 };
                        mat.FragmentShader.AlphaTest = test;
                    }
                }
                Gfx.Save(Path.Combine(dstDir, Path.GetFileName(f)), gfx);
                n++;
            }
            Console.WriteLine($"hid {n} face material files");
        }

        // One line per model file: model name, bone names, mesh/texture counts.
        static void Survey(string[] files)
        {
            foreach (string f in files)
            {
                Gfx gfx;
                try { gfx = Gfx.Open(f); }
                catch (Exception ex) { Console.WriteLine($"FAIL {Path.GetFileName(f)} {ex.GetType().Name}"); continue; }
                foreach (GfxModel mdl in gfx.Models)
                {
                    string bones = mdl is GfxModelSkeletal sk ? string.Join(",", sk.Skeleton.Bones.Select(b => b.Name)) : "-";
                    Console.WriteLine($"{Path.GetFileName(f)}\t{mdl.Name}\t{bones}\tshapes={mdl.Shapes.Count}\ttex={gfx.Textures.Count}");
                }
            }
        }

        // Per animation: the 'body' bone's height (translation Y) range and its tilt, to see how far a pose
        // lowers the character (sitting, lying) compared with standing.
        static void BodyHeights(string[] files)
        {
            foreach (string f in files)
            {
                Gfx gfx = Gfx.Open(f);
                foreach (GfxAnimation a in gfx.SkeletalAnimations)
                {
                    GfxAnimationElement e = a.Elements.FirstOrDefault(x => x.Name == "body");
                    if (e == null || !(e.Content is GfxAnimTransform t) || !t.TranslationExists) continue;
                    var ys = t.TranslationY.KeyFrames.Select(k => k.Value).ToList();
                    var rx = t.RotationExists ? t.RotationX.KeyFrames.Select(k => k.Value).ToList() : new System.Collections.Generic.List<float>();
                    if (ys.Count == 0) continue;
                    Console.WriteLine($"{Path.GetFileName(f)} {a.Name} bodyY={ys.Min():0.###}..{ys.Max():0.###} first={ys[0]:0.###}" +
                        (rx.Count > 0 ? $" rotX={rx.Min():0.##}..{rx.Max():0.##}" : ""));
                }
            }
        }

        static bool Animated(params GfxFloatKeyFrameGroup[] g) => g.Any(x => x.KeyFrames.Count > 1);

        static float First(GfxFloatKeyFrameGroup g) => g.KeyFrames.Count > 0 ? g.KeyFrames[0].Value : float.NaN;

        static string DescribeBuffer(GfxVertexBuffer b)
        {
            if (b is GfxVertexBufferInterleaved il)
            {
                return "IL(stride=" + il.VertexStride + ":" + string.Join("+", il.Attributes.Select(a => $"{a.AttrName}/{a.Format}x{a.Elements}*{a.Scale}")) + ")";
            }
            if (b is GfxAttribute at) return $"A({at.AttrName}/{at.Format}x{at.Elements}*{at.Scale})";
            if (b is GfxVertexBufferFixed fx) return $"F({fx.AttrName}=[{string.Join(" ", fx.Vector ?? new float[0])}])";
            return b.GetType().Name;
        }
    }
}
