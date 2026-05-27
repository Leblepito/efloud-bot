#!/usr/bin/env python3
import json
import os
import sys

def main():
    # Use container path by default, fallback to local path
    path = "/app/state_1k/positions.json"
    if not os.path.exists(path):
        path = "state_1k/positions.json"
        
    if not os.path.exists(path):
        path = "./state/positions.json"
        
    if not os.path.exists(path):
        print("Error: positions.json not found in standard paths.")
        sys.exit(1)
        
    with open(path) as f:
        try:
            p = json.load(f)
        except Exception as e:
            print(f"Error decoding JSON: {e}")
            sys.exit(1)
            
    print(f"==========================================================")
    print(f"📊 Live Open Positions Count: {len(p)}")
    print(f"==========================================================")
    for k, v in p.items():
        print(f"- Symbol: {k}")
        print(f"  Direction: {v.get('direction')}")
        print(f"  Entry Price: {v.get('entry_price')}")
        print(f"  Size: {v.get('size')}")
        print(f"  Stop Loss: {v.get('sl')}")
        print(f"  Take Profit 1: {v.get('tp1')}")
        print(f"  Take Profit 2: {v.get('tp2')}")
        print(f"----------------------------------------------------------")

if __name__ == "__main__":
    main()
