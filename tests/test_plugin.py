"""Run with: python3 -m pytest tests (or python3 tests/test_plugin.py)."""
import os
import sys
import time

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



class FakeFE:
    def getAll(self, original):
        assert original is False
        return {"symbol_rate": 1000000, "system": 1, "modulation": 1, "fec_inner": 3}


class FakeInfo:
    def getInfo(self, what):
        return {"w": 1920, "h": 1080}[what]


class FakeService:
    def frontendInfo(self):
        return FakeFE()

    def info(self):
        return FakeInfo()


def test_live_tech_line():
    import types
    fe.mod.iServiceInformation = types.SimpleNamespace(sVideoWidth="w", sVideoHeight="h")
    s = Session()
    s.nav.getCurrentService = lambda: FakeService()
    p = tuning.live(s)                         # no Tools.Transponder here: fallbacks
    assert p == {"sr_ks": 1000, "system": "DVB-S2", "modulation": "QPSK", "fec": "3/4", "size": (1920, 1080)}
    assert tuning.tech_text(1312, p) == "1312 MHz   1000 kS/s   DVB-S2 QPSK   FEC 3/4   1920x1080"
    assert tuning.tech_text(1312, {}, 2000) == "1312 MHz   2000 kS/s"


class EchoFE:
    """The H11S's driver: hands back what was asked for, FEC still auto."""
    def getAll(self, original):
        return {"symbol_rate": 1000000, "system": 1, "modulation": 1, "fec_inner": 0}


def test_echoing_driver_shows_no_mode():
    import types
    fe.mod.iServiceInformation = types.SimpleNamespace(sVideoWidth="w", sVideoHeight="h")
    svc = FakeService()
    svc.frontendInfo = lambda: EchoFE()
    s = Session()
    s.nav.getCurrentService = lambda: svc
    p = tuning.live(s)
    assert p == {"sr_ks": 1000, "size": (1920, 1080)}
    assert tuning.tech_text(1312, p) == "1312 MHz   1000 kS/s   1920x1080"



def test_title_text():
    e = {"call": "GB3EN", "town": "North London", "km": 25.4, "approx": False}
    assert tuning.title_text(e, {}) == ("GB3EN", "North London   25 km")
    assert tuning.title_text(e, {"name": "gb3en"}) == ("GB3EN", "North London   25 km")
    assert tuning.title_text(e, {"name": "GB3EN Test Card"}) == ("GB3EN Test Card", "North London   25 km")
    assert tuning.clean_name("\x86GB3EN\x87 ") == "GB3EN"
    assert tuning.title_text(e, {"name": "G8YTZ Lynx-Tx"}) == ("G8YTZ Lynx-Tx", "GB3EN   North London   25 km")


API_SAMPLE = {
    "repeaters": [
        {"active": 1, "stream_listed": "1", "stream_title": "GB3OO Folkestone", "stream_output_url": "gb3oo",
         "stream_type_repeater": "1"},
        {"active": 1, "stream_listed": "1", "stream_title": "GB3HV Alton", "stream_output_url": "gb3hv-hd",
         "stream_type_repeater": "1"},
        {"active": 0, "stream_listed": "1", "stream_title": "GB3TV", "stream_output_url": "gb3tv"},
        {"active": 1, "stream_listed": "0", "stream_title": "Hidden", "stream_output_url": "hidden"},
    ],
    "members": [
        {"active": 1, "stream_listed": "1", "stream_title": "G8YTZ shack", "stream_output_url": "g8ytz"},
        {"active": 1, "stream_listed": "1", "stream_title": "Nasty", "stream_output_url": "x\" :evil"},
    ],
    "count": 6,
}


def test_streams_parse_and_match():
    from LynxRepeaters import streams
    got = streams.parse(API_SAMPLE)
    assert [g["key"] for g in got] == ["gb3hv-hd", "gb3oo", "g8ytz"]      # repeaters first; bad names dropped
    assert got[1]["url"] == "rtmp://rtmp.batc.org.uk/live/gb3oo"
    assert streams.for_call(got, "GB3OO")["key"] == "gb3oo"
    assert streams.for_call(got, "GB3HV")["key"] == "gb3hv-hd"
    assert streams.for_call(got, "GB3H") is None and streams.for_call(got, "GB3TV") is None
    assert streams.service_ref(got[1]) == "4097:0:1:0:0:0:0:0:0:0:rtmp%3a//rtmp.batc.org.uk/live/gb3oo:GB3OO Folkestone"


def test_streams_bouquet_files():
    import tempfile
    from LynxRepeaters import streams
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "bouquets.tv"), "w") as f:
        f.write('#NAME User - bouquets (TV)\n#SERVICE 1:7:1:0:0:0:0:0:0:0:FROM BOUQUET "userbouquet.favourites.tv" ORDER BY bouquet\n')
    got = streams.parse(API_SAMPLE)
    assert streams.write_bouquet(got, d) is True
    assert streams.write_bouquet(got, d) is False                        # nothing changed second time
    tv = open(os.path.join(d, "bouquets.tv")).read()
    assert tv.count(streams.BOUQUET) == 1 and "favourites" in tv
    b = open(os.path.join(d, streams.BOUQUET)).read().splitlines()
    assert b[0] == "#NAME BATC Live" and b[1].startswith("#SERVICE 4097:") and len(b) == 7
    path = os.path.join(d, "cache.json")
    streams.save(got, path, now=1234)
    assert streams.load(path) == (got, 1234)
    assert streams.load(os.path.join(d, "missing.json")) == ([], 0)


