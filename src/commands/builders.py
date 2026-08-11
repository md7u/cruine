"""Command tree construction via the Cruine builder API.

The tree is assembled from four composable builders:

* ``CommandBuilder`` - fluent builder for a single command node.
* ``SubBuilder`` - builds a nested sub-command tree for a parent command.
* ``ChainBuilder`` - builds a single deep word chain (leaf-first, alias-safe).
* ``GroupBuilder`` - builds an alphabet group (letter + themed commands + chain).
"""

from __future__ import annotations

import itertools

from cruine.commands.flags import (
    _CONSTELLATIONS,
    _GREEK,
    _NATO,
    _PLANETS,
    _SOLAR,
    _SUB_PAIRS,
    _ZODIAC,
    _aliases_for,
    _f,
    _mix,
)
from cruine.commands.model import Command, Flag

__all__ = ["ChainBuilder", "CommandBuilder", "GroupBuilder", "SubBuilder", "_build_tree"]

_CHAIN_LISTS = (_PLANETS, _SOLAR, _ZODIAC, _CONSTELLATIONS, _GREEK, _NATO)


class CommandBuilder:
    """Fluent builder for a single command node.

    Methods chain: ``aliases()``, ``flags()``, ``handler()``, ``positional()``
    and ``sub()`` all return the builder, so a command is composed declaratively
    and materialised with ``build()``::

        cmd = (
            CommandBuilder("probe", "probe the device")
            .aliases("scan", "ping", "p")
            .handler("echo")
            .positional("target")
            .flags(_f("-n", "--name", "target name", metavar="NAME"))
            .build()
        )
    """

    def __init__(self, name: str, help: str) -> None:
        self._name = name
        self._help = help
        self._aliases: tuple[str, ...] = ()
        self._flags: list[Flag] = []
        self._handler: str | None = None
        self._positional: str | None = None
        self._subs: list[CommandBuilder | SubBuilder | ChainBuilder] = []

    def aliases(self, *names: str) -> CommandBuilder:
        self._aliases = tuple(names)
        return self

    def flags(self, *flags: Flag) -> CommandBuilder:
        self._flags = list(flags)
        return self

    def handler(self, name: str) -> CommandBuilder:
        self._handler = name
        return self

    def positional(self, name: str) -> CommandBuilder:
        self._positional = name
        return self

    def sub(self, *builders: CommandBuilder | SubBuilder | ChainBuilder) -> CommandBuilder:
        self._subs.extend(builders)
        return self

    def build(self, parent: Command | None = None) -> Command:
        node = Command(
            name=self._name,
            help=self._help,
            aliases=self._aliases,
            flags=self._flags,
            handler=self._handler,
            positional=self._positional,
            parent=parent,
        )
        for builder in self._subs:
            if isinstance(builder, CommandBuilder):
                node.children.append(builder.build(node))
            elif isinstance(builder, SubBuilder):
                node.children.extend(builder.build(node))
            else:
                chain = builder.build()
                chain.parent = node
                node.children.append(chain)
        return node


class SubBuilder:
    """Build a complete nested sub-command tree for a parent command.

    Each level draws a verb pair from the pool; every node receives mixed
    aliases, mixed flag shapes, and the pair's handler. Alias pools are shared
    per sibling level so nothing collides. ``levels()`` controls how many
    levels deep the subtree grows and ``verbs()`` swaps the action-verb pool,
    so one builder can emit shallow or bushy subtrees.
    """

    def __init__(self, seed: int = 0) -> None:
        self._seed = seed
        self._levels = 2
        self._verbs = _SUB_PAIRS

    def levels(self, n: int) -> SubBuilder:
        self._levels = max(1, n)
        return self

    def verbs(self, *pairs: tuple[tuple[str, str, str], ...]) -> SubBuilder:
        if pairs:
            self._verbs = tuple(pairs)
        return self

    def build(self, parent: Command) -> list[Command]:
        nodes = self._build_level(self._seed, 0)
        for node in nodes:
            node.parent = parent
        return nodes

    def _build_level(self, seed: int, depth: int) -> list[Command]:
        pair = self._verbs[seed % len(self._verbs)]
        out: list[Command] = []
        pool: set[str] = set()
        for name, help_text, handler in pair:
            node = Command(
                name=name,
                help=help_text,
                aliases=_aliases_for(name, pool, seed + depth),
                flags=_mix(seed + depth + 1),
                handler=handler,
            )
            pool.add(name)
            pool.update(node.aliases)
            if depth + 1 < self._levels:
                for kid in self._build_level(seed + 1, depth + 1):
                    kid.parent = node
                    node.children.append(kid)
            out.append(node)
        return out


