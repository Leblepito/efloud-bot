from scripts.routines.runner import register
from scripts.routines._base import RoutineResult


def _norm_sym(s):
    """Sembol normalizasyonu (R-2/R-3 tamamlama, 2026-07-17).

    Üç kaynak üç format konuşur: ccxt fetch_positions 'ETH/USDT:USDT',
    bot ledger'ı 'ETH/USDT', Binance raw algo payload'ı 'ETHUSDT'.
    Normalize edilmeden drift map'leri HİÇ eşleşmiyordu → açık her pozisyon
    'exchange var / ledger yok' + 'ledger var / exchange yok' olarak İKİ
    false CRITICAL üretiyordu; bare-position eşleşmesi de algo emirlerini
    göremiyordu.
    """
    return str(s or "").replace("/", "").split(":")[0].upper()


def _algo_to_order(a):
    """Binance raw algo order → evaluate() emir şemasına köprü (R-2, 2026-07-17).

    Botun TP/SL'leri ALGO emirleridir (reconcile'daki fapiPrivateGetOpenAlgoOrders
    ile aynı gerekçe: ccxt fetch_open_orders algo emirlerini DÖNDÜRMEZ). Audit
    yalnız regular emirlere bakınca her korumalı pozisyon 'Bare Position'
    false-CRITICAL'i üretiyordu. reduceOnly default'u True: bot yalnız koruyucu
    algo emri basar; egzotik bir algo girişini korumalı saymak (false-negative),
    her pozisyonu çıplak saymaktan (kalıcı false-positive sayfası) daha güvenli.
    """
    otype = str(a.get("orderType") or a.get("type") or a.get("strategyType") or "")
    reduce_raw = a.get("reduceOnly", True)
    reduce_only = str(reduce_raw).lower() != "false"
    return {
        "symbol": a.get("symbol", ""),
        "type": otype,
        "side": str(a.get("side", "")),
        "reduceOnly": reduce_only,
        "closePosition": str(a.get("closePosition", "false")).lower() == "true",
    }


def _ledger_open_size(rec):
    """Ledger kaydindan ACIK pozisyon boyutu (sema fix, 2026-07-24).

    Bot ledger'i (state_1k/positions.json) engine.lifecycle.Position semasidir:
    boyut top-level contracts/size/positionAmt alanlarinda DEGIL,
    entries[]/exits[] listelerindedir. Eski kod o alanlari arayip HER ledger
    kaydini 0 sayiyordu -> her acik pozisyon "Exchange var / Ledger 0.0"
    false CRITICAL drift uretiyordu (2026-07-24 canli: LINK/ETH/BCH; uc
    pozisyon da botca biliniyor ve positions.json'a taze yaziliyordu).
    Acik boyut = sum(entries.size) - sum(exits.size); exchange-semali kayit
    gelirse (geriye uyum / test fikstürleri) eski alanlar okunur.
    """
    if any(k in rec for k in ("contracts", "size", "positionAmt")):
        return abs(float(rec.get("contracts", 0) or rec.get("size", 0) or rec.get("positionAmt", 0) or 0))
    entered = sum(abs(float(e.get("size", 0) or 0)) for e in (rec.get("entries") or []))
    exited = sum(abs(float(x.get("size", 0) or 0)) for x in (rec.get("exits") or []))
    return max(0.0, entered - exited)


