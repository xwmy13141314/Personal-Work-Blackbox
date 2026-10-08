import sys
from types import SimpleNamespace

import pytest

from src.ui.web_api import BlackboxAPI


@pytest.mark.parametrize('failing', ['input', 'screen'])
def test_permission_probe_failure_does_not_clear_other_permission(monkeypatch, failing):
    def failure():
        raise RuntimeError('probe unavailable')

    monkeypatch.setattr('platform.system', lambda: 'Darwin')
    monkeypatch.setitem(sys.modules, 'ApplicationServices', SimpleNamespace(AXIsProcessTrusted=lambda: True))
    monkeypatch.setitem(sys.modules, 'Quartz', SimpleNamespace(
        CGPreflightListenEventAccess=failure if failing == 'input' else lambda: True,
        CGPreflightScreenCaptureAccess=failure if failing == 'screen' else lambda: True,
    ))
    api = BlackboxAPI.__new__(BlackboxAPI)
    api._engine = SimpleNamespace(_keyboard_hook=None)
    result = api.check_permissions()
    assert result['accessibility_granted'] is True
    assert result['input_monitoring_granted'] is (failing != 'input')
    assert result['screen_recording_granted'] is (failing != 'screen')
