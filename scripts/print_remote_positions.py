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
            
    positions_list = p.get("positions", [])
    open_positions = [v for v in positions_list if v.get("closed_at") is None]
    
    print(f"==========================================================")
    print(f"📊 Live Open Positions Count: {len(open_positions)}")
    print(f"==========================================================")
    for v in open_positions:
        print(f"- Symbol: {v.get('symbol')}")
        print(f"  Direction: {v.get('direction')}")
        # Parse entry details
        entries = v.get("entries", [])
        if entries:
            print(f"  Entry Price: {entries[0].get('price')} (Initial)")
        else:
            print(f"  Entry Price: Unknown")
        print(f"  Stop Loss: {v.get('sl')}")
        print(f"  Take Profit 1: {v.get('tp1')}")
        print(f"  Take Profit 2: {v.get('tp2')}")
        print(f"  Max Adverse Excursion (MAE): {v.get('mae_pct'):.4f}%")
        print(f"  Max Favorable Excursion (MFE): {v.get('mfe_pct'):.4f}%")
        print(f"----------------------------------------------------------")

if __name__ == "__main__":
    main()
