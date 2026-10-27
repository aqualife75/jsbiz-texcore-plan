# -*- coding: utf-8 -*-
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "texcore-plan"
SKILL = PLUGIN / "skills" / "texcore-plan"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))


@pytest.fixture
def out_dir(request):
    """테스트별 격리 출력 폴더. Dropbox 폴더 안은 동기화 잠금이 나므로 기본은 시스템 임시 폴더."""
    base = Path(os.environ.get("TEXCORE_TEST_OUT") or Path(tempfile.gettempdir()) / "texcore_plan_tests")
    d = base / request.node.name
    for _ in range(5):
        shutil.rmtree(d, ignore_errors=True)
        if not d.exists():
            break
        time.sleep(0.3)
    d.mkdir(parents=True, exist_ok=True)
    return d


@pytest.fixture
def root():
    return ROOT


@pytest.fixture
def skill_dir():
    return SKILL
