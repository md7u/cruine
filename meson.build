project('cruine',
  version : '0.1.0',
  license : 'MIT',
  default_options : [
    'strip=true',
  ],
)

# ── Auto-detect architecture via scripts/cross.sh ──────────────────────────
gen_cross = find_program('scripts/cross.sh')
run_command(gen_cross, check : true)

py = import('python').find_installation()

build_dir = meson.project_build_root() / 'cru-dist'
src_dir = meson.project_source_root()

# ── Install prefix detection (Cudane: /system, glibc: /usr) ─────────────
detect = find_program('scripts/detect.sh')
detected_prefix = run_command(detect, 'prefix', check : false).stdout().strip()
if detected_prefix == ''
  detected_prefix = '/usr'
endif

# Honor an explicit `-Dprefix=...`; treat the meson default (/usr/local) as
# "not chosen" so the detected prefix applies automatically.
sys_prefix = get_option('prefix')
if sys_prefix == '/usr/local'
  sys_prefix = detected_prefix
endif

package_cmd = [
  'sh', '-c',
  '@0@/scripts/package.sh @1@ && cp @1@/cru @OUTPUT@'
  .format(src_dir, build_dir),
]

custom_target('cru',
  build_by_default : true,
  build_always_stale : true,
  install : true,
  install_dir : sys_prefix / 'bin',
  command : package_cmd,
  output : 'cru',
)

install_data(
  'docs/cru.1',
  'docs/crush.1',
  install_dir : sys_prefix / 'share/man/man1',
)

install_data(
  'docs/rc.json.5',
  install_dir : sys_prefix / 'share/man/man5',
)
