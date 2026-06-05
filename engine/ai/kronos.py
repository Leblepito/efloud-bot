"""Kronos Prediction & LLM Synthesis Pipeline.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Handles subprocess execution of the Kronos model runner, parsing of time-series
forecast outputs, and LLM synthesis of the final commentary.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# NOTE: the LLM client is INJECTED (duck-typed ``complete_json(prompt) -> dict``)
# rather than imported here. The bot resolves it via
# ``engine.agents.llm.make_llm_client`` so the provider (MiniMax in prod, see the
# Claude→MiniMax migration) and the global ``LLM_PROVIDER`` lever stay in sync
# with every other advisory call site. Hard-wiring a specific client here would
# bypass that and 404 in prod.

log = logging.getLogger("efloud.ai.kronos")


def get_yfinance_ticker(symbol: str) -> str:
    """Convert a Binance symbol to a yfinance-compatible crypto/fiat ticker.
    Examples:
      BTCUSDT -> BTC-USD
      ETHUSDT -> ETH-USD
      BTC/USDT:USDT -> BTC-USD
    """
    # Strip any contract suffix (e.g. :USDT)
    clean = symbol.replace("/", "").split(":")[0].upper()
    if clean.endswith("-USD"):
        return clean
    if clean.endswith("USDT"):
        return clean[:-4] + "-USD"
    if clean.endswith("USD"):
        return clean[:-3] + "-USD"
    # Fallback to appending -USD if not already containing a dash
    if "-" not in clean:
        return f"{clean}-USD"
    return clean


def run_kronos_prediction(
    symbol: str,
    period: str = "1mo",
    interval: str = "1h",
    pred_len: int = 24,
    df: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run the Kronos prediction script as a subprocess and parse its output.
    
    Returns a dictionary of parsed forecast metrics or a default empty dictionary
    if execution fails.
    """
    ticker = get_yfinance_ticker(symbol)
    project_root = Path(__file__).resolve().parent.parent.parent
    script_path = project_root / "external_repos" / "kronos-claude-skill" / "scripts" / "run_kronos.py"
    
    if not script_path.exists():
        log.warning(f"Kronos skill runner not found at: {script_path}")
        return {}

    temp_file = None
    if df is not None:
        try:
            import tempfile
            df_cleaned = df.copy()
            df_cleaned.columns = [c.lower() for c in df_cleaned.columns]
            
            # Normalize index name: DatetimeIndex named "timestamp" -> "timestamps"
            if df_cleaned.index.name == "timestamp":
                df_cleaned.index.name = "timestamps"
            elif df_cleaned.index.name is None or df_cleaned.index.name != "timestamps":
                df_cleaned.index.name = "timestamps"
                
            df_cleaned = df_cleaned[["open", "high", "low", "close", "volume"]]
            
            fd, temp_path = tempfile.mkstemp(suffix=".parquet")
            os.close(fd)
            temp_file = temp_path
            df_cleaned.to_parquet(temp_file)
        except Exception as write_err:
            log.warning(f"Failed to write temp parquet for Kronos: {write_err}")
            temp_file = None

    cmd = [sys.executable, str(script_path), ticker, period, interval, str(pred_len)]
    if temp_file:
        cmd.extend(["--df-path", temp_file])

    log.info(f"Running Kronos: {' '.join(cmd)}")
    
    try:
        # First run will download weights (~500MB) and build venv, so timeout is relaxed
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600.0,  # 10 minutes maximum for first run
            check=False,
        )
        if proc.returncode != 0:
            log.warning(f"Kronos process returned non-zero code {proc.returncode}. Stderr: {proc.stderr}")
            return {}

        stdout = proc.stdout
        log.debug(f"Kronos stdout: {stdout}")

        # Parse stdout using regex
        parsed = {"raw_output": stdout}
        
        # Extract last close
        m_last = re.search(r"\*\*Last close:\*\*\s+\$?([0-9,.]+)", stdout)
        if m_last:
            parsed["last_close"] = float(m_last.group(1).replace(",", ""))

        # Extract predicted close
        m_pred = re.search(r"\*\*Predicted close[^:]*:\*\*\s+\$?([0-9,.]+)", stdout)
        if m_pred:
            parsed["predicted_close"] = float(m_pred.group(1).replace(",", ""))

        # Extract direction and change percentage
        m_dir = re.search(r"\*\*Direction:\*\*\s+([A-Z]+)\s+\(([-+0-9.]+)%\)", stdout)
        if m_dir:
            parsed["predicted_direction"] = m_dir.group(1)
            parsed["change_pct"] = float(m_dir.group(2))

        # Extract confidence band — restrict to the known vocabulary so a format
        # drift can never inject a junk token (e.g. "UNKNOWN") into the downstream
        # LLM prompt. On no-match default to the MOST conservative band
        # (WIDE = treat as noise) and warn, rather than silently passing an
        # unparseable value the model then reasons over.
        m_conf = re.search(r"\*\*Confidence band:\*\*\s+(NARROW|MODERATE|WIDE)", stdout)
        if m_conf:
            parsed["confidence_band"] = m_conf.group(1)
        else:
            log.warning("Kronos confidence band unparseable — defaulting to WIDE")
            parsed["confidence_band"] = "WIDE"

        # Extract forecast range
        m_range = re.search(r"\*\*Forecast range:\*\*\s+\$?([0-9,.]+)\s+-\s+\$?([0-9,.]+)", stdout)
        if m_range:
            parsed["range_low"] = float(m_range.group(1).replace(",", ""))
            parsed["range_high"] = float(m_range.group(2).replace(",", ""))

        log.info(f"Successfully parsed Kronos output: {parsed.get('predicted_direction')} | {parsed.get('confidence_band')}")
        return parsed

    except subprocess.TimeoutExpired:
        log.warning(f"Kronos prediction timed out for symbol {symbol}")
        return {}
    except Exception as e:
        log.warning(f"Error executing Kronos prediction: {e}")
        return {}
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception as rm_err:
                log.warning(f"Failed to remove temp parquet file {temp_file}: {rm_err}")


