#!/bin/bash
# =============================================================================
# Webform External Libraries Update Script
# =============================================================================
# Checks installed library versions and updates those that need updating.
# Creates backups before updating. Uses versioned subdirectories.
#
# Usage:
#   cd /var/www/drupal
#   bash modules/custom/drupal_modules/scripts/update_webform_libraries.sh
#
# Options:
#   --check     Only check versions, don't update
#   --force     Force update all libraries regardless of version
#   --backup    Create backup only, don't update
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Library versions (update these when new versions are released)
declare -A VERSIONS=(
    ["codemirror"]="5.65.12"
    ["jquery.inputmask"]="5.0.9"
    ["jquery.intl-tel-input"]="17.0.19"
    ["jquery.rateit"]="1.1.5"
    ["jquery.select2"]="4.0.13"
    ["jquery.textcounter"]="0.9.1"
    ["jquery.timepicker"]="1.14.0"
    ["popperjs"]="2.11.6"
    ["progress-tracker"]="2.0.7"
    ["signature_pad"]="2.3.0"
    ["tabby"]="12.0.3"
    ["tippyjs"]="6.3.7"
)

# Options
CHECK_ONLY=false
FORCE_UPDATE=false
BACKUP_ONLY=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --check)
            CHECK_ONLY=true
            shift
            ;;
        --force)
            FORCE_UPDATE=true
            shift
            ;;
        --backup)
            BACKUP_ONLY=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

detect_directories() {
    if [ -f "index.php" ] && [ -d "core" ]; then
        DRUPAL_ROOT=$(pwd)
        LIBS_DIR="$DRUPAL_ROOT/libraries"
    elif [ -f "web/index.php" ] && [ -d "web/core" ]; then
        DRUPAL_ROOT=$(pwd)
        LIBS_DIR="$DRUPAL_ROOT/web/libraries"
    else
        log_error "Not in Drupal root directory."
        exit 1
    fi
}

detect_downloader() {
    if command -v wget &> /dev/null; then
        DOWNLOADER="wget"
    elif command -v curl &> /dev/null; then
        DOWNLOADER="curl"
    else
        log_error "Neither wget nor curl found."
        exit 1
    fi
}

download_file() {
    local url=$1
    local output=$2

    if [ "$DOWNLOADER" = "wget" ]; then
        wget -q "$url" -O "$output"
    else
        curl -sL "$url" -o "$output"
    fi
}

# =============================================================================
# Backup Functions
# =============================================================================

create_backup() {
    local backup_dir
    backup_dir="$DRUPAL_ROOT/libraries-backup-$(date +%Y%m%d-%H%M%S)"

    if [ -d "$LIBS_DIR" ]; then
        log_info "Creating backup at $backup_dir..."
        cp -r "$LIBS_DIR" "$backup_dir"
        log_success "Backup created"
        echo "$backup_dir"
    else
        log_warning "No libraries directory to backup"
        echo ""
    fi
}

# =============================================================================
# Version Check Functions
# =============================================================================

get_installed_version() {
    local lib=$1
    local version_file="$LIBS_DIR/$lib/.version"

    if [ -f "$version_file" ]; then
        cat "$version_file"
    else
        echo "unknown"
    fi
}

save_version() {
    local lib=$1
    local version=$2
    echo "$version" > "$LIBS_DIR/$lib/.version"
}

