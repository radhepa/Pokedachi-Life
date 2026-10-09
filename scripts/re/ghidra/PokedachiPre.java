// Pre-analysis options for Tomodachi Life code.bin (raw ARMv6K at 0x100000).
import ghidra.app.script.GhidraScript;

public class PokedachiPre extends GhidraScript {
    @Override
    public void run() throws Exception {
        setAnalysisOption(currentProgram, "ARM Aggressive Instruction Finder", "true");
        setAnalysisOption(currentProgram, "Decompiler Parameter ID", "false");
        disassemble(toAddr(0x100000));
        createFunction(toAddr(0x100000), "entry");
    }
}