def synthesize_signal_with_kronos(
    symbol: str,
    direction: str,
    entry: float,
    sl: float,
    tp1: float,
    tp2: Optional[float],
    confluence: int,
    reasons: List[str],
    kronos_data: Dict[str, Any],
    llm_client: Any,
) -> Dict[str, Any]:
    """Synthesize the bot's SMC trade signal with the Kronos time-series prediction.

    ``llm_client`` is any object exposing ``complete_json(prompt) -> dict`` (built
    by :func:`engine.agents.llm.make_llm_client`). Returns a dict with:
      - ``comment``    (Turkish text)
      - ``confidence`` (0-100 advisory score — NEVER feeds trade/sizing logic)
      - ``source``     ('llm' when the model answered, 'fallback' when a static
                        message was substituted) so callers can flag degraded output.
    """
    if not kronos_data:
        # Return fallback values if Kronos did not run successfully
        base_conf = min(95, max(30, int(confluence * 0.9)))
        return {
            "comment": (
                f"{symbol} için SMC modelimiz {direction} yönlü bir kurulum tespit etti. "
                f"Zaman serisi tahmin modeli (Kronos) şu an için çevrimdışı olduğundan "
                f"teknik yapı analizi doğrudan confluence verilerine ({confluence}/100) göre işlenmiştir."
            ),
            "confidence": base_conf,
            "source": "fallback",
        }

    # Format setup info
    tp2_str = f"{tp2:.4f}" if tp2 is not None else "N/A"
    reasons_str = ", ".join(reasons) if reasons else "SMC swing breakout"
    
    prompt = f"""You are a professional AI Quantitative Analyst and Crypto Trader.
Synthesize the Smart Money Concepts (SMC) setup from our automated trading bot with the time-series price prediction from the Kronos technical forecasting model.

Bot SMC Signal Details:
- Symbol: {symbol}
- Direction: {direction} (LONG/SHORT)
- Entry Price: {entry:.4f}
- Stop Loss: {sl:.4f}
- Take Profit 1 (Target): {tp1:.4f}
- Take Profit 2 (Extension): {tp2_str}
- Confluence Score: {confluence}/100
- Setup Reasons: {reasons_str}

Kronos Time-Series Forecast Details:
- Last Close: {kronos_data.get('last_close')}
- Predicted Close: {kronos_data.get('predicted_close')}
- Predicted Direction: {kronos_data.get('predicted_direction')} ({kronos_data.get('change_pct', 0.0):+.2f}%)
- Confidence Band: {kronos_data.get('confidence_band', 'UNKNOWN')}
- Forecast Range: {kronos_data.get('range_low')} - {kronos_data.get('range_high')}

Your Task:
1. Synthesize these analyses. Explain how the time-series model's forecast trajectory supports, diverges from, or acts as noise/hedging relative to the SMC setup.
2. Write a high-quality, professional, and institutional trading commentary in Turkish (Türkçe). Explain the rationale clearly in a way that is insightful for premium traders.
3. Determine a synthesized confidence score (integer, 0 to 100) for this setup.
   - If Kronos confirms the direction and has a NARROW band (high confidence), the synthesized confidence should be high.
   - If Kronos conflicts with the direction, or has a WIDE band (treated as noise), the synthesized confidence should be lowered, and the commentary must warn about this divergence.

You MUST respond strictly with a JSON object matching this schema (do not wrap in markdown blocks, do not include any other text):
{{
  "comment": "Synthesized commentary in Turkish...",
  "confidence": 85
}}
"""

    try:
        res = llm_client.complete_json(prompt)
        if not res or "comment" not in res:
            raise ValueError("Empty or invalid response from LLM provider")

        # Ensure confidence is a valid integer between 0 and 100
        conf = res.get("confidence", confluence)
        try:
            conf = int(conf)
            conf = min(100, max(0, conf))
        except (ValueError, TypeError):
            conf = confluence

        return {
            "comment": res["comment"],
            "confidence": conf,
            "source": "llm",
        }
    except Exception as e:
        log.warning(f"Failed to synthesize signal with LLM provider: {e}")
        # Graceful fallback — static commentary derived purely from the parsed
        # Kronos band + direction alignment. Tagged source='fallback' so the
        # caller can mark the Telegram/DB output as degraded (a dead provider
        # must be VISIBLE, not silently dressed up as a real AI verdict).
        kronos_dir = kronos_data.get("predicted_direction", "FLAT")
        kronos_conf = kronos_data.get("confidence_band", "WIDE")
        aligned = (direction == "LONG" and kronos_dir == "UP") or (direction == "SHORT" and kronos_dir == "DOWN")

        fallback_comment = (
            f"{symbol} üzerinde {direction} yönlü SMC kurulumu. "
            f"Kronos zaman serisi analizi, {kronos_conf} güven bandında bir {kronos_dir} hareketi öngörüyor. "
            f"İki modelin yön uyumu: {'Uyumlu' if aligned else 'Uyumsuz/Belirsiz'}. Risk yönetimini elden bırakmayınız."
        )
        return {
            "comment": fallback_comment,
            "confidence": int(confluence * 0.95) if aligned else int(confluence * 0.75),
            "source": "fallback",
        }