class ChainBuilder:
    """Build a single deep chain of words.

    Nodes are assembled leaf-first so each node's alias pool already holds its
    child's name and aliases, guaranteeing a collision-free deep path. Every
    node runs the ``echo`` handler.
    """

    def __init__(self, words: tuple[str, ...], seed: int = 0) -> None:
        self._words = tuple(words)
        self._seed = seed

    def build(self) -> Command:
        child: Command | None = None
        for i in range(len(self._words) - 1, -1, -1):
            word = self._words[i]
            pool: set[str] = {word}
            if child is not None:
                pool.add(child.name)
                pool.update(child.aliases)
            node = Command(
                name=word,
                help=f"deep level {i + 1}",
                aliases=_aliases_for(word, pool, self._seed + i),
                flags=_mix(self._seed + i + 1),
                handler="echo",
            )
            if child is not None:
                child.parent = node
                node.children.append(child)
            child = node
        return child or Command("deep", "empty chain")


def _group_aliases(letter: str, seed: int) -> tuple[str, ...]:
    styles = (
        (letter * 2, letter * 3, letter + "1", letter + "-group"),
        (letter + "a", letter * 2, letter + "0", letter + "-all"),
        (letter + "1", letter * 2, letter + "x", letter + "-grp"),
        (letter * 2, letter * 3, letter + "z", letter + "-hub"),
    )
    return styles[seed % len(styles)]


class GroupBuilder:
    """Build an alphabet command group.

    A letter node wraps a themed list of commands. Each command is composed via
    ``CommandBuilder`` with mixed aliases and flags, and carries its own nested
    ``SubBuilder`` subtree; a ``ChainBuilder`` deep chain is appended to the
    group for long paths.
    """

    def __init__(self, letter: str, theme: str, words: str, seed: int) -> None:
        self._letter = letter
        self._theme = theme
        self._names = words.split()
        self._seed = seed

    def build(self, parent: Command | None = None) -> Command:
        aliases = _group_aliases(self._letter, self._seed)
        group = Command(
            name=self._letter,
            help=f"{self._theme} command group ({self._letter})",
            aliases=aliases,
            parent=parent,
        )
        counter = itertools.count(self._seed * 7)
        pool: set[str] = {self._letter, *aliases}
        for index, name in enumerate(self._names):
            child_aliases = _aliases_for(name, pool, next(counter))
            pool.add(name)
            pool.update(child_aliases)
            child = (
                CommandBuilder(name, f"{self._theme}: {name}")
                .aliases(*child_aliases)
                .flags(*_mix(next(counter)))
                .handler("describe")
                .sub(SubBuilder(next(counter)).levels(2 + (index % 2)))
                .build(group)
            )
            group.children.append(child)
        chain = ChainBuilder(
            _CHAIN_LISTS[self._seed % len(_CHAIN_LISTS)][:24], next(counter)
        ).build()
        chain.parent = group
        group.children.append(chain)
        return group


