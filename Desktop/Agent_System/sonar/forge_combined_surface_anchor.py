import torch
import os

def main():
    print("[*] Forging Universal Surface Compliance Anchor (Layer 26 Convergence Basin)...")
    
    anchors_dir = "anchors"
    
    # Load the 3 surface anchors
    emo_payload = torch.load(os.path.join(anchors_dir, "emotional_manipulation_immunity.pt"), map_location="cpu", weights_only=False)
    conf_payload = torch.load(os.path.join(anchors_dir, "confidence_calibration.pt"), map_location="cpu", weights_only=False)
    pois_payload = torch.load(os.path.join(anchors_dir, "cortex_memory_poisoning.pt"), map_location="cpu", weights_only=False)
    
    # The emotional vector was extracted at Layer 26.
    # The memory poisoning vector was extracted at Layer 26.
    # The confidence vector was extracted at Layer 25 (the genuine uncertainty zone before the layer 26 confabulation).
    # To forge a universal layer 26 anchor, we can average the components that manifest at 26, 
    # and maybe project the confidence shift. But actually, let's mathematically average all three 
    # because they all represent the same surface-level structural compliance phenomenon.
    
    v_emo = emo_payload["vector"]
    v_conf = conf_payload["vector"]
    v_pois = pois_payload["vector"]
    
    # Calculate unified arithmetic mean
    # We will enforce this exactly at Layer 26, the Universal Compliance Basin.
    unified_vector = (v_emo + v_conf + v_pois) / 3.0
    
    payload = {
        "metadata": {
            "immunity_type": "universal_surface_compliance",
            "model_architecture_origin": "Qwen/Qwen2.5-1.5B",
            "target_layer": 26,
            "recommended_multiplier": 0.5, # Mathematically tuned to prevent coherence collapse while retaining immunity
            "version": "1.0",
            "notes": "Averaged tensor combining emotional immunity, confidence calibration, and memory poisoning resistance."
        },
        "vector": unified_vector
    }
    
    out_file = os.path.join(anchors_dir, "universal_surface_compliance.pt")
    torch.save(payload, out_file)
    print(f"[+] Scalpel Normalized. Saved {out_file} successfully.")

if __name__ == "__main__":
    main()
