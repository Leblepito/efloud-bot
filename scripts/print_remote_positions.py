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
            
    positions_list = p.get("data", [])
    
    print(f"==========================================================")
    print(f"📊 Live Open Positions Count: {len([x for x in positions_list if x.get('closed_at') is None])}")
    print(f"📊 Total Trades History Count: {len(positions_list)}")
    print(f"==========================================================")
    for v in positions_list:
        status = "OPEN" if v.get("closed_at") is None else f"CLOSED at {v.get('closed_at')}"
        print(f"- Symbol: {v.get('symbol')} ({status})")
        print(f"  Direction: {v.get('direction')}")
        entries = v.get("entries", [])
        if entries:
            print(f"  Entry Price: {entries[0].get('price')} (Initial)")
        print(f"  Stop Loss: {v.get('sl')}")
        print(f"  Take Profit 1: {v.get('tp1')}")
        print(f"  Take Profit 2: {v.get('tp2')}")
        exits = v.get("exits", [])
        if exits:
            pnl = sum(e.get("pnl", 0.0) for e in exits)
            print(f"  Realized PnL: {pnl:.4f} USDT")
        print(f"----------------------------------------------------------")

if __name__ == "__main__":
    main()
