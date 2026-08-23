"""Flag definitions, alias generation, and sub-command pools for the command tree."""

from __future__ import annotations

from cruine.commands.model import Flag

__all__ = [
    "COMMON_FLAGS",
    "_CONSTELLATIONS",
    "_GREEK",
    "_LONG_FLAGS",
    "_NATO",
    "_PLANETS",
    "_SHORT_FLAGS",
    "_SOLAR",
    "_SUB_PAIRS",
    "_ZODIAC",
    "_aliases_for",
    "_f",
    "_mix",
]


def _f(
    short: str | None,
    long: str | None,
    help: str,
    action: str = "store",
    metavar: str | None = None,
) -> Flag:
    return Flag(short=short, long=long, help=help, action=action, metavar=metavar)


COMMON_FLAGS: tuple[Flag, ...] = (
    _f("-v", "--verbose", "enable verbose output", action="store_true"),
    _f("-q", "--quiet", "suppress non-critical output", action="store_true"),
    _f("-x", "--debug", "enable debug tracing", action="store_true"),
    _f("-d", "--dry-run", "preview without executing", action="store_true"),
    _f("-f", "--format", "output format", metavar="FMT"),
    _f("-o", "--output", "output location", metavar="PATH"),
    _f("-p", "--path", "target path", metavar="PATH"),
    _f("-n", "--name", "name override", metavar="NAME"),
    _f("-t", "--target", "target device or tree", metavar="TARGET"),
    _f("-m", "--mode", "execution mode", metavar="MODE"),
    _f("-c", "--config", "configuration file", metavar="FILE"),
    _f("-r", "--recipe", "recipe file (rc.json)", metavar="FILE"),
    _f("-j", "--jobs", "parallel build jobs", metavar="N"),
    _f("-l", "--list", "list items", action="store_true"),
    _f("-s", "--silent", "silent mode", action="store_true"),
    _f("-e", "--env", "environment override", metavar="KEY=VAL"),
)

_SHORT_FLAGS = (
    ("-a", "--advance", "advance the operation"),
    ("-b", "--batch", "run in batch mode"),
    ("-g", "--gauge", "gauge progress"),
    ("-h", "--hail", "hail the target"),
    ("-i", "--index", "index entries"),
    ("-k", "--kiosk", "enable kiosk mode"),
    ("-u", "--uprush", "uprush throughput"),
    ("-w", "--whirl", "whirl mode"),
    ("-y", "--yank", "yank the target"),
    ("-z", "--zest", "add zest"),
)

_LONG_FLAGS = (
    "--amber",
    "--cobalt",
    "--dune",
    "--ember",
    "--frost",
    "--grove",
    "--haven",
    "--ice",
    "--jade",
    "--kelp",
    "--lume",
    "--moss",
    "--nimbus",
    "--onyx",
    "--pearl",
    "--quill",
    "--reef",
    "--sable",
    "--tide",
    "--umber",
    "--vista",
    "--wren",
    "--zephyr",
    "--bolt",
    "--chip",
    "--drift",
    "--edge",
    "--flex",
    "--hub",
    "--jolt",
    "--loop",
    "--mesh",
    "--neon",
    "--opaque",
    "--prism",
    "--quartz",
    "--ripple",
    "--silica",
    "--torch",
    "--vector",
    "--willow",
    "--xenon",
    "--yonder",
    "--azure",
    "--braid",
    "--cove",
    "--delta-x",
    "--ember-x",
    "--flowing",
    "--granite",
)

_SUB_PAIRS = (
    (("run", "run the operation", "echo"), ("show", "show details", "echo")),
    (("go", "start execution", "echo"), ("list", "list entries", "echo")),
    (("do", "perform the action", "echo"), ("view", "view current state", "echo")),
    (("now", "execute immediately", "echo"), ("status", "report state", "echo")),
    (("on", "enable the feature", "echo"), ("off", "disable the feature", "echo")),
    (("start", "begin the process", "echo"), ("stop", "halt the process", "echo")),
    (("open", "open the resource", "echo"), ("close", "close the resource", "echo")),
    (("add", "append an entry", "echo"), ("drop", "remove an entry", "echo")),
    (("set", "assign a value", "echo"), ("unset", "clear a value", "echo")),
    (("push", "push upstream", "echo"), ("pull", "pull downstream", "echo")),
)

_PLANETS = ("mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune")

_SOLAR = (
    "sun",
    "mercury",
    "venus",
    "earth",
    "mars",
    "jupiter",
    "saturn",
    "uranus",
    "neptune",
    "pluto",
)

