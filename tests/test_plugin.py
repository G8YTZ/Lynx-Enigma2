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
    assert [g["key"] for g in got] == ["gb3hv-hd", "gb3oo", "g8ytz", "gb3tv"]   # repeaters first; bad names dropped
    assert [g["key"] for g in streams.live_only(got)] == ["gb3hv-hd", "gb3oo", "g8ytz"]
    assert "gb3tv" not in streams.bouquet_text(got)                     # offline: not in BATC Live
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
    assert len(s.streams) == 4 and len(streams.live_only(s.streams)) == 3 and not s.stale() and calls == [1]
    def boom(timeout=15):
        raise IOError("no network")
    streams.fetch = boom
    s.refresh()
    s._worker.join()
    fe.run()
    assert len(s.streams) == 4 and calls == [1]                           # last list kept
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
    got.append({"name": "G4FRE Orpington", "key": "g4fre", "url": "x", "repeater": False, "live": False})
    every = streams.stream_only(got, ["GB3OO", "GB3EN", "g8ytz"], everything=True)
    assert [x["call"] for x in every] == ["DB0OZ", "Oscar 100 net", "G4FRE"]     # live first, then offline
    assert [x["call"] for x in streams.stream_only([dict(got[0], live=False)], [])] == []


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


def test_no_tuner_set_up():
    import types
    nm = types.SimpleNamespace(nim_slots=[types.SimpleNamespace(slot=0, isCompatible=lambda t: True)],
                               getSatListForNim=lambda slot: [])          # tuner A "not configured"
    comps = types.ModuleType("Components")
    nimmod = types.ModuleType("Components.NimManager")
    nimmod.nimmanager = nm
    sys.modules["Components"], sys.modules["Components.NimManager"] = comps, nimmod
    try:
        assert tuning.find_tuner() is None
        s, log, result, t = _tune("GB3OO")
        assert result == [(None, None, tuning.NO_TUNER)] and s.nav.stopped == 0 and fe.SCANS == []
        nm.getSatListForNim = lambda slot: [(192, "Astra", 0)]
        assert tuning.find_tuner() == 0
    finally:
        del sys.modules["Components"], sys.modules["Components.NimManager"]


def test_waits_for_stream_to_let_go():
    fe.WORLD.update(sr=2000, start=0)
    killed = []
    real_call = tuning.subprocess.call
    tuning.subprocess.call = lambda args, **kw: killed.append(args) or 1   # nothing left running
    s, log, result = Session(), [], []

    class Ref(str):
        def toString(self):
            return str(self)
    s.nav.getCurrentlyPlayingServiceReference = lambda: Ref("5001:0:1:0:0:0:0:0:0:0:rtmp%3a//rtmp.batc.org.uk/live/gb3en:GB3EN")
    t = tuning.RepeaterTuner(s, log.append, lambda *a: result.append(a))
    e = next(r for r in repeaters.rows(DATA) if r["call"] == "GB3OO")
    fe.SCANS.clear()
    t.tune(e)
    assert fe.SCANS == [] and "letting the stream go" in log[0]          # nothing tuned yet
    fe.run()
    assert len(fe.SCANS) == 1 and result[0][0]                             # then it tunes and plays
    assert ["killall", "gstplayer2"] in killed
    tuning.subprocess.call = real_call


def test_rs6060_decode_and_find():
    import tempfile
    from LynxRepeaters import rs6060
    # 0x19 = 0x39 and 0x76 = 0x30 in the dump taken with Lynx-Tx on 8PSK 3/4, pilots, 0.35.
    assert rs6060.decode_pls(0x39, 0x30) == {"system": "DVB-S2", "modulation": "8PSK", "fec": "3/4",
                                             "pilots": True, "short_frames": False, "rolloff": "0.35"}
    apsk = rs6060.decode_pls(0x4D, 0x32)                                        # live, 01:05
    assert (apsk["modulation"], apsk["fec"], apsk["pilots"], apsk["rolloff"]) == ("16APSK", "3/4", True, "0.20")
    qpsk = rs6060.decode_pls((7 << 2) | 1, 0x32)
    assert (qpsk["modulation"], qpsk["fec"], qpsk["rolloff"]) == ("QPSK", "3/4", "0.20")
    assert rs6060.decode_pls(0x00) == {} and rs6060.decode_pls(0x85) == {}      # dummy frame, DVB-S2X
    assert rs6060.decode_s(2 << 5) == {"system": "DVB-S", "modulation": "QPSK", "fec": "3/4"}
    assert rs6060.decode_s(7 << 5) == {}
    d = tempfile.mkdtemp()
    for e, name in (("i2c-2", "hi-i2c"), ("2-006b", "rs6060")):
        os.mkdir(os.path.join(d, e))
        open(os.path.join(d, e, "name"), "w").write(name + "\n")
    assert rs6060.find(d) == (2, 0x6B)
    assert rs6060.find(os.path.join(d, "nothing")) is None


def test_bar_uses_demodulator_when_driver_echoes():
    import types
    from LynxRepeaters import rs6060
    fe.mod.iServiceInformation = types.SimpleNamespace(sVideoWidth="w", sVideoHeight="h")
    svc = FakeService()
    svc.frontendInfo = lambda: EchoFE()
    s = Session()
    s.nav.getCurrentService = lambda: svc
    real = rs6060.modcod
    rs6060.modcod = lambda: rs6060.decode_pls(0x39, 0x30)
    try:
        p = tuning.live(s)
        assert tuning.tech_text(1304, p) == "1304 MHz   1000 kS/s   DVB-S2 8PSK   FEC 3/4   pilots   roll-off 0.35   1920x1080"
    finally:
        rs6060.modcod = real