def _build_functional() -> list[CommandBuilder]:
    return [
        (
            CommandBuilder("build", "build the ROM via the full pipeline")
            .aliases("bld", "make", "go", "compile")
            .handler("build")
            .positional("destination")
            .flags(
                _f("-w", "--work-dir", "build workspace directory", metavar="PATH"),
                _f(None, "--skip-fetch", "skip source fetching", action="store_true"),
                _f(None, "--no-fetch", "skip source fetching (alias)", action="store_true"),
                _f(None, "--skip-package", "skip packaging", action="store_true"),
                _f(None, "--clean", "force a clean build", action="store_true"),
                _f(None, "--mem-limit", "virtual memory ulimit in MB", metavar="MB"),
                _f(None, "--no-color", "disable ANSI colors", action="store_true"),
            )
        ),
        (
            CommandBuilder("init", "write an example rc.json recipe")
            .aliases("gen", "template", "scaffold", "new")
            .handler("init")
            .positional("target")
        ),
        (
            CommandBuilder("config", "show, reload, or initialize the Cruine configuration")
            .aliases("conf", "cfg", "prefs", "settings")
            .handler("config")
            .positional("action")
            .flags(
                _f(
                    None,
                    "--dir",
                    "directory to write the config into (config init)",
                    metavar="PATH",
                ),
            )
        ),
        (
            CommandBuilder("doctor", "validate the host environment and tools")
            .aliases("chk", "check", "health", "preflight")
            .handler("doctor")
        ),
        (
            CommandBuilder("info", "print the build plan for the active recipe")
            .aliases("plan", "preview", "show", "about")
            .handler("info")
            .positional("target")
        ),
        (
            CommandBuilder("fetch", "pull manifests and device trees")
            .aliases("sync", "pull", "get", "clone")
            .handler("fetch")
        ),
        (
            CommandBuilder("patch", "apply recipe patches")
            .aliases("apply", "fix", "hotfix")
            .handler("patch")
        ),
        (
            CommandBuilder("pack", "package build outputs")
            .aliases("pkg", "archive", "bundle", "tar")
            .handler("pack")
            .positional("destination")
            .flags(
                _f(
                    None,
                    "--source",
                    "directory to package (default: build output dir)",
                    metavar="PATH",
                ),
            )
        ),
        (
            CommandBuilder("extract", "extract a ROM archive into a directory")
            .aliases("unzip", "unpack", "inflate", "untar")
            .handler("extract")
            .positional("archive")
        ),
        (
            CommandBuilder("repack", "extract, modify, and re-archive a ROM")
            .aliases("repackage", "rearchive", "rebundle", "mod")
            .handler("repack")
            .positional("archive [destination]")
            .flags(
                _f(
                    "-w",
                    "--work-dir",
                    "workspace directory (default: <cwd>/<project_name>)",
                    metavar="PATH",
                ),
                _f(
                    None,
                    "--skip-fetch",
                    "skip extraction; use the existing tree",
                    action="store_true",
                ),
                _f(None, "--no-fetch", "skip extraction (alias)", action="store_true"),
                _f(
                    None,
                    "--skip-package",
                    "extract and modify but do not package",
                    action="store_true",
                ),
                _f(None, "--no-color", "disable ANSI colors", action="store_true"),
            )
        ),
        (
            CommandBuilder("clean", "request a clean build")
            .aliases("cls", "wipe", "purge")
            .handler("echo")
        ),
        (
            CommandBuilder("formats", "list supported output formats")
            .aliases("fmt", "ext", "types")
            .handler("formats")
        ),
        (
            CommandBuilder("version", "print the cruine version")
            .aliases("ver", "verinfo", "verstr")
            .handler("version")
        ),
        (
            CommandBuilder("env", "show the host environment report")
            .aliases("environment", "sysinfo", "sysenv")
            .handler("env")
        ),
        (
            CommandBuilder("log", "tail the most recent build log")
            .aliases("logs", "tail", "journal")
            .handler("log")
            .flags(_f(None, "--dir", "directory to scan for build logs", metavar="PATH"))
        ),
        (
            CommandBuilder("ccache", "inspect ccache statistics")
            .aliases("cache", "cc", "compilecache")
            .handler("ccache")
        ),
        (
            CommandBuilder("jobs", "print the recommended parallel job count")
            .aliases("par", "cores", "jobcount")
            .handler("jobs")
        ),
        (
            CommandBuilder("path", "resolve and echo a command path")
            .aliases("which", "resolve", "trace")
            .handler("path")
            .positional("command")
        ),
        (
            CommandBuilder("tree", "print the command tree")
            .aliases("map", "index", "browse")
            .handler("tree")
            .positional("depth")
        ),
        (
            CommandBuilder("help", "show help for a command or path")
            .aliases("assist", "?", "manual")
            .handler("help")
            .positional("command")
        ),
        (
            CommandBuilder("tier", "deep command chain (depth 25)")
            .aliases("deep", "chain", "ladder")
            .sub(ChainBuilder(_NATO[:24], 0))
        ),
        (
            CommandBuilder("crush", "interactive shell over the command tree")
            .aliases("sh", "console", "repl")
            .handler("shell")
            .positional("path")
        ),
    ]


