include env.mk

TARGET  := target/cru
DESTDIR ?=

# ── cps: external dependency, no longer required by Cruine ─────────────
# Cruine is a pure-Python project; the standalone binary is produced by
# PyInstaller (single self-contained executable, no system Python needed).
# No upstream C/Rust deps.

.PHONY: all deps build test lint install install-man uninstall clean

all: build

deps:
	-$(PYTHON) -m venv $(VENV)
	$(PYTHON) -m pip --python $(VENV)/bin/python install --upgrade pip
	$(PYTHON) -m pip --python $(VENV)/bin/python install pyinstaller
	$(PYTHON) -m pip --python $(VENV)/bin/python install -e "./src[dev]"

build: deps
	scripts/package.sh $(REPO_ROOT)/target

test:
	$(PY) -m pytest src/tests

lint:
	$(PY) -m ruff check src
	$(PY) -m ruff format --check src

install: build install-man
	install -Dm755 $(TARGET) $(DESTDIR)$(PREFIX)/bin/cru

install-man:
	install -d $(DESTDIR)$(PREFIX)/share/man/man1
	install -d $(DESTDIR)$(PREFIX)/share/man/man5
	install -m 644 docs/cru.1 docs/crush.1 $(DESTDIR)$(PREFIX)/share/man/man1/
	install -m 644 docs/rc.json.5 $(DESTDIR)$(PREFIX)/share/man/man5/

uninstall:
	rm -f $(DESTDIR)$(PREFIX)/bin/cru
	rm -f $(DESTDIR)$(PREFIX)/share/man/man1/cru.1
	rm -f $(DESTDIR)$(PREFIX)/share/man/man1/crush.1
	rm -f $(DESTDIR)$(PREFIX)/share/man/man5/rc.json.5

clean:
	rm -rf target builddir
