#!/usr/bin/env bash
#
# bump-version.sh — update version in all 6 locations
#
# Usage:
#   ./scripts/bump-version.sh 0.7.0
#   ./scripts/bump-version.sh 0.7.0 --tag    # also git commit + tag
#   ./scripts/bump-version.sh --check         # show current versions

set -euo pipefail

VERSION_FILES=(
    "pyproject.toml"
    "fledgling/__init__.py"
    "fledgling/pro/__init__.py"
    "bin/fledgling"
    "init/init-fledgling-base.sql"
    "sql/install-fledgling.sql"
)

TEST_FILES=(
    "tests/test_dr_fledgling.py"
    "tests/test_installer.py"
    "tests/conftest.py"
    "tests/test_cli.py"
)

_current() {
    grep '^version' pyproject.toml | head -1 | sed 's/.*"\(.*\)"/\1/'
}

_check() {
    echo "Version sources:"
    for f in "${VERSION_FILES[@]}"; do
        ver=$(grep -oP '\d+\.\d+\.\d+' "$f" | head -1)
        printf "  %-40s %s\n" "$f" "$ver"
    done
    echo ""
    echo "Test fixtures:"
    for f in "${TEST_FILES[@]}"; do
        ver=$(grep -oP '\d+\.\d+\.\d+' "$f" | head -1)
        printf "  %-40s %s\n" "$f" "$ver"
    done
}

_bump() {
    local old="$1" new="$2"
    echo "Bumping $old → $new"
    echo ""

    for f in "${VERSION_FILES[@]}" "${TEST_FILES[@]}"; do
        if [[ -f "$f" ]]; then
            count=$(grep -c "$old" "$f" || true)
            if [[ "$count" -gt 0 ]]; then
                sed -i "s/$old/$new/g" "$f"
                echo "  $f ($count replacements)"
            fi
        fi
    done

    echo ""
    echo "Verify:"
    _check
}

# Parse args
case "${1:-}" in
    --check|-c)
        _check
        ;;
    --help|-h|"")
        echo "Usage: $0 <new-version> [--tag]"
        echo "       $0 --check"
        exit 0
        ;;
    *)
        NEW="$1"
        OLD=$(_current)

        if [[ "$OLD" == "$NEW" ]]; then
            echo "Already at $NEW"
            exit 0
        fi

        _bump "$OLD" "$NEW"

        if [[ "${2:-}" == "--tag" ]]; then
            echo ""
            git add "${VERSION_FILES[@]}" "${TEST_FILES[@]}"
            git commit -m "chore: bump version to $NEW"
            git tag "v$NEW"
            echo "Tagged v$NEW — run 'git push && git push --tags' to publish"
        fi
        ;;
esac