_LOWER = {
    "a": (
        "analyze apk adb audit arch attach apply agent alias assert "
        "access activity adapter admin affinity aggregate allocate "
        "anchor annotate answer"
    ),
    "b": (
        "bake bundle binary branch backup bootstrap bench badge beacon build "
        "blueprint bolt block broadcast browse buffer bug burn byte"
    ),
    "c": (
        "clone clean compile cache connect commit chart check control config "
        "call cancel capture carve cascade catalog certify change classify click"
    ),
    "d": (
        "deploy debug diff dump detect decrypt daemon dynamic domain decode "
        "dedupe define degrade delete deliver delta derive describe destroy dispatch"
    ),
    "e": (
        "env export execute edit enable extract encrypt erase emit entry echo "
        "eject elevate embed embrace emulate encode endorse enforce enroll enter"
    ),
    "f": (
        "fetch flash format find filter finalize fix force freeze follow factor "
        "fail fasten feed file fingerprint fire fork forward frame fuzz"
    ),
    "g": (
        "git graph generate grep guard group grab grant gauge glide gather "
        "gate gear ghost glance gradient graft grammar gravity groom guide"
    ),
    "h": (
        "host help history hash handle hook health head hexdump hover halt "
        "handshake hangup harness heartbeat hello hint hold home hydrate"
    ),
    "i": (
        "image info install inspect import index identify ignore inject icon idle "
        "implement include infer inflate ingest init inline input insert"
    ),
    "j": (
        "jobs jar join jump justify jail juice jitter jot json jam java jelly "
        "jinx jockey jolt journal judo juggle junction jumper"
    ),
    "k": (
        "kernel key kconfig kick kill keep ko kvm klog keystone kh kilo kindle "
        "kinetic kmsg knobs kprobe kselftest kubectl kworker"
    ),
    "l": (
        "log list link lint label load launch lookup lock lens lambda last latency "
        "lay layout leader lease legacy level library license lifecycle"
    ),
    "m": (
        "make mka manifest module mirror mount merge measure map move machine magnet "
        "mailbox maintain major manage mark mask matrix media memory"
    ),
    "n": (
        "network node notes notify navigate narrow nuke nfs name namespace nat net "
        "netboot nibble nickname nightly noise north now number nurture"
    ),
    "o": (
        "output option optimize overlay order open offset observe oracle object obey "
        "octal offer oncall opaque operate outline override own ozone"
    ),
    "p": (
        "package patch pack publish push pull prune probe parse path pace palette "
        "panic parallel parity park part password pause persist pick pin"
    ),
    "q": (
        "query qemu quick quit quote queue quash quantify qualifier quirk quadrant "
        "quantum quarantine quarry quartile quench quest quiet quintile quota"
    ),
    "r": (
        "rom repo release reset restore rebase rebuild run resolve review raid ram "
        "range rate raw reach read reboot record recover reduce registry"
    ),
    "s": (
        "system sync source setup status scan search snapshot strip sign safety "
        "sample sandbox save scale scheme score script scrub secure seed select"
    ),
    "t": (
        "tool target test tree trace tag track transform transfer tune table tail "
        "take tamper tap task teach team tee temp term throttle"
    ),
    "u": (
        "update unpack upload unzip undo unset unify unmount uptime unblock unbundle "
        "uncheck underscore unearth unflag unlock unmark unparse unwrap upgrade"
    ),
    "v": (
        "vendor verify version view validate value virtual variant verbose vacuum vault "
        "vector vent verdict vim vlog volume vmlinux"
    ),
    "w": (
        "workspace watch wipe write wrap weight window work walk wait wake walkthrough "
        "wall warp watermark weave wedge wizard wombat world"
    ),
    "x": (
        "cross xfer xmit xray xattr x86 xz xrandr xen xmpp xterm xor xorg xperf "
        "xslt xtest xwayland xyz xfs xrdb"
    ),
    "y": (
        "yaml yield yank year yodle yolo yamlfmt yarn yaw yeast yellow yelp yesterday "
        "yin yodel yoke young your yttrium yq"
    ),
    "z": (
        "zip zram zstd zero zoom zap zone zimage zcat zenith zephyr zigzag zinc "
        "zipper zlib zombie zonetest zynq zpool zk"
    ),
}