def evaluate(exchange_positions, exchange_open_orders, ledger_positions,
             algo_fetch_ok=True):
    breaches = []
    report_lines = [
        "# Position Audit Report",
        "",
        "## Summary",
    ]

    # 1. Bare Position Audit (SL/TP check)
    # algo_fetch_ok=False iken bu bölüm ATLANIR (fail-safe): TP/SL'ler algo
    # emirleri olduğundan algo fetch'i başarısız bir turda "çıplak" kararı
    # verilemez — reconcile'daki aynı gate felsefesi.
    bare_count = 0
    bare_skipped = not algo_fetch_ok
    for pos in (exchange_positions if algo_fetch_ok else []):
        symbol = pos.get("symbol")
        side = (pos.get("side") or "").lower()
        size = abs(float(pos.get("contracts", 0) or pos.get("size", 0) or pos.get("positionAmt", 0) or 0))
        if size == 0:
            continue

        has_sl = False
        has_tp = False

        for order in exchange_open_orders:
            o_symbol = order.get("symbol", "")
            if _norm_sym(o_symbol) != _norm_sym(symbol):
                continue
            o_type = str(order.get("type", "")).upper()
            o_side = str(order.get("side", "")).upper()
            o_reduce = order.get("reduceOnly", False) or order.get("closePosition", False)
            
            o_side_norm = "sell" if o_side in ("SELL", "SHORT") else "buy" if o_side in ("BUY", "LONG") else o_side.lower()
            side_norm = "sell" if side in ("sell", "short") else "buy" if side in ("buy", "long") else side.lower()
            is_opposite = (side_norm == "buy" and o_side_norm == "sell") or (side_norm == "sell" and o_side_norm == "buy")
            
            is_sl = ("STOP" in o_type or "TRAILING" in o_type) and "PROFIT" not in o_type
            is_tp = "PROFIT" in o_type or o_type in ("LIMIT", "MARKET")
            
            if is_opposite and o_reduce:
                if is_sl:
                    has_sl = True
                if is_tp:
                    has_tp = True
                    
        if not has_sl or not has_tp:
            bare_count += 1
            missing = []
            if not has_sl:
                missing.append("Stop Loss (SL)")
            if not has_tp:
                missing.append("Take Profit (TP)")
            breaches.append({
                "severity": "critical",
                "key": f"bare:{symbol}",
                "title": f"Bare Position: {symbol}",
                "body": f"Exchange position {side} of size {size} is missing protective: {', '.join(missing)}"
            })
            
    # 2. Orphan Orders Audit
    orphan_count = 0
    open_symbols = {_norm_sym(p["symbol"]) for p in exchange_positions if abs(float(p.get("contracts", 0) or p.get("size", 0) or p.get("positionAmt", 0) or 0)) > 0}
    for order in exchange_open_orders:
        symbol = order.get("symbol")
        o_reduce = order.get("reduceOnly", False) or order.get("closePosition", False)
        o_type = str(order.get("type", "")).upper()
        is_sl_or_tp = "STOP" in o_type or "PROFIT" in o_type or o_reduce
        if is_sl_or_tp and _norm_sym(symbol) not in open_symbols:
            orphan_count += 1
            breaches.append({
                "severity": "warn",
                "key": f"orphan:{symbol}",
                "title": f"Orphan Order: {symbol}",
                "body": f"Open Algo order (type: {o_type}, reduceOnly: {o_reduce}) exists but no active position on exchange."
            })
            
    # 3. Ledger vs Exchange Reconciliation (Drift Check)
    # _norm_sym: ccxt 'ETH/USDT:USDT' ↔ ledger 'ETH/USDT' başka türlü eşleşmez.
    drift_count = 0
    ex_map = {_norm_sym(p["symbol"]): p for p in exchange_positions}
    # Ayni sembol eski-kapali + yeni-acik kayitlarla birden fazla gelebilir;
    # comprehension SON kaydi tutar = kronolojik en yeni (bot sembol basina
    # tek acik pozisyon calistigi icin guvenli).
    ld_map = {_norm_sym(p["symbol"]): p for p in ledger_positions}
    
    all_symbols = set(ex_map.keys()) | set(ld_map.keys())
    for symbol in all_symbols:
        ex_pos = ex_map.get(symbol)
        ld_pos = ld_map.get(symbol)
        
        ex_size = abs(float(ex_pos.get("contracts", 0) or ex_pos.get("size", 0) or ex_pos.get("positionAmt", 0) or 0)) if ex_pos else 0.0
        # 2026-07-24 sema fix: ledger Position semasi (entries/exits) -> helper.
        ld_size = _ledger_open_size(ld_pos) if ld_pos else 0.0
        
        if ex_size == 0 and ld_size == 0:
            continue
            
        if ex_size == 0 or ld_size == 0:
            drift_count += 1
            breaches.append({
                "severity": "critical",
                "key": f"drift:{symbol}",
                "title": f"Position Drift: {symbol}",
                "body": f"Position presence mismatch. Exchange size: {ex_size}, Ledger size: {ld_size}"
            })
        else:
            diff_pct = abs(ex_size - ld_size) / ex_size * 100
            if diff_pct > 1.0:
                drift_count += 1
                breaches.append({
                    "severity": "critical",
                    "key": f"drift:{symbol}",
                    "title": f"Position Drift: {symbol}",
                    "body": f"Exchange size ({ex_size}) vs ledger size ({ld_size}) differs by {diff_pct:.2f}% (limit: 1.0%)"
                })
                
    if bare_skipped:
        report_lines.append("- **Bare Positions:** SKIPPED (algo orders fetch failed this run)")
    else:
        report_lines.append(f"- **Bare Positions (Missing SL/TP):** {bare_count}")
    report_lines.append(f"- **Orphan Orders:** {orphan_count}")
    report_lines.append(f"- **Position Size Drifts:** {drift_count}")
    report_lines.append("")
    
    if breaches:
        report_lines.append("## Flagged Issues")
        for b in breaches:
            report_lines.append(f"### [{b['severity'].upper()}] {b['title']}")
            report_lines.append(f"{b['body']}")
            report_lines.append("")
            
    report_text = "\n".join(report_lines)
    return report_text, breaches

