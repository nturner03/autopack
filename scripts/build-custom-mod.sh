#!/usr/bin/env bash
# Build a custom mod from custom-mods/<name> and ship its jar in the pack.
#   build-custom-mod.sh <name>            ./gradlew build, copy jar to packwiz/mods/, packwiz refresh
#   build-custom-mod.sh <name> --test     also run the gametest task first (runGameTestServer)
#   build-custom-mod.sh <name> --dev      dev-only tool mod from infrastructure/dev-mods/<name> (e.g.
#                                         pexp_devtools): the jar goes to infrastructure/cache/dev-mods/
#                                         and the dev server's and headless client's mods/, never into
#                                         packwiz/ (players never get it). Restart them to load it.
#
# The jar is committed under packwiz/mods/ (the only tracked jars), so
# packwiz serve/installer ship it to clients and the server without a remote
# release. The previous build of the same mod is replaced. Java comes from the
# pack's MC version (never the host's PATH java, which is 1.8).
. "$(dirname -- "$0")/../infrastructure/lib/common.sh"
name=${1:?usage: build-custom-mod.sh <name> [--test] [--dev]}
shift
test=false dev=false
for arg in "$@"; do
  case $arg in
    --test) test=true ;;
    --dev) dev=true ;;
    *) die "unknown option $arg" ;;
  esac
done
dir="$REPO_DIR/custom-mods/$name"
$dev && [ -d "$DEV_MODS_SRC/$name" ] && dir="$DEV_MODS_SRC/$name"
[ -x "$dir/gradlew" ] || die "no Gradle wrapper at $dir/gradlew"
export JAVA_HOME
JAVA_HOME=$(dirname "$(dirname "$(pack_java)")")
cd "$dir"
if $test; then
  ./gradlew --no-daemon -q runGameTestServer || die "gametests failed"
fi
./gradlew --no-daemon -q build || die "build failed"
jar=$(ls -1t build/libs/*.jar | grep -vE -- '-(sources|javadoc|dev|slim)\.jar$' | head -1)
[ -n "$jar" ] || die "no jar in build/libs"
modid=$(basename "$jar" .jar | sed -E 's/[-_][0-9].*$//')
if $dev; then
  mkdir -p "$DEV_MODS_DIR"
  find "$DEV_MODS_DIR" -maxdepth 1 -name "$modid[-_][0-9]*.jar" -delete
  cp "$jar" "$DEV_MODS_DIR/"
  [ -d "$SERVER_DIR/mods" ] && install_dev_mods "$SERVER_DIR/mods"
  [ -d "$CLIENT_DIR/mods" ] && install_dev_mods "$CLIENT_DIR/mods"
  echo "$(dev_mod_hash "$dir")" >"$DEV_MODS_DIR/.$name.srchash"
  log "dev-only $(basename "$jar") -> $DEV_MODS_DIR (+ dev server and headless client mods/; restart them to load it)"
  exit 0
fi
find "$REPO_DIR/packwiz/mods" -maxdepth 1 -name "$modid[-_][0-9]*.jar" -delete
cp "$jar" "$REPO_DIR/packwiz/mods/"
refresh_pack
log "shipped $(basename "$jar") -> packwiz/mods/ (sha256 $(sha256sum "$jar" | cut -c1-12))"