_UPPER = {
    "A": (
        "aosp avb api artifact archive alert authorize assemble ascii arp abi "
        "abseil accept acl address adapter agent album alpine android avrcp"
    ),
    "B": (
        "binary backend block byte bsp benchmark bridge broker bootloader bionic "
        "bitmap bluetooth break buffer bundle bpf bus bootctl busdtool"
    ),
    "C": (
        "crypto cert checksum codec container client corpus cgroup caveat capability "
        "carrier cellular cipher cms compress console core cryptfs custom"
    ),
    "D": (
        "debugger dumpsys dependency delta driver download decrypt ditto dashboard "
        "deadlock deblob decode deodex descriptor developer diagnostic dialer "
        "digest dma docker"
    ),
    "E": (
        "emulator exec elf endpoint event eabi extractall except eager edid "
        "egrep eject ellipse embedded emoji empty enable engine epoll escalate"
    ),
    "F": (
        "firmware fstab fsck factory feature flag flow fuzz fork fabric fastboot "
        "fat fence fiber filter flashtool fota fractal fragment frame"
    ),
    "G": (
        "gpu gralloc glamor gecko generic gadget gltf gps gesture gallery gateway "
        "gaussian genesis geometry gib glean glog gnss gradle graphics gyro"
    ),
    "H": (
        "hardware hw hal hci hwc hevc hdmi hotplug hint hwcomposer hackbench handset "
        "heap heartbeat helper hibernate hostapd huffman hydra hypervisor"
    ),
    "I": (
        "initrc iptables iso idb idmap iommu identity interp ifconfig icmp iface "
        "igmp ignore ime imei imply index install intel interface"
    ),
    "J": (
        "json jpeg jumpstart jvm jitter jack jank jar javac jce jedit jenkins "
        "jint jobqueue journald jpeg jscore jumbo jvm jwk"
    ),
    "K": (
        "kernelconfig keyring kasan kms kvm kdump kallsyms kcfi kconfig kdb kexec "
        "kgdb kheaders kinit kmem kmod kmsan kprobe ksplice kthread kunit"
    ),
    "L": (
        "linker launcher layout library latency loader loopback lcd lamp ldconfig "
        "legacy lfs libc libhybris libvirt linaro live lmk loop lock"
    ),
    "M": (
        "module memory msm mkbootimg mdtp monitor machine mixer mac mapper mask "
        "max media merge metadata method mhz micro mirror mock modem"
    ),
    "N": (
        "nfc namespace numeric native netd nocache nano narrow nas nat nav ndk "
        "neck netlink network nexus nft nodebug nomap nop nougat"
    ),
    "O": (
        "overlayfs oem ondevice opcode opencl object ota oauth octal odf offsetof "
        "ois omap oneplus openmax opengl optimize otp overclock owncloud"
    ),
    "P": (
        "platform pixel product property prototype payload proguard pipeline pm param "
        "patchset pathname pattern pdf perf phandle pid plugin policy pointer"
    ),
    "Q": (
        "qualcomm quantizer quickboot quotient qcom qdl qfp qfuse qi qidl qmi "
        "qmp qnx qpst qrng qsee qti quat query quicc qvga"
    ),
    "R": (
        "runtime resource radio ramdisk recovery registry render rro ram range rate "
        "realpath realloc reboot refcount regex relay remap remoteproc reset rpc"
    ),
    "S": (
        "security selinux sepolicy server selftest sparse sqlite stub staging sandbox "
        "scsi sdk seccomp service shell shim slot smmu soc spi"
    ),
    "T": (
        "treble target tensor toolchain tracer telemetry throttle tz taint tap tcp "
        "tee telephony temp terminal thread tidy timeout tls tombstones topology"
    ),
    "U": (
        "userspace uevent uart ufs usb upstream updateengine udev uapi uaudio uboot "
        "uid uio uksm ulib umount uname unicode unit unlock"
    ),
    "V": (
        "vendor vold vts vulkan vector vm voltage vintf vapi vault vboot vcore "
        "vdso vect vendorimage veth vfs vga video virtio visual"
    ),
    "W": (
        "watchdog wifi wlan wakelock wm wrap wake watermark wav wcd webview wfd "
        "white wick window winsys wmx wpa wq ws wvwlan"
    ),
    "X": (
        "xattr xdelta xkb xmp xr x86 xanadu xbps xcb xclk xcom xdr xend xevent "
        "xfer xform xhost xi xinetd xkbcomp xlock"
    ),
    "Y": (
        "yocto yield yellow yaboot yacc yank yapp yarn yas yaw ybuild yday "
        "yearbook yeast yelp yen yin yld yml yoctopuce"
    ),
    "Z": (
        "zygote zram zen zlib zcat zcr zephyr zero zig zinc zipped ziti zmalloc "
        "zoned zpool zramctl zsh zswap zulu zynga zzz"
    ),
}