_ZODIAC = (
    "aries",
    "taurus",
    "gemini",
    "cancer",
    "leo",
    "virgo",
    "libra",
    "scorpio",
    "sagittarius",
    "capricorn",
    "aquarius",
    "pisces",
)

_CONSTELLATIONS = (
    "andromeda",
    "cassiopeia",
    "cygnus",
    "draco",
    "gemini",
    "leo",
    "lyra",
    "orion",
    "pegasus",
    "phoenix",
    "scorpius",
    "taurus",
    "ursa",
    "virgo",
)

_GREEK = (
    "alpha",
    "beta",
    "gamma",
    "delta",
    "epsilon",
    "zeta",
    "eta",
    "theta",
    "iota",
    "kappa",
    "lambda",
    "mu",
    "nu",
    "xi",
    "omicron",
    "pi",
    "rho",
    "sigma",
    "tau",
    "upsilon",
    "phi",
    "chi",
    "psi",
    "omega",
)

_NATO = (
    "alfa",
    "bravo",
    "charlie",
    "delta",
    "echo",
    "foxtrot",
    "golf",
    "hotel",
    "india",
    "juliett",
    "kilo",
    "lima",
    "mike",
    "november",
    "oscar",
    "papa",
    "quebec",
    "romeo",
    "sierra",
    "tango",
    "uniform",
    "victor",
    "whiskey",
    "xray",
    "yankee",
    "zulu",
)


def _aliases_for(name: str, pool: set[str], seed: int = 0) -> tuple[str, ...]:
    """Generate 3-6 mixed-style aliases for a command, avoiding `pool`.

    Styles alternate across prefixes, suffixes, vowel-stripping, and
    numeric suffixes so sibling commands do not look uniform.
    """
    want = 3 + seed % 4  # 3..6 aliases
    result: list[str] = []
    seen: set[str] = {name}

    def add(raw: str) -> None:
        cand = raw.lower().strip("-_")
        if not cand or len(cand) > 16 or cand == name or cand in pool or cand in seen:
            return
        seen.add(cand)
        result.append(cand)

    for n in (1, 2, 3):
        add(name[:n])
    for n in (2, 3):
        add(name[-n:])
    add(name.replace("_", ""))
    add(name.replace("-", ""))
    add("".join(ch for ch in name if ch not in "aeiou"))
    add(name + "x")
    add(name + "y")
    add("x" + name)
    add("z" + name)
    if len(name) + 3 <= 16:
        add("do-" + name)
        add("run" + name)
        add("my" + name)
    for i in range(1, 10):
        add(f"{name}{i}")
    guard = 0
    while len(result) < want and guard < 1000:
        guard += 1
        add(f"{name[:2] or name}{seed}{guard}")
    return tuple(result[:want])


def _mix(index: int) -> list[Flag]:
    """Produce a mixed set of flags: short+long, short-only, long-only, or none.

    The result is deterministic per index but varies in shape between
    commands so the tree does not look strictly uniform.
    """
    short, short_long, short_help = _SHORT_FLAGS[index % len(_SHORT_FLAGS)]
    long_a = _LONG_FLAGS[index % len(_LONG_FLAGS)]
    long_b = _LONG_FLAGS[(index + 3) % len(_LONG_FLAGS)]
    long_c = _LONG_FLAGS[(index + 7) % len(_LONG_FLAGS)]
    mode = index % 10
    if mode == 0:
        return [
            _f(short, short_long, short_help, action="store_true"),
            _f(None, long_a, f"{long_a[2:]} mode", metavar="VAL"),
        ]
    if mode == 1:
        return [_f(short, None, short_help, action="store_true")]
    if mode == 2:
        return [_f(None, long_a, f"{long_a[2:]} value", metavar="VAL")]
    if mode == 3:
        return []
    if mode == 4:
        return [_f(short, short_long, short_help, metavar="VAL")]
    if mode == 5:
        return [
            _f(None, long_a, f"{long_a[2:]} value", metavar="VAL"),
            _f(None, long_b, f"{long_b[2:]} value", metavar="VAL"),
        ]
    if mode == 6:
        return [
            _f(short, None, short_help, action="store_true"),
            _f(None, long_a, f"{long_a[2:]} value", metavar="VAL"),
        ]
    if mode == 7:
        return [_f(short, short_long, short_help, action="store_true")]
    if mode == 8:
        return [
            _f(None, long_a, f"{long_a[2:]} mode", metavar="VAL"),
            _f(None, long_b, f"{long_b[2:]} mode", metavar="VAL"),
            _f(None, long_c, f"{long_c[2:]} mode", metavar="VAL"),
        ]
    return [_f(short, short_long, short_help, action="store_true")]
