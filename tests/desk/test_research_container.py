"""Advisory research cycle — konteyner runner'ının güvenlik sözleşmesi.

Bu döngü TradingAgents'i çalıştırır ve o framework güvenilmeyen haber/sosyal medya
metnini LLM'e verir. Bu yüzden runner'ın sınırları test edilir:

  * repo konteynere READ-ONLY mount edilir (LLM tarafından tetiklenen bir yazma
    motor kodunu değiştirmemeli),
  * LLM anahtarı yalnız `.env.research`'tan gelir — `.env.production` (Binance
    API anahtarları) ASLA konteynere verilmez,
  * zamanlayıcı 5 saatlik kadansı korur (monotonic timer: `Persistent=` yalnız
    OnCalendar timer'larında etkilidir, burada no-op olduğu için kullanılmaz),
  * servis durduğunda/zaman aşımına uğradığında konteyner temizlenir (systemd yalnız
    `docker run` istemcisini öldürür; konteyner LLM harcamaya devam edebilirdi),
  * örnek env dosyası Binance sırrı içermez.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "deploy" / "research-cycle.sh"
SERVICE = ROOT / "deploy" / "research-cycle.service"
TIMER = ROOT / "deploy" / "research-cycle.timer"
DOCKERFILE = ROOT / "deploy" / "Dockerfile.research"
ENV_EXAMPLE = ROOT / "deploy" / ".env.research.example"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_runner_files_exist():
    for p in (WRAPPER, SERVICE, TIMER, DOCKERFILE, ENV_EXAMPLE):
        assert p.exists(), f"eksik: {p.relative_to(ROOT)}"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash yok (Windows test makinesi)")
def test_wrapper_is_valid_posix_shell():
    out = subprocess.run(["bash", "-n", str(WRAPPER)], capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr


def test_repo_is_mounted_read_only_and_only_desk_is_writable():
    text = _read(WRAPPER)
    assert "dst=/app,readonly" in text, "repo mount'u read-only olmalı"
    assert "dst=/app/desk" in text, "desk/ yazılabilir mount edilmeli"


def test_llm_key_comes_only_from_the_research_env_file():
    text = _read(WRAPPER)
    assert '.env.research' in text, "varsayılan env dosyası .env.research olmalı"
    # production env dosyası açıkça reddedilir
    assert "production" in text and "FATAL" in text, "production env dosyası reddedilmeli"


def test_wrapper_never_defaults_to_a_production_env_file():
    text = _read(WRAPPER)
    for line in text.splitlines():
        if "RESEARCH_ENV_FILE:=" in line or "--env-file" in line:
            assert ".env.production" not in line, f"production env sızıntısı: {line.strip()}"


def test_runner_does_not_print_key_values():
    """Anahtar yalnız 'boş mu' kontrolünden geçer; değeri asla basılmaz."""
    text = _read(WRAPPER)
    assert '-q' in text, "anahtar varlığı grep -q ile (değer basmadan) kontrol edilmeli"
    assert "cat \"$ENV_FILE\"" not in text and "cat $ENV_FILE" not in text


def test_env_example_has_the_llm_key_and_no_binance_secrets():
    text = _read(ENV_EXAMPLE)
    assert "OPENROUTER_API_KEY" in text
    for forbidden in ("BINANCE_API_KEY", "BINANCE_API_SECRET", "DASHBOARD_PASSWORD", "SESSION_SECRET"):
        assert forbidden not in text, f"{forbidden} research env şablonunda olmamalı"


def test_timer_keeps_the_five_hour_cadence():
    text = _read(TIMER)
    assert "OnBootSec=5min" in text
    assert "OnUnitActiveSec=5h" in text
    # Persistent= only affects OnCalendar= timers; on a monotonic timer it is a no-op
    # that falsely promises catch-up runs. OnBootSec covers reboots instead.
    directives = [ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    assert not any(d.startswith("Persistent=") for d in directives)
    assert "Unit=research-cycle.service" in text


def test_service_runs_the_wrapper_as_a_oneshot():
    text = _read(SERVICE)
    assert "Type=oneshot" in text
    assert "ExecStart=/opt/efloud-bot/deploy/research-cycle.sh" in text
    assert "TimeoutStartSec=" in text, "LLM koşusu için üst sınır şart"


def test_service_removes_the_container_when_it_stops_or_times_out():
    """systemd kills only the docker CLI on timeout; without this the container keeps
    running (and spending LLM credit) and the next run hits a --name conflict."""
    text = _read(SERVICE)
    assert "ExecStopPost=-/usr/bin/docker rm -f efloud-research-run" in text


def test_image_is_built_on_the_same_python_as_ci():
    text = _read(DOCKERFILE)
    assert "FROM python:3.11-slim" in text, "CI/bot ile aynı Python sürümü kullanılmalı"
    assert "requirements-research.txt" in text, "değişken bağımlılıklar tek dosyadan gelmeli"
