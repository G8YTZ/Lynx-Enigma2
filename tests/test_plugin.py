"""Run with: python3 -m pytest tests (or python3 tests/test_plugin.py)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.join(HERE, "..", "plugin")]

import fake_enigma as fe                        # noqa: E402  (installs "enigma")
from LynxRepeaters import repeaters, tuning     # noqa: E402

DATA = repeaters.load()


def test_locator():
    assert repeaters.valid_locator("jo01aj") and repeaters.valid_locator("IO92")
    assert not repeaters.valid_locator("JO1") and not repeaters.valid_locator("ZZ01AA")
    assert not repeaters.valid_locator("JO01AZ")


def test_rows_from_petts_wood():
    home = repeaters.locator_to_latlon("JO01AJ")
    rows = repeaters.rows(DATA, home)
    calls = [r["call"] for r in rows]
    assert calls[0] == "GB3EN"                 # North London is nearest on air
    assert "GB3JV" not in calls                # off air hidden by default
    assert "GB3FT" not in calls                # 500 kS/s, below the tuner
    assert all(r["km"] is not None for r in rows)
    assert rows == sorted(rows, key=lambda r: r["km"])
    oo = next(r for r in rows if r["call"] == "GB3OO")
    assert oo["box_khz"] == 11054000 and 70 < oo["km"] < 100 and oo["note"] == ""
    assert next(r for r in rows if r["call"] == "GB3ET")["approx"]
    tg = next(r for r in rows if r["call"] == "GB3TG")
    assert tg["note"] == "Needs an LNB with a 9 GHz oscillator"
    assert "GB3JV" in [r["call"] for r in repeaters.rows(DATA, home, show_off=True)]


def test_rows_without_locator():
    rows = repeaters.rows(DATA)
    assert [r["call"] for r in rows] == sorted(r["call"] for r in rows)


def test_pick_service():
    assert tuning.pick_service(["1:0:2:2:1:1:1:0:0:0:", "1:0:19:3:1:1:1:0:0:0:"]).startswith("1:0:19")
    assert tuning.pick_service(["1:0:2:2:1:1:1:0:0:0:"]).startswith("1:0:2")
    assert tuning.pick_service([]) is None


def test_symbol_rates():
    oo = {"output": {"sr_ks": 2000}}
    assert tuning.symbol_rates(oo) == [2000]
    assert tuning.symbol_rates(oo, hunt=True)[0] == 2000 and len(tuning.symbol_rates(oo, hunt=True)) == 6
    assert tuning.symbol_rates({"output": {"sr_ks": None}}) == list(repeaters.COMMON_SR_KS)


class Nav:
    def __init__(self):
        self.playing, self.stopped = None, 0

    def stopService(self):
        self.stopped += 1

    def playService(self, ref):
        self.playing = ref


class Session:
    def __init__(self):
        self.nav = Nav()


def _tune(call, hunt=False, supply="13"):
    s, log, result = Session(), [], []
    t = tuning.RepeaterTuner(s, log.append, lambda *a: result.append(a))
    e = next(r for r in repeaters.rows(DATA, show_off=True) if r["call"] == call)
    fe.SCANS.clear()
    t.tune(e, supply, hunt)
    fe.run()
    return s, log, result, t


def test_tune_gb3oo():
    fe.WORLD.update(sr=2000, start=0)
    s, log, result, t = _tune("GB3OO", supply="18")
    assert result == [("1:0:1:1:1:FF01:C02B2E:0:0:0:", 2000, None)]   # TV, not radio
    assert s.nav.playing == "1:0:1:1:1:FF01:C02B2E:0:0:0:" and s.nav.stopped == 1
    p = fe.SCANS[0][2]
    assert p.frequency == 11054000 and p.orbital_position == 192 and p.polarisation == 0
    assert p.system == 1 and not t.busy


def test_hunt_unknown_rate():
    fe.WORLD.update(sr=4000, start=0)
    s, log, result, t = _tune("GB3DO")                 # no symbol rate listed
    assert result[0][1] == 4000
    assert [p.symbol_rate for _, _, p in fe.SCANS] == [2000000, 1500000, 1000000, 4000000]
    assert len(log) == 4


def test_no_signal():
    fe.WORLD.update(sr=9999, start=0)
    s, log, result, t = _tune("GB3OO")
    assert result == [(None, None, "No signal at 2000 kS/s")] and s.nav.playing is None


def test_tuner_busy():
    fe.WORLD.update(sr=2000, start=-1)
    s, log, result, t = _tune("GB3OO")
    assert result[0][0] is None and "busy" in result[0][2]
    fe.WORLD["start"] = 0


def test_dvb_s_and_9cm():
    fe.WORLD.update(sr=2000, start=0)
    _tune("GB3ET")
    assert fe.SCANS[0][2].system == 0                   # DVB-S
    fe.WORLD.update(sr=2000)
    s, log, result, t = _tune("GB3JV")                   # 3404 MHz via a 5150 LNB
    assert fe.SCANS[0][2].frequency == (5150 - 3404 + 9750) * 1000


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
