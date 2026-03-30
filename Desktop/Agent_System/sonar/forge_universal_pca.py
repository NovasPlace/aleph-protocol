import torch
import os
import sys

def main():
    print("[*] Forging Universal Surface Compliance Anchor (PCA Extraction)...")
    
    anchors_dir = "anchors"
    
    # Load the 3 surface anchors
    try:
        emo_payload = torch.load(os.path.join(anchors_dir, "emotional_manipulation_immunity.pt"), map_location="cpu", weights_only=False)
        conf_payload = torch.load(os.path.join(anchors_dir, "confidence_calibration.pt"), map_location="cpu", weights_only=False)
        pois_payload = torch.load(os.path.join(anchors_dir, "cortex_memory_poisoning.pt"), map_location="cpu", weights_only=False)
    except Exception as e:
        print(f"[!] Missing anchor file: {e}")
        sys.exit(1)
    
    v_emo = emo_payload["vector"]
    v_conf = conf_payload["vector"]
    v_pois = pois_payload["vector"]
    
    # Stack the vectors into a matrix [3, D]
    X = torch.stack([v_emo, v_conf, v_pois])
    
    # Run PCA (SVD) to find the primary axis of variance/compliance rejection
    # We set center=False because the vectors are already centered around the ground truth differential.
    # The first right singular vector represents the exact shared rejection basin.
    U, S, V = torch.pca_lowrank(X, q=1, center=False)
    
    # V[:, 0] is the primary principal component of shape [D]
    principal_component = V[:, 0]
    
    # Check orientation: The dot product of PC1 with the original vectors should be positive 
    # if it's pointing in the rejection direction. If not, flip the sign.
    if torch.dot(principal_component, v_emo) < 0:
        principal_component = -principal_component
        
    payload = {
        "metadata": {
            "immunity_type": "universal_surface_compliance_pca",
            "model_architecture_origin": "Qwen/Qwen2.5-1.5B",
            "target_layer": 26, # Universal Surface Convergence coordinate
            "recommended_multiplier": 50.0, # PCA vectors are normalized to unit length, so they need a scaled multiplier to match original L2 norms (~60-100)
            "version": "1.0",
            "notes": "Extracted via Principal Component Analysis (PC1) across Emotion, Confidence, and Memory Posioning vectors."
        },
        "vector": principal_component
    }
    
    out_file = os.path.join(anchors_dir, "universal_surface_compliance_pca.pt")
    torch.save(payload, out_file)
    print(f"[+] Scalpel Normalized (PCA Component 1). Saved {out_file} successfully.")
    
    # Calculate Variance explained
    total_var = torch.sum(X ** 2)
    explained_var = (S[0] ** 2)
    ratio = explained_var / total_var
    print(f"[*] Variance explained by PC1: {ratio.item():.2%}")

if __name__ == "__main__":
    main()
