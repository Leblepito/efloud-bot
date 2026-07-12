"""
Adaptive Config — Self-Tuning Parameter Engine
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Learning Memory'deki hata pattern'lerine göre bot'un parametrelerini
otomatik adapte eder. Her trade'den sonra değil — her N trade'de bir
tekrar değerlendirilir (aşırı oscilasyon yapmaması için).

Adaptasyonlar persistent — diskte `adaptive_config.json` dosyasında
tutulur, bot yeniden başlayınca öğrendikleri kaybolmaz.

Her adaptasyon için:
  - before_value (orijinal)
  - current_value (adapte edilmiş)
  - source_pattern (hangi hata sebep oldu)
  - applied_at (ne zaman değişti)
  - win_rate_before (adaptasyondan önce başarı oranı)
"""

import json
import logging
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional
from datetime import datetime, timezone

from .memory import LearningMemory, Pattern

log = logging.getLogger("efloud.adaptive")


@dataclass
class Adaptation:
    param: str
    before: float
    current: float
    delta: float
    source_pattern: str
    severity: str
    applied_at: str
    win_rate_before: float = 0.0


class AdaptiveConfig:
    """Botun parametrelerini öğrenilen hatalara göre ayarlar."""

    # Adaptasyon kuralları: hangi hata hangi param'ı ne kadar değiştirir
    RULES = {
        "LOW_CONFLUENCE":   {"param": "min_confluence", "delta": +5, "min": 40, "max": 85},
        "TIGHT_SL":         {"param": "sl_atr_buffer",  "delta": +0.25, "min": 0.25, "max": 2.0},
        "LOOSE_SL":         {"param": "sl_atr_buffer",  "delta": -0.25, "min": 0.25, "max": 2.0},
        "TP_OVERSHOT":      {"param": "fib_ext_tp2",    "delta": +0.5, "min": 1.0, "max": 4.0},
        "TP_UNDERSHOT":     {"param": "fib_ext_tp2",    "delta": -0.3, "min": 1.0, "max": 4.0},
        "PREMIUM_LONG":     {"param": "zone_filter_active", "delta": True, "bool": True},
        "DISCOUNT_SHORT":   {"param": "zone_filter_active", "delta": True, "bool": True},
        "WRONG_BIAS":       {"param": "strict_htf_alignment", "delta": True, "bool": True},
        "AGAINST_INTENT":   {"param": "min_intent_score", "delta": +10, "min": 30, "max": 80},
        "NO_OB_SUPPORT":    {"param": "require_ob_or_fvg", "delta": True, "bool": True},
        "LOW_VOLUME_ENTRY": {"param": "min_volume_ratio", "delta": +0.1, "min": 0.7, "max": 2.0},
    }

    # Trigger için minimum recent_frequency
    ADAPTATION_TRIGGER_THRESHOLD = 3

    def __init__(self, base_config: dict,
                 memory: LearningMemory,
                 state_path: str = "adaptive_config.json",
                 revaluation_interval: int = 5):
        """
        Args:
            base_config: bot'un orijinal config'i
            memory: LearningMemory instance
            state_path: adaptasyonların persist edildiği dosya
            revaluation_interval: her N trade'de bir tekrar değerlendir
        """
        self.base = base_config
        self.memory = memory
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.interval = revaluation_interval

        self.overrides: Dict[str, float] = {}
        self.adaptations: List[Adaptation] = []
        self.last_eval_trade_count = 0

        self._load()

    def _load(self):
        """Disk'ten adaptasyonları yükle."""
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.overrides = data.get("overrides", {})
            self.last_eval_trade_count = data.get("last_eval_trade_count", 0)
            self.adaptations = [Adaptation(**a) for a in data.get("adaptations", [])]
            log.info(f"Loaded {len(self.overrides)} adaptive overrides")
        except Exception as e:
            log.error(f"Adaptive config load failed: {e}")

    def _save(self):
        """Disk'e yaz."""
        data = {
            "overrides": self.overrides,
            "last_eval_trade_count": self.last_eval_trade_count,
            "adaptations": [asdict(a) for a in self.adaptations],
        }
        self.state_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def get(self, param: str, default=None):
        """Override varsa onu, yoksa base config'i döndür."""
        if param in self.overrides:
            return self.overrides[param]

        # Base config'ten ara (iç içe key'lere de bak)
        for section in ("risk", "structure", "fibonacci"):
            if section in self.base and param in self.base[section]:
                return self.base[section][param]
        return default

    def should_evaluate(self) -> bool:
        """Yeterli yeni trade oldu mu, yeniden değerlendirme zamanı mı?"""
        current_count = len(self.memory.journal.all_closed())
        return (current_count - self.last_eval_trade_count) >= self.interval

    def evaluate_and_adapt(self) -> List[Adaptation]:
        """
        Pattern'leri analiz edip adaptasyonları uygula.
        Her çağrıda değişen parametreleri döndürür.
        """
        if not self.should_evaluate():
            return []

        new_adaptations = []
        patterns = self.memory.analyze_patterns()

        for p in patterns:
            if p.recent_frequency < self.ADAPTATION_TRIGGER_THRESHOLD:
                continue
            if p.tag not in self.RULES:
                continue

            rule = self.RULES[p.tag]
            param = rule["param"]
            now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

            # Boolean toggle
            if rule.get("bool"):
                before = self.overrides.get(param, False)
                if before is True:
                    continue  # zaten açık
                self.overrides[param] = True
                adapt = Adaptation(
                    param=param, before=0, current=1, delta=1,
                    source_pattern=p.tag, severity=p.severity,
                    applied_at=now, win_rate_before=p.win_rate_when_present,
                )
                self.adaptations.append(adapt)
                new_adaptations.append(adapt)
                log.info(f"🔧 ADAPTATION: {param} = True (source: {p.tag})")
                continue

            # Numeric delta
            delta = rule["delta"]
            mn, mx = rule.get("min", -999), rule.get("max", 999)

            current_value = self.get(param)
            if current_value is None:
                continue

            new_value = max(mn, min(mx, current_value + delta))
            if new_value == current_value:
                continue

            self.overrides[param] = new_value
            adapt = Adaptation(
                param=param,
                before=float(current_value),
                current=float(new_value),
                delta=float(delta),
                source_pattern=p.tag,
                severity=p.severity,
                applied_at=now,
                win_rate_before=p.win_rate_when_present,
            )
            self.adaptations.append(adapt)
            new_adaptations.append(adapt)
            log.info(
                f"🔧 ADAPTATION: {param} {current_value} → {new_value} "
                f"(source: {p.tag}, recent {p.recent_frequency}x)"
            )

        self.last_eval_trade_count = len(self.memory.journal.all_closed())
        self._save()
        return new_adaptations

    def summary(self) -> str:
        """Mevcut adaptasyonların özeti."""
        if not self.overrides:
            return "Henüz adaptasyon yok — bot default parametrelerle çalışıyor."

        lines = ["# 🔧 Active Adaptations", ""]
        for param, value in self.overrides.items():
            # En son bu param için uygulanan adaptasyonu bul
            latest = next(
                (a for a in reversed(self.adaptations) if a.param == param),
                None
            )
            if latest:
                lines.append(
                    f"- **{param}** = `{value}` "
                    f"(was `{latest.before}`, source: `{latest.source_pattern}`)"
                )
            else:
                lines.append(f"- **{param}** = `{value}`")
        return "\n".join(lines)
