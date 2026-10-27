# -*- coding: utf-8 -*-
"""texcore-plan 워크스페이스 상태(state.json). seed-ir의 state.py를 단계 이름만 바꿔 재사용."""
from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path

PHASES = ["1_facts", "2_write", "3_review", "4_research", "5_design", "6_final"]

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class State:
    def __init__(self, ws: Path, data: dict):
        self.ws = Path(ws); self.data = data

    @classmethod
    def new(cls, ws: Path, team: str, input_dir: str, edu_type: str = "미정") -> "State":
        data = {
            "team": team, "input_dir": input_dir, "edu_type": edu_type, "created": _now(), "updated": _now(),
            "phases": {p: {"status": "pending", "started": None, "finished": None, "note": ""} for p in PHASES},
            "gates": {}, "approvals": {"accept_risk": False, "outline_confirmed": False, "questions_sent": False}, "log": [],
        }
        st = cls(ws, data); st.save(); return st

    @classmethod
    def load(cls, ws: Path) -> "State":
        p = Path(ws) / "state.json"
        if not p.exists():
            raise FileNotFoundError(f"state.json 없음: {p} — 먼저 `harness.py init`을 실행하세요")
        return cls(ws, json.loads(p.read_text(encoding="utf-8")))

    def save(self) -> None:
        self.data["updated"] = _now()
        (self.ws / "state.json").write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_phase(self, name: str, status: str, note: str = "") -> None:
        ph = self.data["phases"][name]
        if status == "running": ph["started"] = _now()
        if status in ("done", "failed"): ph["finished"] = _now()
        ph["status"] = status; ph["note"] = note
        self.data["log"].append({"t": _now(), "phase": name, "status": status, "note": note})

    def record_gate(self, phase: str, ok: bool, reasons: list[str]) -> None:
        self.data["gates"][str(phase)] = {"ok": ok, "reasons": reasons, "t": _now()}

    def approve(self, key: str) -> None:
        self.data["approvals"][key] = True