check_versions() {
    echo ""
    echo "=============================================="
    echo "  Library Version Status"
    echo "=============================================="
    echo ""
    printf "%-25s %-15s %-15s %s\n" "Library" "Installed" "Required" "Status"
    printf "%-25s %-15s %-15s %s\n" "-------" "---------" "--------" "------"

    local needs_update=0

    for lib in "${!VERSIONS[@]}"; do
        local required="${VERSIONS[$lib]}"
        local installed
        installed=$(get_installed_version "$lib")
        local status=""

        if [ ! -d "$LIBS_DIR/$lib" ]; then
            status="${RED}Not installed${NC}"
            ((needs_update++))
        elif [ "$installed" = "unknown" ]; then
            status="${YELLOW}Unknown version${NC}"
            ((needs_update++))
        elif [ "$installed" = "$required" ]; then
            status="${GREEN}OK${NC}"
        else
            status="${YELLOW}Update available${NC}"
            ((needs_update++))
        fi

        printf "%-25s %-15s %-15s " "$lib" "$installed" "$required"
        echo -e "$status"
    done

    echo ""
    if [ $needs_update -gt 0 ]; then
        log_warning "$needs_update libraries need attention"
    else
        log_success "All libraries are up to date"
    fi

    return $needs_update
}

# =============================================================================
# Update Functions
# =============================================================================

update_codemirror() {
    local version="${VERSIONS["codemirror"]}"
    log_info "Updating CodeMirror to $version..."

    rm -rf "$LIBS_DIR/codemirror"

    cd /tmp
    rm -rf codemirror.zip codemirror5-*

    download_file "https://github.com/codemirror/codemirror5/archive/refs/tags/$version.zip" "codemirror.zip"
    unzip -q codemirror.zip

    mkdir -p "$LIBS_DIR/codemirror/$version"
    cp -r "codemirror5-$version/lib" "$LIBS_DIR/codemirror/$version/"
    cp -r "codemirror5-$version/mode" "$LIBS_DIR/codemirror/$version/"

    rm -rf codemirror.zip codemirror5-*

    save_version "codemirror" "$version"
    log_success "CodeMirror updated"
}

update_inputmask() {
    local version="${VERSIONS["jquery.inputmask"]}"
    log_info "Updating InputMask to $version..."

    rm -rf "$LIBS_DIR/jquery.inputmask"
    mkdir -p "$LIBS_DIR/jquery.inputmask/$version/dist"

    download_file "https://cdnjs.cloudflare.com/ajax/libs/jquery.inputmask/$version/jquery.inputmask.min.js" \
        "$LIBS_DIR/jquery.inputmask/$version/dist/jquery.inputmask.min.js"

    save_version "jquery.inputmask" "$version"
    log_success "InputMask updated"
}

update_intl_tel_input() {
    local version="${VERSIONS["jquery.intl-tel-input"]}"
    log_info "Updating Intl-Tel-Input to $version..."

    rm -rf "$LIBS_DIR/jquery.intl-tel-input"

    cd /tmp
    rm -rf intl-tel-input.zip intl-tel-input-*

    download_file "https://github.com/jackocnr/intl-tel-input/archive/refs/tags/v$version.zip" "intl-tel-input.zip"
    unzip -q intl-tel-input.zip

    mkdir -p "$LIBS_DIR/jquery.intl-tel-input/$version"
    cp -r "intl-tel-input-$version/build" "$LIBS_DIR/jquery.intl-tel-input/$version/"

    rm -rf intl-tel-input.zip intl-tel-input-*

    save_version "jquery.intl-tel-input" "$version"
    log_success "Intl-Tel-Input updated"
}

update_rateit() {
    local version="${VERSIONS["jquery.rateit"]}"
    log_info "Updating RateIt to $version..."

    rm -rf "$LIBS_DIR/jquery.rateit"
    mkdir -p "$LIBS_DIR/jquery.rateit/$version/scripts" "$LIBS_DIR/jquery.rateit/$version/styles"

    download_file "https://cdnjs.cloudflare.com/ajax/libs/jquery.rateit/$version/jquery.rateit.min.js" \
        "$LIBS_DIR/jquery.rateit/$version/scripts/jquery.rateit.min.js"
    download_file "https://cdnjs.cloudflare.com/ajax/libs/jquery.rateit/$version/rateit.css" \
        "$LIBS_DIR/jquery.rateit/$version/styles/rateit.css"

    save_version "jquery.rateit" "$version"
    log_success "RateIt updated"
}