def test_level_from_strength():
    from LynxRepeaters import rs6060
    got = [round(rs6060.level_dbm(p * 656)) for p in (20, 32, 56, 72, 85)]
    assert got == [-77, -73, -65, -58, -49]          # Justin's -40 to 0 dB steps, 21 Oct 2026
    assert rs6060.level_dbm(0) is None


def test_magic_eye():
    from LynxRepeaters import eye
    assert round(eye.margin_db(9.54, "8PSK", "2/3"), 2) == 2.92
    assert eye.margin_db(9.54, None, None) is None
    assert round(eye.margin_db(9.0, "QPSK", "3/4", "DVB-S"), 1) == 2.1
    assert eye.closure(False, 19.0, 11.0) == 0.0                 # no lock: wide open, dark
    assert eye.closure(True, 19.0, 12.0) == 1.0                  # plenty in hand: closed
    assert eye.closure(True, 10.0, None) == 0.5                  # MODCOD unknown: SNR alone
    # Justin's sweep, 21 Oct 2026 (8PSK 2/3): it must open steadily as he
    # turns down, not sit closed until -30 dB as margin alone did.
    sweep = [eye.closure(True, snr, eye.margin_db(snr, "8PSK", "2/3"), dbm)
             for snr, dbm in ((19.03, -49), (19.03, -58), (19.03, -65), (17.55, -73), (9.03, -77))]
    assert sweep == sorted(sweep, reverse=True) and sweep[0] > 0.9 and 0.5 < sweep[3] < 0.7 and sweep[4] < 0.4
    assert eye.frame(0.0, True) == 0 and eye.frame(1.0, True) == eye.FRAMES - 1 and eye.frame(0.7, False) == "off"
    here = os.path.join(HERE, "..", "plugin", "LynxRepeaters", "eye")
    for folder in (here, os.path.join(here, "hd")):
        names = ["eye_%02d.png" % n for n in range(eye.FRAMES)] + ["eye_off.png"]
        assert all(os.path.exists(os.path.join(folder, n)) for n in names)

def test_manual_entry():
    e = repeaters.manual_entry(1249, 1500)
    assert e["call"] == "1249 MHz" and e["town"] == "Tuned by hand" and not e["preset"]
    assert e["box_khz"] == 10999000 and e["band"] == "23cm" and e["output"]["sr_ks"] == 1500
    assert tuning.symbol_rates(e) == [1500]
    p = repeaters.manual_entry(1312, None, " Lynx-Tx ")
    assert p["call"] == "Lynx-Tx" and p["preset"] and tuning.symbol_rates(p)[0] == 2000
    assert repeaters.manual_entry(1500)["band"] == "direct"           # any IF straight in
    assert repeaters.manual_entry(10400)["box_khz"] == (1400 + 9750) * 1000
    assert repeaters.manual_entry(800) is None                        # below the tuner
    assert repeaters.manual_entry(10400, lnb_osc={"3cm": 9750}) is None


def test_presets(tmp=None):
    import tempfile
    path = os.path.join(tmp or tempfile.mkdtemp(), "lynx_presets.json")
    assert repeaters.load_presets(path) == []
    a = {"name": "Lynx-Tx", "freq_mhz": 1312.0, "sr_ks": 1000}
    b = {"name": "Test", "freq_mhz": 1249.0, "sr_ks": None}
    ps = repeaters.put_preset(repeaters.put_preset([], a), b)
    ps = repeaters.put_preset(ps, dict(a, sr_ks=2000))               # same name: replaced in place
    assert [p["name"] for p in ps] == ["Lynx-Tx", "Test"] and ps[0]["sr_ks"] == 2000
    ps = repeaters.put_preset(ps, dict(b, name="Renamed"), replacing="test")
    assert [p["name"] for p in ps] == ["Lynx-Tx", "Renamed"]
    repeaters.save_presets(ps, path)
    assert repeaters.load_presets(path) == ps
    assert repeaters.drop_preset(ps, "lynx-tx") == ps[1:]
    with open(path, "w") as f:
        f.write('{"presets": [{"name": "", "freq_mhz": 1249}, {"name": "x", "freq_mhz": "y"}, {"oops": 1}]}')
    assert repeaters.load_presets(path) == []
    with open(path, "w") as f:
        f.write("not json")
    assert repeaters.load_presets(path) == []


def test_locator_as_typed():
    assert repeaters.clean_locator(" jo 01aj ") == "JO01AJ"
    assert repeaters.valid_locator("jo01 aj") and repeaters.valid_locator("Jo01Aj")
    assert repeaters.locator_to_latlon("jo01aj") == repeaters.locator_to_latlon("JO01AJ")


def test_stream_presets():
    import tempfile
    from LynxRepeaters import streams
    path = os.path.join(tempfile.mkdtemp(), "p.json")
    ps = repeaters.put_preset([], {"name": "G4FRE", "stream": "g4fre"})
    ps = repeaters.put_preset(ps, {"name": "Lynx-Tx", "freq_mhz": 1312.0, "sr_ks": 1000})
    repeaters.save_presets(ps, path)
    assert repeaters.load_presets(path) == ps
    assert repeaters._preset({"name": "x", "stream": "rtmp://evil host/x"}) is None
    live = [{"name": "G4FRE Orpington", "key": "G4FRE", "url": streams.RTMP % "G4FRE", "repeater": False}]
    s = streams.member_stream(live, "g4fre", "G4FRE")
    assert s["live"] and s["name"] == "G4FRE Orpington"
    s = streams.member_stream([], "g4fre", "Dave")
    assert not s["live"] and s["url"] == "rtmp://rtmp.batc.org.uk/live/g4fre" and s["name"] == "Dave"
    assert streams.member_stream([], "no spaces allowed") is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
