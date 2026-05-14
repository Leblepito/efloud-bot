"""Efloud overseer agent — bot davranış izleme + raporlama.

Mevcut ops/alerter/ ve ops/daily_report/ paketlerini genişletir,
paralel sistem değil. Hetzner sidecar olarak deploy edilir
(docker-compose.prod.yml içinde 'overseer' service).
"""
__version__ = "0.1.0"