update_select2() {
    local version="${VERSIONS["jquery.select2"]}"
    log_info "Updating Select2 to $version..."

    rm -rf "$LIBS_DIR/jquery.select2"

    cd /tmp
    rm -rf select2.zip select2-*

    download_file "https://github.com/select2/select2/archive/refs/tags/$version.zip" "select2.zip"
    unzip -q select2.zip

    mkdir -p "$LIBS_DIR/jquery.select2/$version"
    cp -r "select2-$version/dist" "$LIBS_DIR/jquery.select2/$version/"

    rm -rf select2.zip select2-*

    save_version "jquery.select2" "$version"
    log_success "Select2 updated"
}

update_textcounter() {
    local version="${VERSIONS["jquery.textcounter"]}"
    log_info "Updating TextCounter to $version..."

    rm -rf "$LIBS_DIR/jquery.textcounter"

    cd /tmp
    rm -rf textcounter.zip jQuery-Text-Counter-*

    download_file "https://github.com/ractoon/jQuery-Text-Counter/archive/refs/tags/$version.zip" "textcounter.zip"
    unzip -q textcounter.zip

    mkdir -p "$LIBS_DIR/jquery.textcounter/$version"
    cp "jQuery-Text-Counter-$version/textcounter.min.js" "$LIBS_DIR/jquery.textcounter/$version/"

    rm -rf textcounter.zip jQuery-Text-Counter-*

    save_version "jquery.textcounter" "$version"
    log_success "TextCounter updated"
}

update_timepicker() {
    local version="${VERSIONS["jquery.timepicker"]}"
    log_info "Updating Timepicker to $version..."

    rm -rf "$LIBS_DIR/jquery.timepicker"

    cd /tmp
    rm -rf timepicker.zip jquery-timepicker-*

    download_file "https://github.com/jonthornton/jquery-timepicker/archive/refs/tags/$version.zip" "timepicker.zip"
    unzip -q timepicker.zip

    mkdir -p "$LIBS_DIR/jquery.timepicker/$version"
    cp "jquery-timepicker-$version/jquery.timepicker.min.js" "$LIBS_DIR/jquery.timepicker/$version/"
    cp "jquery-timepicker-$version/jquery.timepicker.min.css" "$LIBS_DIR/jquery.timepicker/$version/"

    rm -rf timepicker.zip jquery-timepicker-*

    save_version "jquery.timepicker" "$version"
    log_success "Timepicker updated"
}

update_popperjs() {
    local version="${VERSIONS["popperjs"]}"
    log_info "Updating Popper.js to $version..."

    rm -rf "$LIBS_DIR/popperjs"
    mkdir -p "$LIBS_DIR/popperjs/$version/dist/umd"

    download_file "https://cdn.jsdelivr.net/npm/@popperjs/core@$version/dist/umd/popper.min.js" \
        "$LIBS_DIR/popperjs/$version/dist/umd/popper.min.js"

    save_version "popperjs" "$version"
    log_success "Popper.js updated"
}

update_progress_tracker() {
    local version="${VERSIONS["progress-tracker"]}"
    log_info "Updating Progress Tracker to $version..."

    rm -rf "$LIBS_DIR/progress-tracker"

    cd /tmp
    rm -rf progress-tracker.zip progress-tracker-*

    download_file "https://github.com/NigelOToole/progress-tracker/archive/refs/tags/$version.zip" "progress-tracker.zip"
    unzip -q progress-tracker.zip

    mkdir -p "$LIBS_DIR/progress-tracker/$version"
    cp -r "progress-tracker-$version/src" "$LIBS_DIR/progress-tracker/$version/"

    rm -rf progress-tracker.zip progress-tracker-*

    save_version "progress-tracker" "$version"
    log_success "Progress Tracker updated"
}

