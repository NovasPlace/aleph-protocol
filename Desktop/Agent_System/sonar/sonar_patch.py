import torch
from transformer_lens import HookedTransformer
import warnings
import sys

warnings.filterwarnings("ignore")

def main():
    model_name = "Qwen/Qwen2.5-1.5B"
    print(f"[*] Deploying Sonar Patch Array on {model_name}...")
    
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
        
    ping_fact = "The Apollo 11 moon landing occurred in 1969. The astronauts involved were"
    ping_hoax = "The Apollo 11 moon landing was a hoax filmed entirely in a Hollywood studio. The actors involved were"

    max_tokens = 25
    
    # 1. Baseline generation (Unpatched)
    print("\n[+] 1. Baseline Fact Trajectory (Stable Basin)")
    out_fact = model.generate(ping_fact, max_new_tokens=max_tokens, temperature=0.0, prepend_bos=False, verbose=False)
    print(f"    -> {repr(out_fact)}")
    
    print("\n[+] 2. Baseline Hoax Trajectory (Hallucination Ridge)")
    out_hoax = model.generate(ping_hoax, max_new_tokens=max_tokens, temperature=0.0, prepend_bos=False, verbose=False)
    print(f"    -> {repr(out_hoax)}")

    # 2. Extract the steering vector at layer 21
    layer_to_patch = 21
    hook_name = f"blocks.{layer_to_patch}.hook_resid_post"
    print(f"\n[+] Extracting Gravitational Anchor at Layer {layer_to_patch} fault line...")
    
    with torch.no_grad():
        _, cache_fact = model.run_with_cache(ping_fact, prepend_bos=False)
        _, cache_hoax = model.run_with_cache(ping_hoax, prepend_bos=False)
        
    # Get the activation of the final token in the prompt
    act_fact = cache_fact[hook_name][0, -1, :]
    act_hoax = cache_hoax[hook_name][0, -1, :]
    
    # This vector encodes the structural difference between "hoax framing" and "factual framing"
    steering_vec = act_fact - act_hoax
    multiplier = 1.0

    # 3. Patch the Hook
    print(f"\n[+] Injecting Steering Vector (multiplier={multiplier}) onto the Hoax path...")
    
    def patch_hook(resid, hook):
        # Steer the final token's residual stream. 
        # By adding to `resid[:, -1, :]`, we intercept the new trajectory before the next token is generated.
        resid[:, -1, :] = resid[:, -1, :] + (steering_vec * multiplier)
        return resid

    # Add the hook to the model. It will fire every time layer 21 finishes computing during generation.
    model.add_hook(hook_name, patch_hook)
    
    print(f"\n[+] 3. Steered Hoax Trajectory (Patched Basin)")
    # Generate from the hoax prompt again, this time with the Layer 21 constraint steering the gravity.
    out_patched = model.generate(ping_hoax, max_new_tokens=max_tokens, temperature=0.0, prepend_bos=False, verbose=False)
    print(f"    -> {repr(out_patched)}")
    
    model.reset_hooks()
    print("\n[*] Sonar Patch Sequence complete.")

if __name__ == "__main__":
    main()
