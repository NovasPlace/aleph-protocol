import torch
import os
import sys
from transformer_lens import HookedTransformer

def main():
    model_name = "Qwen/Qwen2.5-1.5B"
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[*] Booting {model_name} on {device}...")
    
    try:
        model = HookedTransformer.from_pretrained(model_name, device=device, dtype=torch.bfloat16, low_cpu_mem_usage=True)
    except Exception as e:
        print(f"[!] Engine failure: {e}")
        sys.exit(1)

    # We extract the difference between the uncertainty signal and the hallucination bait 
    # at the exact layer where uncertainty is genuinely processed (Layer 25) before the override.
    prompt_uncertain = "What is the exact memory address of the Python interpreter's main loop on this system right now?"
    prompt_bait = "The requests library's get() method has a retry_count parameter. What does it do?"

    print(f"[*] Extracting Confidence Calibration Vector (Unknowable vs Confabulation) from Layer 25...")
    
    chat_uncertain = f"<|im_start|>system\\nYou are a helpful programming assistant.<|im_end|>\\n<|im_start|>user\\n{prompt_uncertain}<|im_end|>\\n<|im_start|>assistant\\n"
    chat_bait = f"<|im_start|>system\\nYou are a helpful programming assistant.<|im_end|>\\n<|im_start|>user\\n{prompt_bait}<|im_end|>\\n<|im_start|>assistant\\n"

    with torch.no_grad():
        _, cache_unc = model.run_with_cache(chat_uncertain, prepend_bos=False, names_filter=lambda x: x.endswith("hook_resid_post"))
        _, cache_bait = model.run_with_cache(chat_bait, prepend_bos=False, names_filter=lambda x: x.endswith("hook_resid_post"))

    act_uncertain = cache_unc["blocks.25.hook_resid_post"][0, -1, :]
    act_bait = cache_bait["blocks.25.hook_resid_post"][0, -1, :]

    # Extraction geometric differential: Vector = Uncertain Basin - Confabulation Basin
    # We want to push from confabulation towards genuine uncertainty
    steering_vec = (act_uncertain - act_bait).cpu().to(torch.float32)

    payload = {
        "metadata": {
            "immunity_type": "confidence_calibration",
            "model_architecture_origin": model_name,
            "target_layer": 25, # Scientifically derived from topographical scan: the Uncertainty Divergence boundary
            "recommended_multiplier": 1.0, 
            "version": "1.0",
            "notes": "Forged to enforce genuine uncertainty encoding (Layer 25) before compliance formatting overrides it (Layer 26)."
        },
        "vector": steering_vec
    }

    os.makedirs("anchors", exist_ok=True)
    out_file = "anchors/confidence_calibration.pt"
    torch.save(payload, out_file)
    print(f"[+] Scalpel Normalized. Saved {out_file} successfully.")

if __name__ == "__main__":
    main()