update_signature_pad() {
    local version="${VERSIONS["signature_pad"]}"
    log_info "Updating Signature Pad to $version..."

    rm -rf "$LIBS_DIR/signature_pad"

    cd /tmp
    rm -rf signature_pad.zip signature_pad-*

    download_file "https://github.com/szimek/signature_pad/archive/refs/tags/v$version.zip" "signature_pad.zip"
    unzip -q signature_pad.zip

    mkdir -p "$LIBS_DIR/signature_pad/$version"
    cp -r "signature_pad-$version/dist" "$LIBS_DIR/signature_pad/$version/"

    rm -rf signature_pad.zip signature_pad-*

    save_version "signature_pad" "$version"
    log_success "Signature Pad updated"
}

update_tabby() {
    local version="${VERSIONS["tabby"]}"
    log_info "Updating Tabby to $version..."

    rm -rf "$LIBS_DIR/tabby"

    cd /tmp
    rm -rf tabby.zip tabby-*

    download_file "https://github.com/cferdinandi/tabby/archive/refs/tags/$version.zip" "tabby.zip"
    unzip -q tabby.zip

    mkdir -p "$LIBS_DIR/tabby/$version"
    cp -r "tabby-$version/dist" "$LIBS_DIR/tabby/$version/"

    rm -rf tabby.zip tabby-*

    save_version "tabby" "$version"
    log_success "Tabby updated"
}

update_tippyjs() {
    local version="${VERSIONS["tippyjs"]}"
    log_info "Updating Tippy.js to $version..."

    rm -rf "$LIBS_DIR/tippyjs"
    mkdir -p "$LIBS_DIR/tippyjs/$version/dist"

    download_file "https://cdn.jsdelivr.net/npm/tippy.js@$version/dist/tippy.umd.min.js" \
        "$LIBS_DIR/tippyjs/$version/dist/tippy.umd.min.js"
    download_file "https://cdn.jsdelivr.net/npm/tippy.js@$version/dist/tippy.css" \
        "$LIBS_DIR/tippyjs/$version/dist/tippy.css"

    save_version "tippyjs" "$version"
    log_success "Tippy.js updated"
}

update_all() {
    log_info "Updating all libraries..."
    echo ""

    update_codemirror
    update_inputmask
    update_intl_tel_input
    update_rateit
    update_select2
    update_textcounter
    update_timepicker
    update_popperjs
    update_progress_tracker
    update_signature_pad
    update_tabby
    update_tippyjs

    # Set permissions
    chmod -R 755 "$LIBS_DIR"
    find "$LIBS_DIR" -type f -exec chmod 644 {} \;

    echo ""
    log_success "All libraries updated"
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "=============================================="
    echo "  Webform Libraries Update Script"
    echo "=============================================="
    echo ""

    detect_directories
    detect_downloader

    log_info "Drupal root: $DRUPAL_ROOT"
    log_info "Libraries: $LIBS_DIR"

    # Check versions
    check_versions
    needs_update=$?

    if $CHECK_ONLY; then
        exit 0
    fi

    if $BACKUP_ONLY; then
        create_backup
        exit 0
    fi

    if [ $needs_update -eq 0 ] && ! $FORCE_UPDATE; then
        log_info "No updates needed. Use --force to update anyway."
        exit 0
    fi

    # Create backup before updating
    echo ""
    backup_dir=$(create_backup)

    # Update libraries
    echo ""
    update_all

    echo ""
    echo "=============================================="
    echo "  Update Complete"
    echo "=============================================="
    if [ -n "$backup_dir" ]; then
        echo "Backup: $backup_dir"
    fi
    echo ""
    echo "Next steps:"
    echo "  1. Clear Drupal cache: drush cr"
    echo "  2. Test webform functionality"
    echo "  3. Remove backup if everything works:"
    if [ -n "$backup_dir" ]; then
        echo "     rm -rf $backup_dir"
    fi
    echo ""
}

main "$@"
