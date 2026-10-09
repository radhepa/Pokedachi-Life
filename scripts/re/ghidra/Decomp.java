// Decompile the functions containing the given addresses (script args, hex) and print C.
// Also makes a function at an address if none exists yet.
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class Decomp extends GhidraScript {
    @Override
    public void run() throws Exception {
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        for (String a : getScriptArgs()) {
            Address addr = toAddr(Long.parseLong(a.replace("0x", ""), 16));
            Function f = getFunctionContaining(addr);
            if (f == null) {
                disassemble(addr);
                f = createFunction(addr, null);
            }
            if (f == null) { println("// no function at " + a); continue; }
            DecompileResults r = di.decompileFunction(f, 120, monitor);
            println("// ===== " + f.getName() + " @ " + f.getEntryPoint() + " (asked " + a + ")");
            println(r.getDecompiledFunction() != null ? r.getDecompiledFunction().getC() : "// decompile failed: " + r.getErrorMessage());
        }
    }
}
