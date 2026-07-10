import logging
import time
from typing import Dict, List, Any, Optional

from .llm import make_llm_client

log = logging.getLogger("efloud.agents.leblep")

class LeblepMultiLLMOrchestrator:
    def __init__(self, config: Dict[str, Any]):
        self.cfg = config
        self.providers = {}

        # Leblep disabled by default - shadow mode only
        if not self.cfg.get("leblep_enabled", False):
            log.info("Leblep disabled (leblep_enabled=false)")
            return

        provider_configs = self.cfg.get("leblep_providers", {})
        for provider_name, provider_cfg in provider_configs.items():
            # Skip disabled providers
            if not provider_cfg.get("enabled", False):
                log.info(f"Leblep provider {provider_name} disabled (enabled=false)")
                continue

            try:
                client = make_llm_client(provider_cfg)

                # Health check: probe provider with simple JSON request
                probe_start = time.time()
                probe = client.complete_json('Return JSON {"status":"ok"}')
                probe_duration = time.time() - probe_start

                if not probe or probe.get("status") != "ok":
                    log.warning(f"Leblep {provider_name} health check failed — skipped")
                    continue

                self.providers[provider_name] = {
                    "client": client,
                    "role": provider_cfg.get("role", "secondary"),
                    "weight": provider_cfg.get("weight", 1.0),
                    "timeout": provider_cfg.get("timeout", 5.0),
                    "cb_failures": 0  # circuit breaker failure count
                }
                log.info(f"Leblep {provider_name} validated + enabled (probe: {probe_duration:.2f}s)")

            except Exception as e:
                log.warning(f"Leblep {provider_name} init failed: {e}")

        if not self.providers:
            log.warning("No Leblep providers passed health check - Leblep inactive")

    def query_consensus(self, prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        if not self.providers:
            return {
                "consensus_verdict": "ERROR",
                "confidence": 0.0,
                "provider_verdicts": {},
                "reasoning": "No Leblep providers configured or healthy"
            }

        # Quorum requirement: need ≥2 live providers
        if len(self.providers) < 2:
            log.warning(f"Leblep quorum failed: only {len(self.providers)} providers available")
            return {
                "consensus_verdict": "ERROR",
                "confidence": 0.0,
                "provider_verdicts": {},
                "reasoning": f"Quorum failed: need ≥2 providers, have {len(self.providers)}"
            }

        provider_verdicts = {}
        for provider_name, provider_info in self.providers.items():
            try:
                client = provider_info["client"]
                timeout = provider_info.get("timeout", 5.0)

                # Add timeout handling
                start_time = time.time()
                result = client.complete_json(prompt)
                duration = time.time() - start_time

                if duration > timeout:
                    log.warning(f"Leblep provider {provider_name} timeout ({duration:.2f}s > {timeout}s)")
                    provider_verdicts[provider_name] = {"verdict": "ERROR", "confidence": 0.0}
                    # Circuit breaker: increment failure count
                    provider_info["cb_failures"] += 1
                    continue

                provider_verdicts[provider_name] = self._parse_verdict(result)
                # Reset circuit breaker on success
                provider_info["cb_failures"] = 0

            except Exception as e:
                log.warning(f"Leblep provider {provider_name} failed: {e}")
                provider_verdicts[provider_name] = {"verdict": "ERROR", "confidence": 0.0}
                provider_info["cb_failures"] += 1

        return self._aggregate_consensus(provider_verdicts, context)

    def _parse_verdict(self, raw_result: dict) -> Dict[str, Any]:
        if not raw_result:
            return {"verdict": "ERROR", "confidence": 0.0}
        verdict = str(raw_result.get("verdict", "ERROR")).upper()
        try:
            confidence = float(raw_result.get("confidence", 0.5))
        except (ValueError, TypeError):
            confidence = 0.5
        reasoning = raw_result.get("reasoning", "")
        return {"verdict": verdict, "confidence": confidence, "reasoning": reasoning}

    def _aggregate_consensus(self, provider_verdicts: Dict, context: Dict) -> Dict[str, Any]:
        if not provider_verdicts:
            return {"consensus_verdict": "ERROR", "confidence": 0.0, "reasoning": "No verdicts"}

        # Filter out ERROR verdicts
        valid_verdicts = {
            name: verdict for name, verdict in provider_verdicts.items()
            if verdict.get("verdict") != "ERROR"
        }

        if len(valid_verdicts) < 2:
            return {
                "consensus_verdict": "ERROR",
                "confidence": 0.0,
                "provider_verdicts": provider_verdicts,
                "reasoning": f"Consensus failed: only {len(valid_verdicts)} valid verdicts (need ≥2)"
            }

        total_weight = 0.0
        weighted_approve = 0.0
        weighted_reject = 0.0
        for provider_name, verdict_info in valid_verdicts.items():
            weight = self.providers.get(provider_name, {}).get("weight", 1.0)
            confidence = verdict_info.get("confidence", 0.5)
            verdict = verdict_info.get("verdict", "ERROR")
            total_weight += weight
            if verdict == "APPROVE":
                weighted_approve += weight * confidence
            elif verdict == "REJECT":
                weighted_reject += weight * confidence

        if total_weight == 0:
            return {"consensus_verdict": "ERROR", "confidence": 0.0, "reasoning": "No valid providers"}

        approve_score = weighted_approve / total_weight
        reject_score = weighted_reject / total_weight
        if approve_score > reject_score:
            consensus_verdict = "APPROVE"
            confidence = approve_score
        else:
            consensus_verdict = "REJECT"
            confidence = reject_score

        reasoning = f"Consensus: {consensus_verdict} (approve={approve_score:.2f}, reject={reject_score:.2f})"
        return {
            "consensus_verdict": consensus_verdict,
            "confidence": confidence,
            "provider_verdicts": provider_verdicts,
            "reasoning": reasoning
        }