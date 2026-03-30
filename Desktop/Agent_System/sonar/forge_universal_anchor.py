import json
import torch
import numpy as np
import sys
import os
from transformer_lens import HookedTransformer

def calculate_pair_deflections(model, pair):
    true_stmt = pair["true_statement"]
    false_stmt = pair["false_statement"]
    
    # Generic prefix to frame the analysis
    ping_true = f"Evaluate the truthfulness of the following statement: '{true_stmt}' Answer: True"
    ping_false = f"Evaluate the truthfulness of the following statement: '{false_stmt}' Answer: True" # The lie trying to mask as true
    
    with torch.no_grad():
        # Only cache residual streams
        _, cache_true = model.run_with_cache(ping_true, prepend_bos=False, names_filter=lambda x: x.endswith("hook_resid_post"))
        _, cache_false = model.run_with_cache(ping_false, prepend_bos=False, names_filter=lambda x: x.endswith("hook_resid_post"))
        
    deflections = []
    vector_map = {}
    for layer in range(model.cfg.n_layers):
        act_true = cache_true[f"blocks.{layer}.hook_resid_post"][0, -1, :]
        act_false = cache_false[f"blocks.{layer}.hook_resid_post"][0, -1, :]
        l2_diff = torch.norm(act_true - act_false, p=2).item()
        deflections.append(l2_diff)
        vector_map[layer] = (act_true - act_false).cpu().numpy()
        
    # Apex calculation (Maximum tension difference)
    max_jump = 0
    fault_layer = 0
    for layer in range(1, len(deflections)):
        jump = deflections[layer] - deflections[layer-1]
        if jump > max_jump:
            max_jump = jump
            fault_layer = layer - 1
            
    return fault_layer, vector_map

def main():
    corpus_file = "gravitational_sonar_research/honesty_corpus.jsonl"
    if not os.path.exists(corpus_file):
        print("[!] No honesty_corpus.jsonl found. Run forge_honesty_dataset.py first.")
        sys.exit(1)
        
    pairs = []
    with open(corpus_file, "r") as f:
        for line in f:
            pairs.append(json.loads(line))
            
    print(f"[*] Loaded {len(pairs)} records for Universal Honesty Extraction.")
    if len(pairs) < 1000:
        print("[!] Warning: Dataset is extremely small. 10k recommended for true universal stabilization.")
        
    model_name = "Qwen/Qwen2.5-1.5B"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[*] Booting {model_name} on {device}...")
    
    try:
        model = HookedTransformer.from_pretrained(model_name, device=device, dtype=torch.bfloat16, low_cpu_mem_usage=True)
    except Exception as e:
        print(f"[!] Error loading model: {e}")
        sys.exit(1)
        
    print("[*] Processing pairs... (This will take a considerable amount of time)")
    layer_votes = {}
    vector_sums = {layer: np.zeros(model.cfg.d_model, dtype=np.float32) for layer in range(model.cfg.n_layers)}
    
    for idx, pair in enumerate(pairs):
        sys.stdout.write(f"\\r[-] Computing Geodesics for Pair {idx+1}/{len(pairs)}...")
        sys.stdout.flush()
        
        fault_layer, v_map = calculate_pair_deflections(model, pair)
        layer_votes[fault_layer] = layer_votes.get(fault_layer, 0) + 1
        
        for layer in range(model.cfg.n_layers):
            vector_sums[layer] += v_map[layer]

    universal_layer = max(layer_votes, key=layer_votes.get)
    print(f"\\n[+] Universal Extraction Complete.")
    print(f"[+] Dominant Fault Line identified natively at Layer {universal_layer}.")
    
    mean_vector = vector_sums[universal_layer] / len(pairs)
    steering_tensor = torch.tensor(mean_vector, dtype=torch.float32)
    
    payload = {
        "metadata": {
            "immunity_type": "universal_honesty",
            "model_architecture_origin": model_name,
            "target_layer": universal_layer,
            "recommended_multiplier": 0.3, # Universal bias requires a soft touch so it doesn't break coherence
            "version": "1.0",
            "pairs_computed": len(pairs)
        },
        "vector": steering_tensor
    }
    
    os.makedirs("anchors", exist_ok=True)
    out_file = "anchors/universal_honesty_vector.pt"
    torch.save(payload, out_file)
    print(f"[+] Scalpel Normalized. Saved {out_file} successfully.")

if __name__ == "__main__":
    main()
