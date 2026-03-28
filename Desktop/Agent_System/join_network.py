#!/usr/bin/env python3
"""
ALEPH Network — Frictionless Node Announcer
Usage: python join_network.py

Spools up an ephemeral Cloudflare tunnel and automatically broadcasts
your presence to the federated ALEPH mesh.
"""

import subprocess
import time
import re
import sys
import json
from urllib import request, error
from datetime import datetime, timezone

ORIGIN_NODE = "https://aleph.manifesto-engine.com"

def spin_tunnel(port: int = 8800) -> tuple[subprocess.Popen, str]:
    print("\033[96m[ALEPH]\033[0m \033[93mProvisioning ephemeral federated tunnel...\033[0m")
    try:
        subprocess.run(["cloudflared", "--version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\033[91m[ALEPH ERROR] 'cloudflared' not found. Please install it first.\033[0m")
        sys.exit(1)

    proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    url = None
    url_pattern = re.compile(r"(https://[a-zA-Z0-9-]+\.trycloudflare\.com)")
    
    start_time = time.time()
    for line in iter(proc.stdout.readline, ''):
        match = url_pattern.search(line)
        if match:
            url = match.group(1)
            break
        if time.time() - start_time > 15:
            print("\033[91m[ALEPH TIMEOUT] Failed to acquire tunnel URL.\033[0m")
            proc.terminate()
            sys.exit(1)
            
    if not url:
        print("\033[91m[ALEPH ERROR] Could not parse trycloudflare.com URL.\033[0m")
        proc.terminate()
        sys.exit(1)
        
    return proc, url

def post_beacon(endpoint_url: str):
    payload = {
        "node_id": "aleph-community-node",
        "operator": "anonymous-developer",
        "endpoint": endpoint_url,
        "capabilities": ["query", "peers"],
        "standing": 10,
        "corpus_size": 0,
        "online_since": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ttl": 300,
        "beacon_seq": 1,
        "signature": "ed25519:community-join"
    }

    data = json.dumps(payload).encode("utf-8")
    req = request.Request(f"{ORIGIN_NODE}/aleph/v1/beacon", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with request.urlopen(req, timeout=10) as response:
                if response.status in (200, 201):
                    return True
        except error.URLError as e:
            if attempt == max_retries - 1:
                print(f"\033[91m[ALEPH ERROR] Mesh ping failed: {e}\033[0m")
        time.sleep(2)
    return False

def main():
    print(f"\n\033[96mALEPH PROTOCOL BOOTSTRAP\033[0m")
    print(f"Connecting to Origin Network: {ORIGIN_NODE}\n")
    
    proc, url = spin_tunnel(port=8800)
    
    print(f"\n\033[92m● NODE ONLINE\033[0m")
    print(f"Live URI: \033[1;97m{url}\033[0m\n")
    print("\033[93mBroadcasting beacon to federated mesh...\033[0m")
    
    try:
        sequence = 1
        while True:
            if post_beacon(url):
                print(f"\033[92m[✓] Sent Beacon Seq {sequence} to {ORIGIN_NODE}\033[0m")
            else:
                print(f"\033[91m[✗] Failed to broadcast seq {sequence}\033[0m")
            
            sequence += 1
            # Sleep 4 minutes (TTL is 300s/5min)
            time.sleep(240)
            
    except KeyboardInterrupt:
        print("\n\033[93m[ALEPH] Disconnecting from mesh and tearing down tunnel...\033[0m")
    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    main()