_THEMES = {
    "a": "analytics",
    "b": "builder",
    "c": "control",
    "d": "device",
    "e": "engine",
    "f": "fetch",
    "g": "git",
    "h": "host",
    "i": "image",
    "j": "jobs",
    "k": "kernel",
    "l": "log",
    "m": "make",
    "n": "network",
    "o": "output",
    "p": "package",
    "q": "query",
    "r": "rom",
    "s": "system",
    "t": "tool",
    "u": "update",
    "v": "vendor",
    "w": "workspace",
    "x": "cross",
    "y": "yaml",
    "z": "zip",
    "A": "aosp",
    "B": "binary",
    "C": "crypto",
    "D": "debug",
    "E": "emulator",
    "F": "firmware",
    "G": "graphics",
    "H": "hardware",
    "I": "init",
    "J": "json",
    "K": "kernel",
    "L": "linker",
    "M": "module",
    "N": "native",
    "O": "overlay",
    "P": "platform",
    "Q": "qualcomm",
    "R": "runtime",
    "S": "security",
    "T": "treble",
    "U": "userspace",
    "V": "vendor",
    "W": "watchdog",
    "X": "xattr",
    "Y": "yocto",
    "Z": "zygote",
}


def _build_tree() -> Command:
    root = Command(name="cru", help="cruine command root")
    for index, (letter, words) in enumerate(_LOWER.items()):
        group = GroupBuilder(letter, _THEMES[letter], words, index).build(root)
        root.children.append(group)
    for index, (letter, words) in enumerate(_UPPER.items()):
        group = GroupBuilder(letter, _THEMES[letter], words, index + 26).build(root)
        root.children.append(group)
    for builder in _build_functional():
        root.children.append(builder.build(root))
    return root
