"""Stand-ins for the parts of Enigma2 the tuner uses, so its logic runs on a PC."""
import sys
import types

PENDING = []          # timers due to fire, run by run() in time order
NOW = [0]


class Signal:
    def __init__(self):
        self.fns = []

    def get(self):
        return self.fns

    def __call__(self):
        for f in list(self.fns):
            f()


class eTimer:
    def __init__(self):
        self.callback = Signal()
        self.active = False

    def start(self, ms, single=True):
        self.active, self.due = True, NOW[0] + ms
        if self not in PENDING:
            PENDING.append(self)

    def stop(self):
        self.active = False


def run():
    while PENDING:
        PENDING.sort(key=lambda t: t.due)
        t = PENDING.pop(0)
        NOW[0] = max(NOW[0], t.due)
        if t.active:
            t.active = False
            t.callback()


class eDVBFrontendParametersSatellite:
    Polarisation_Horizontal, Polarisation_Vertical = 0, 1
    System_DVB_S, System_DVB_S2 = 0, 1


# Which symbol rate "has a signal" for the next scans, and what it carries.
WORLD = {"sr": 2000, "refs": ["1:0:2:2:1:FF01:C02B2E:0:0:0:", "1:0:1:1:1:FF01:C02B2E:0:0:0:"], "start": 0}
SCANS = []


class eComponentScan:
    def __init__(self):
        self.statusChanged, self.newService = Signal(), Signal()
        self.tp, self.done, self.last = None, False, ""

    def addInitial(self, p):
        self.tp = p

    def start(self, feid, flags):
        SCANS.append((feid, flags, self.tp))
        if WORLD["start"] < 0:
            return -1
        t = eTimer()
        t.callback.get().append(self._finish)
        t.start(0)
        self._t = t
        return 0

    def _finish(self):
        if self.tp.symbol_rate == WORLD["sr"] * 1000:
            for r in WORLD["refs"]:
                self.last = r
                self.newService()
        self.done = True
        self.statusChanged()

    def isDone(self):
        return self.done

    def getLastServiceRef(self):
        return self.last

    def getLastServiceName(self):
        return "test"


class eServiceReference(str):
    pass


mod = types.ModuleType("enigma")
for name in ("eTimer", "eDVBFrontendParametersSatellite", "eComponentScan", "eServiceReference"):
    setattr(mod, name, globals()[name])
sys.modules["enigma"] = mod
