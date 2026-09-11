"""Suite genelinde gecerli test hijyeni.

create_app her cagrida SessionLogger.start() uzerinden Ollama'ya
GET /api/tags atar (3 sn timeout; Ollama kapaliysa Windows'ta TCP connect
~4 sn surer) ve psutil ile TUM sureclerin bellegini tarar (~1.3 sn). Testte
ikisi de anlamsiz: 30 create_app cagrisi x ~5 sn = 2 dakikalik bekleme.
Burada ikisi de stub'lanir; URETIM DAVRANISI DEGISMEZ — yalniz test surecinde
monkeypatch ile ezilir. Log dosyasi yine yazilir ("Model bilgisi alinamadi"
satiriyla), yani SessionLogger'in yazma yolu test disina cikmaz.
"""

from __future__ import annotations

import pytest

import session_logger


@pytest.fixture(autouse=True)
def _ag_ve_psutil_probu_kapali(monkeypatch):
    """Ollama /api/tags probu ve psutil surec taramasi testte yapilmaz."""
    monkeypatch.setattr(session_logger.SessionLogger, "_fetch_model_info",
                        lambda self: None)
    monkeypatch.setattr(session_logger, "ram_usage", lambda: None)