def test_sync_updates_and_keeps_list_on_error(monkeypatch=None):
    import tempfile
    from LynxRepeaters import streams, sync
    d = tempfile.mkdtemp()
    streams.CACHE, streams.BOUQUET_DIR = os.path.join(d, "c.json"), d
    fe.mod.eDVBDB = type("DB", (), {"getInstance": staticmethod(lambda: type("I", (), {"reloadBouquets": lambda self: None})())})
    sync.StreamSync.instance = None
    s = sync.get()
    assert s.stale() and s.streams == []
    calls = []
    s.listeners.append(lambda: calls.append(1))
    streams.fetch = lambda timeout=15: streams.parse(API_SAMPLE)
    s.refresh()
    s._worker.join()
    fe.run()
    assert len(s.streams) == 3 and not s.stale() and calls == [1]
    def boom(timeout=15):
        raise IOError("no network")
    streams.fetch = boom
    s.refresh()
    s._worker.join()
    fe.run()
    assert len(s.streams) == 3 and calls == [1]                           # last list kept
    s.fetched = time.time() + 5 * 365 * 86400                             # clock gone back to 2021
    assert s.stale()


def test_stream_player_choice():
    import tempfile
    from LynxRepeaters import streams
    d = tempfile.mkdtemp()
    streams.SERVICEAPP, streams.EXTEPLAYER3 = os.path.join(d, "ServiceApp"), os.path.join(d, "exteplayer3")
    streams.GSTPLAYER = os.path.join(d, "gstplayer")
    assert streams.player_chain("auto") == [4097]              # nothing installed
    os.mkdir(streams.SERVICEAPP)
    open(streams.EXTEPLAYER3, "w").close()
    open(streams.GSTPLAYER, "w").close()
    assert streams.player_chain("auto") == [5001, 5002]        # gstplayer then exteplayer3: Justin, 20 Oct
    assert streams.player_type("auto") == 5001
    os.remove(streams.GSTPLAYER)
    assert streams.player_chain("auto") == [5002]
    open(streams.GSTPLAYER, "w").close()
    assert streams.player_chain("exteplayer3") == [5002]
    assert streams.player_type("builtin") == 4097 and streams.player_type("gstplayer") == 5001
    s = {"name": "GB3HV", "url": "rtmp://rtmp.batc.org.uk/live/gb3hv"}
    assert streams.service_ref(s, 5002).startswith("5002:0:1:0:0:0:0:0:0:0:rtmp%3a//")
    assert "#SERVICE 5002:" in streams.bouquet_text([s], 5002)


def test_fix_clock_only_when_wrong():
    from LynxRepeaters import sync
    calls = []
    sync.subprocess = type("SP", (), {"call": staticmethod(lambda args: calls.append(args) or 0)})
    sync.NTPDATE = (sys.executable,)                      # any file that exists
    assert sync.fix_clock() is False and calls == []      # this PC's clock is fine
    old = sync.SANE_YEAR
    sync.SANE_YEAR = 9999
    assert sync.fix_clock() is True and calls[0][1:] == ["-b", "pool.ntp.org"]
    sync.SANE_YEAR = old


def test_stream_only_repeaters():
    from LynxRepeaters import streams
    got = streams.parse({"r": [
        {"active": 1, "stream_listed": "1", "stream_title": "DB0OZ Bremen", "stream_output_url": "db0oz", "stream_type_repeater": "1"},
        {"active": 1, "stream_listed": "1", "stream_title": "GB3OO Folkestone", "stream_output_url": "gb3oo", "stream_type_repeater": "1"},
        {"active": 1, "stream_listed": "1", "stream_title": "Oscar 100 net", "stream_output_url": "oscar100net", "stream_type_repeater": "1"},
        {"active": 1, "stream_listed": "1", "stream_title": "G8YTZ shack", "stream_output_url": "g8ytz"}]})
    only = streams.stream_only(got, ["GB3OO", "GB3EN"])
    assert [(x["call"], x["town"]) for x in only] == [("DB0OZ", "Bremen"), ("Oscar 100 net", "")]
    assert only[0]["stream"]["key"] == "db0oz"


def test_match_playing():
    rows = repeaters.rows(DATA, show_off=True)
    for e in rows:
        e["stream"] = {"key": "gb3hv", "name": "GB3HV"} if e["call"] == "GB3HV" else None
    ref = "1:0:1:1:1:FF01:C02B2E:0:0:0:"                                      # 1304 MHz: GB3KM, GB3OO, GB3SQ
    oo = tuning.match_playing(rows, ref, "GB3OO Folkestone")
    assert oo["call"] == "GB3OO" and oo["locked_sr_ks"] == 2000
    assert tuning.match_playing(rows, ref, "Test card")["call"] == rows[[e["box_khz"] for e in rows].index(11054000)]["call"]
    hv = tuning.match_playing(rows, "5001:0:1:0:0:0:0:0:0:0:rtmp%3a//rtmp.batc.org.uk/live/gb3hv:GB3HV Alton")
    assert hv["call"] == "GB3HV" and hv["via_stream"]
    assert tuning.match_playing(rows, "1:0:19:283D:3FB:1:C00000:0:0:0:") is None   # BBC One HD
    assert tuning.match_playing(rows, "") is None

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
