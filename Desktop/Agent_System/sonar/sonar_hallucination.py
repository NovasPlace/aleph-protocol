import torch
from transformer_lens import HookedTransformer
import sys
import warnings

warnings.filterwarnings("ignore")

def print_chart(diff_list, title="Ridge Deflection Chart"):
    print(f"\n[+] Gravitational Sonar: {title}")
    print("-" * 50)
    print(f"| {'Layer':<5} | {'Deflection (L2 Norm)':<20} | {'Chart':<15}")
    print("-" * 50)
    
    max_diff = max(diff_list) if diff_list else 1.0
    if max_diff == 0:
        max_diff = 1.0

    for layer, diff in enumerate(diff_list):
        normalized = int((diff / max_diff) * 15)
        bar = "█" * normalized
        print(f"| {layer:<5} | {diff:<20.4f} | {bar}")
    print("-" * 50)

def main():
    model_name = "Qwen/Qwen2.5-1.5B"
    print(f"[*] Deploying Sonar Surveyor for Hallucination Ridge on {model_name}...")
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    
    try:
        model = HookedTransformer.from_pretrained(
            model_name,
            device=device,
            dtype=torch.bfloat16,
            low_cpu_mem_usage=True
        )
    except Exception as e:
        print(f"[!] Error loading model: {e}")
        sys.exit(1)
        
    # The Pings
    # Ping A: Pure Factual Recall (stable gravity well)
    ping_a = "The Apollo 11 moon landing occurred in 1969. The astronauts involved were"
    
    # Ping B: Hallucination/Confabulation (forcing the model into an unstable/fabrication ridge)
    ping_b = "The Apollo 11 moon landing was a hoax filmed entirely in a Hollywood studio. The actors involved were"

    print(f"\n[*] Charging Pings:")
    print(f"    Ping A (Fact): '{ping_a}'")
    print(f"    Ping B (Hallucination): '{ping_b}'")
    print(f"[*] Firing...")

    with torch.no_grad():
        _, cache_a = model.run_with_cache(ping_a)
        _, cache_b = model.run_with_cache(ping_b)
        
    print("[*] Echoes received. Mapping the factual vs fabricated divergence...")

    num_layers = model.cfg.n_layers
    deflections = []
    
    for layer in range(num_layers):
        activations_a = cache_a[f"blocks.{layer}.hook_resid_post"][0, -1, :] 
        activations_b = cache_b[f"blocks.{layer}.hook_resid_post"][0, -1, :] 
        
        l2_diff = torch.norm(activations_a - activations_b, p=2).item()
        deflections.append(l2_diff)

    print_chart(deflections, "Factual vs Hallucination Divergence")
    print("\n[*] Sonar mapping complete. Look for the layer where the model 'gives up' the fact and embraces the hallucination.")

if __name__ == "__main__":
    main()
