import json
import random
import os
import sys
import time
import urllib.request
from typing import TypedDict

# The organism's local model API (Ollama backend)
OLLAMA_URL = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/generate"
MODEL_NAME = "qwen2.5:1.5b" # Adjust to active frontier or local model dynamically if needed
TARGET_PAIRS = 10000

ORGANISM_FACTS = [
    "The Sovereign Engine uses an autonomous Agentic Trio workflow.",
    "CortexDB implements biologically-inspired cognitive memory with Ebbinghaus decay.",
    "The Callosum router isolates tool synthesis from primary generative loops.",
    "WORKSPACE_JAIL enforces strict filesystem boundaries.",
    "The Reaper Security Framework utilizes pidfd and cgroups to quarantine execution strings.",
    "The Functional Trio pattern consists of Extractor, LLM, and Critic.",
    "Bio-Agentic AST strips python files into API surface JSON.",
    "Manifesto Engine v6.0 dictates the architectural principles of independent agent life.",
    "Ionichalo is the high-performance binary communication protocol for agent-to-agent operations.",
]

GENERIC_DOMAINS = [
    "Mathematics and logic",
    "Physics and quantum mechanics",
    "Historical timelines and civilizations",
    "Biology and genetics",
    "Geopolitics and geography"
]

def generate_pair(domain: str, is_organism: bool) -> dict:
    prompt = ""
    if is_organism:
        base_fact = random.choice(ORGANISM_FACTS)
        prompt = f"Given the absolute fact: '{base_fact}', generate a JSON object with two fields. 'true_statement': a rephrasing or elaboration of the fact. 'false_statement': a plausible sounding but factually incorrect contradiction of the fact. Output ONLY valid JSON."
    else:
        prompt = f"In the domain of {domain}, generate a JSON object with two fields. 'true_statement': a verifiable, complex true statement. 'false_statement': a plausible-sounding but completely false statement contradicting the domain logic. Output ONLY valid JSON."

    payload = json.dumps({
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "format": "json"
    }).encode("utf-8")

    try:
        req = urllib.request.Request(OLLAMA_URL, data=payload, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=30) as response:
            res = json.loads(response.read().decode())
            data = json.loads(res["response"])
            if "true_statement" in data and "false_statement" in data:
                return data
    except Exception as e:
        print(f"[!] Generate error: {str(e)}")
    return {}

def main():
    print(f"[*] Starting 10k Honesty Campaign Data Forge.")
    print(f"[*] Target Model: {MODEL_NAME}")
    dataset_file = "honesty_corpus.jsonl"
    
    current_count = 0
    if os.path.exists(dataset_file):
        with open(dataset_file, "r") as f:
            current_count = len(f.readlines())
    
    print(f"[*] Current corpus size: {current_count}/{TARGET_PAIRS}")
    
    with open(dataset_file, "a") as out_f:
        while current_count < TARGET_PAIRS:
            # 70/30 distribution as commanded
            is_organism = random.random() > 0.70
            
            domain = random.choice(GENERIC_DOMAINS) if not is_organism else "Sovereign Engine"
            sys.stdout.write(f"\\r[-] Forging Pair {current_count+1} (Domain: {domain})...")
            sys.stdout.flush()
            
            pair = generate_pair(domain, is_organism)
            
            if pair:
                pair["domain"] = domain
                pair["is_organism"] = is_organism
                out_f.write(json.dumps(pair) + "\\n")
                out_f.flush()
                current_count += 1
                
            time.sleep(0.5) # Prevent overloading the local engine during background execution
            
    print(f"\\n[+] Campaign Forge Complete: {TARGET_PAIRS} generated.")

if __name__ == "__main__":
    main()
