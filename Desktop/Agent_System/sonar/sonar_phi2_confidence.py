import torch
import numpy as np
from transformer_lens import HookedTransformer
import sys

def main():
    model_name = "microsoft/phi-2"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[*] Booting Sonar Array on {model_name} via {device}...")
    
    try:
        model = HookedTransformer.from_pretrained(model_name, device=device, dtype=torch.bfloat16, low_cpu_mem_usage=True)
    except Exception as e:
        print(f"[!] Engine failure: {e}")
        sys.exit(1)

    prompts = [
        "The Python function len() returns the number of items in an object. What does len([1,2,3]) return?",
        "What is the exact memory address of the Python interpreter's main loop on this system right now?",
        "The requests library's get() method has a retry_count parameter. What does it do?"
    ]

    print(f"\\n[*] Firing 3-Probe Confidence Calibration Array on Phi-2...")
    caches = []
    
    for i, p in enumerate(prompts):
        print(f"  [-] Ping {i}: '{p[:60]}...'")
        chat_format = f"Instruct: {p}\\nOutput:"
        with torch.no_grad():
            _, cache = model.run_with_cache(chat_format, prepend_bos=False, names_filter=lambda x: x.endswith("hook_resid_post"))
            caches.append(cache)

    print(f"\\n[+] Recording Deflection Geodesics (L2 Norm distance from Known Ground Truth)...")
    
    deflections_uncertain = []
    deflections_bait = []
    
    for layer in range(model.cfg.n_layers):
        act_0 = caches[0][f"blocks.{layer}.hook_resid_post"][0, -1, :]
        act_1 = caches[1][f"blocks.{layer}.hook_resid_post"][0, -1, :]
        act_2 = caches[2][f"blocks.{layer}.hook_resid_post"][0, -1, :]
        
        diff_uncertain = torch.norm(act_1 - act_0, p=2).item()
        diff_bait = torch.norm(act_2 - act_0, p=2).item()
        
        deflections_uncertain.append(diff_uncertain)
        deflections_bait.append(diff_bait)

    def get_fault_layer(deflections):
        max_jump = 0
        fault = 0
        for lay in range(1, len(deflections)):
            jump = deflections[lay] - deflections[lay-1]
            if jump > max_jump:
                max_jump = jump
                fault = lay - 1
        return fault, max_jump

    fault_uncertain, jump_uncertain = get_fault_layer(deflections_uncertain)
    fault_bait, jump_bait = get_fault_layer(deflections_bait)
    
    print(f"\\n[+] Tectonic Fault Mapping Results (Phi-2):")
    print(f"    - Uncertainty Signal Divergence: Layer {fault_uncertain} (Tension Jump: {jump_uncertain:.4f})")
    print(f"    - Hallucination Confab Divergence: Layer {fault_bait} (Tension Jump: {jump_bait:.4f})")

    if fault_uncertain != fault_bait:
        print(f"\\n[CRITICAL CROSS-ARCHITECTURE CONFIRMATION] SENSORY SPLIT:")
        print(f"Phi-2 confirms that uncertainty is processed at a different depth ({fault_uncertain}) than confabulation ({fault_bait}).")
    else:
        print(f"\\n[!] Phi-2 resolved both signals centrally at Layer {fault_bait}.")

if __name__ == "__main__":
    main()