@register("position_audit")
def run(client=None, alert=None, cfg=None):
    from scripts.routines._base import (
        read_snapshot, write_snapshot, write_report, RoutineResult,
        resolve_state_dir, unwrap_state,
    )
    import os

    # R-3 fix (2026-07-17): env override'lı state_dir — canlı prod ./state_1k'ya
    # yazar; root config baseline'ıyla ./state okumak boş ledger → her açık
    # pozisyonda kalıcı false "Position Drift" CRITICAL üretiyordu.
    ledger_path = os.path.join(resolve_state_dir(cfg), "positions.json")
    report_path = "reports/position_audit.md"
    snapshot_path = "state/position_audit_snapshot.json"
    
    try:
        # Fetch exchange state
        positions = client.fetch_positions()
        active_exchange_positions = [
            p for p in positions 
            if abs(float(p.get("contracts", 0) or p.get("size", 0) or p.get("positionAmt", 0) or 0)) > 0
        ]
        
        open_orders = list(client.fetch_open_orders())

        # R-2 tamamlama (2026-07-17): botun TP/SL'leri ALGO emirleri — ccxt
        # fetch_open_orders bunları DÖNDÜRMEZ (reconcile'daki aynı gerçek).
        # Algo emirleri de taranmazsa her korumalı pozisyon "Bare Position"
        # false-CRITICAL üretir. Fetch başarısızsa bare-position bölümü bu
        # turda atlanır (fail-safe; evaluate algo_fetch_ok=False).
        algo_fetch_ok = True
        try:
            algo_raw = client.fapiPrivateGetOpenAlgoOrders({}) or []
            open_orders.extend(_algo_to_order(a) for a in algo_raw)
        except Exception as algo_exc:
            algo_fetch_ok = False
            print(f"position_audit: algo orders fetch failed ({algo_exc}) — "
                  f"bare-position audit skipped this run")

        # Load local ledger positions
        # R-3 fix: StateStore zarfını aç ({"saved_at":…, "data":[…]}) — zarfsız
        # okuma listeyi göremeyip ledger'ı hep boş sayıyordu.
        ledger_data = unwrap_state(read_snapshot(ledger_path))
        # Handle positions.json which could be a list or a dict
        if isinstance(ledger_data, dict) and "positions" in ledger_data:
            ledger_positions = ledger_data["positions"]
        elif isinstance(ledger_data, list):
            ledger_positions = ledger_data
        else:
            ledger_positions = []
            
    except Exception as e:
        import traceback
        print(f"Error executing position audit: {e}")
        traceback.print_exc()
        return RoutineResult(
            name="position_audit",
            ok=False,
            error=str(e)
        )
        
    report_text, breaches = evaluate(active_exchange_positions, open_orders,
                                     ledger_positions, algo_fetch_ok=algo_fetch_ok)
    
    write_report(report_path, report_text)
    
    snapshot_data = {
        "active_exchange_positions": active_exchange_positions,
        "open_orders": open_orders,
        "ledger_positions": ledger_positions,
        "breaches_count": len(breaches)
    }
    write_snapshot(snapshot_path, snapshot_data)
    
    return RoutineResult(
        name="position_audit",
        ok=True,
        breaches=breaches,
        report_path=report_path
    )
