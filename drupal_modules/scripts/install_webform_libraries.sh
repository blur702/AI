#!/bin/bash
# =============================================================================
# Webform External Libraries Installation Script
# =============================================================================
# Downloads and installs all 12 required Webform libraries
# Libraries are installed in versioned subdirectories for easier management
#
# Usage:
#   cd /var/www/drupal
#   bash modules/custom/drupal_modules/scripts/install_webform_libraries.sh
#
# Requirements:
#   - wget or curl
#   - unzip
#   - Write access to libraries directory
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Library versions
CODEMIRROR_VERSION="5.65.12"
INPUTMASK_VERSION="5.0.9"
INTL_TEL_INPUT_VERSION="17.0.19"
RATEIT_VERSION="1.1.5"
SELECT2_VERSION="4.0.13"
TEXTCOUNTER_VERSION="0.9.1"
TIMEPICKER_VERSION="1.14.0"
POPPERJS_VERSION="2.11.6"
PROGRESS_TRACKER_VERSION="2.0.7"
SIGNATURE_PAD_VERSION="2.3.0"
TABBY_VERSION="12.0.3"
TIPPYJS_VERSION="6.3.7"

# Counters
INSTALLED=0
FAILED=0

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

# Detect download tool
detect_downloader() {
    if command -v wget &> /dev/null; then
        DOWNLOADER="wget"
    elif command -v curl &> /dev/null; then
        DOWNLOADER="curl"
    else
        log_error "Neither wget nor curl found. Please install one."
        exit 1
    fi
    log_info "Using $DOWNLOADER for downloads"
}

# Download file
download_file() {
    local url=$1
    local output=$2

    if [ "$DOWNLOADER" = "wget" ]; then
        wget -q "$url" -O "$output"
    else
        curl -sL "$url" -o "$output"
    fi
}

# Detect Drupal root and libraries directory
detect_directories() {
    # Check if we're in Drupal root
    if [ -f "index.php" ] && [ -d "core" ]; then
        DRUPAL_ROOT=$(pwd)
        LIBS_DIR="$DRUPAL_ROOT/libraries"
    elif [ -f "web/index.php" ] && [ -d "web/core" ]; then
        DRUPAL_ROOT=$(pwd)
        LIBS_DIR="$DRUPAL_ROOT/web/libraries"
    else
        log_error "Not in Drupal root directory. Please cd to your Drupal root."
        exit 1
    fi

    log_info "Drupal root: $DRUPAL_ROOT"
    log_info "Libraries directory: $LIBS_DIR"

    # Create libraries directory if needed
    mkdir -p "$LIBS_DIR"
}

# Save version to .version file
save_version() {
    local lib_dir=$1
    local version=$2
    echo "$version" > "$lib_dir/.version"
}

# =============================================================================
# Library Installation Functions
# =============================================================================

install_codemirror() {
    log_info "Installing CodeMirror $CODEMIRROR_VERSION..."
    local LIB_DIR="$LIBS_DIR/codemirror/$CODEMIRROR_VERSION"

    if [ -f "$LIB_DIR/lib/codemirror.js" ]; then
        log_warning "CodeMirror already installed, skipping"
        return 0
    fi

    cd /tmp
    rm -rf codemirror.zip codemirror5-*

    download_file "https://github.com/codemirror/codemirror5/archive/refs/tags/$CODEMIRROR_VERSION.zip" "codemirror.zip"
    unzip -q codemirror.zip

    mkdir -p "$LIB_DIR"
    cp -r codemirror5-$CODEMIRROR_VERSION/lib "$LIB_DIR/"
    cp -r codemirror5-$CODEMIRROR_VERSION/mode "$LIB_DIR/"

    rm -rf codemirror.zip codemirror5-*

    if [ -f "$LIB_DIR/lib/codemirror.js" ]; then
        save_version "$LIBS_DIR/codemirror" "$CODEMIRROR_VERSION"
        log_success "CodeMirror installed"
        ((INSTALLED++))
    else
        log_error "CodeMirror installation failed"
        ((FAILED++))
    fi
}

install_inputmask() {
    log_info "Installing jQuery InputMask $INPUTMASK_VERSION..."
    local LIB_DIR="$LIBS_DIR/jquery.inputmask/$INPUTMASK_VERSION"

    if [ -f "$LIB_DIR/dist/jquery.inputmask.min.js" ]; then
        log_warning "InputMask already installed, skipping"
        return 0
    fi

    mkdir -p "$LIB_DIR/dist"
    download_file "https://cdnjs.cloudflare.com/ajax/libs/jquery.inputmask/$INPUTMASK_VERSION/jquery.inputmask.min.js" \
        "$LIB_DIR/dist/jquery.inputmask.min.js"

    if [ -f "$LIB_DIR/dist/jquery.inputmask.min.js" ]; then
        save_version "$LIBS_DIR/jquery.inputmask" "$INPUTMASK_VERSION"
        log_success "InputMask installed"
        ((INSTALLED++))
    else
        log_error "InputMask installation failed"
        ((FAILED++))
    fi
}

install_intl_tel_input() {
    log_info "Installing jQuery Intl-Tel-Input $INTL_TEL_INPUT_VERSION..."
    local LIB_DIR="$LIBS_DIR/jquery.intl-tel-input/$INTL_TEL_INPUT_VERSION"

    if [ -f "$LIB_DIR/build/js/intlTelInput.min.js" ]; then
        log_warning "Intl-Tel-Input already installed, skipping"
        return 0
    fi

    cd /tmp
    rm -rf intl-tel-input.zip intl-tel-input-*

    download_file "https://github.com/jackocnr/intl-tel-input/archive/refs/tags/v$INTL_TEL_INPUT_VERSION.zip" "intl-tel-input.zip"
    unzip -q intl-tel-input.zip

    mkdir -p "$LIB_DIR"
    cp -r intl-tel-input-$INTL_TEL_INPUT_VERSION/build "$LIB_DIR/"

    rm -rf intl-tel-input.zip intl-tel-input-*

    if [ -f "$LIB_DIR/build/js/intlTelInput.min.js" ]; then
        save_version "$LIBS_DIR/jquery.intl-tel-input" "$INTL_TEL_INPUT_VERSION"
        log_success "Intl-Tel-Input installed"
        ((INSTALLED++))
    else
        log_error "Intl-Tel-Input installation failed"
        ((FAILED++))
    fi
}

install_rateit() {
    log_info "Installing jQuery RateIt $RATEIT_VERSION..."
    local LIB_DIR="$LIBS_DIR/jquery.rateit/$RATEIT_VERSION"

    if [ -f "$LIB_DIR/scripts/jquery.rateit.min.js" ]; then
        log_warning "RateIt already installed, skipping"
        return 0
    fi

    mkdir -p "$LIB_DIR/scripts" "$LIB_DIR/styles"

    download_file "https://cdnjs.cloudflare.com/ajax/libs/jquery.rateit/$RATEIT_VERSION/jquery.rateit.min.js" \
        "$LIB_DIR/scripts/jquery.rateit.min.js"
    download_file "https://cdnjs.cloudflare.com/ajax/libs/jquery.rateit/$RATEIT_VERSION/rateit.css" \
        "$LIB_DIR/styles/rateit.css"

    if [ -f "$LIB_DIR/scripts/jquery.rateit.min.js" ]; then
        save_version "$LIBS_DIR/jquery.rateit" "$RATEIT_VERSION"
        log_success "RateIt installed"
        ((INSTALLED++))
    else
        log_error "RateIt installation failed"
        ((FAILED++))
    fi
}

install_select2() {
    log_info "Installing jQuery Select2 $SELECT2_VERSION..."
    local LIB_DIR="$LIBS_DIR/jquery.select2/$SELECT2_VERSION"

    if [ -f "$LIB_DIR/dist/js/select2.min.js" ]; then
        log_warning "Select2 already installed, skipping"
        return 0
    fi

    cd /tmp
    rm -rf select2.zip select2-*

    download_file "https://github.com/select2/select2/archive/refs/tags/$SELECT2_VERSION.zip" "select2.zip"
    unzip -q select2.zip

    mkdir -p "$LIB_DIR"
    cp -r select2-$SELECT2_VERSION/dist "$LIB_DIR/"

    rm -rf select2.zip select2-*

    if [ -f "$LIB_DIR/dist/js/select2.min.js" ]; then
        save_version "$LIBS_DIR/jquery.select2" "$SELECT2_VERSION"
        log_success "Select2 installed"
        ((INSTALLED++))
    else
        log_error "Select2 installation failed"
        ((FAILED++))
    fi
}

install_textcounter() {
    log_info "Installing jQuery TextCounter $TEXTCOUNTER_VERSION..."
    local LIB_DIR="$LIBS_DIR/jquery.textcounter/$TEXTCOUNTER_VERSION"

    if [ -f "$LIB_DIR/textcounter.min.js" ]; then
        log_warning "TextCounter already installed, skipping"
        return 0
    fi

    cd /tmp
    rm -rf textcounter.zip jQuery-Text-Counter-*

    download_file "https://github.com/ractoon/jQuery-Text-Counter/archive/refs/tags/$TEXTCOUNTER_VERSION.zip" "textcounter.zip"
    unzip -q textcounter.zip

    mkdir -p "$LIB_DIR"
    cp jQuery-Text-Counter-$TEXTCOUNTER_VERSION/textcounter.min.js "$LIB_DIR/"

    rm -rf textcounter.zip jQuery-Text-Counter-*

    if [ -f "$LIB_DIR/textcounter.min.js" ]; then
        save_version "$LIBS_DIR/jquery.textcounter" "$TEXTCOUNTER_VERSION"
        log_success "TextCounter installed"
        ((INSTALLED++))
    else
        log_error "TextCounter installation failed"
        ((FAILED++))
    fi
}

install_timepicker() {
    log_info "Installing jQuery Timepicker $TIMEPICKER_VERSION..."
    local LIB_DIR="$LIBS_DIR/jquery.timepicker/$TIMEPICKER_VERSION"

    if [ -f "$LIB_DIR/jquery.timepicker.min.js" ]; then
        log_warning "Timepicker already installed, skipping"
        return 0
    fi

    cd /tmp
    rm -rf timepicker.zip jquery-timepicker-*

    download_file "https://github.com/jonthornton/jquery-timepicker/archive/refs/tags/$TIMEPICKER_VERSION.zip" "timepicker.zip"
    unzip -q timepicker.zip

    mkdir -p "$LIB_DIR"
    cp jquery-timepicker-$TIMEPICKER_VERSION/jquery.timepicker.min.js "$LIB_DIR/"
    cp jquery-timepicker-$TIMEPICKER_VERSION/jquery.timepicker.min.css "$LIB_DIR/"

    rm -rf timepicker.zip jquery-timepicker-*

    if [ -f "$LIB_DIR/jquery.timepicker.min.js" ]; then
        save_version "$LIBS_DIR/jquery.timepicker" "$TIMEPICKER_VERSION"
        log_success "Timepicker installed"
        ((INSTALLED++))
    else
        log_error "Timepicker installation failed"
        ((FAILED++))
    fi
}

install_popperjs() {
    log_info "Installing Popper.js $POPPERJS_VERSION..."
    local LIB_DIR="$LIBS_DIR/popperjs/$POPPERJS_VERSION"

    if [ -f "$LIB_DIR/dist/umd/popper.min.js" ]; then
        log_warning "Popper.js already installed, skipping"
        return 0
    fi

    mkdir -p "$LIB_DIR/dist/umd"
    download_file "https://cdn.jsdelivr.net/npm/@popperjs/core@$POPPERJS_VERSION/dist/umd/popper.min.js" \
        "$LIB_DIR/dist/umd/popper.min.js"

    if [ -f "$LIB_DIR/dist/umd/popper.min.js" ]; then
        save_version "$LIBS_DIR/popperjs" "$POPPERJS_VERSION"
        log_success "Popper.js installed"
        ((INSTALLED++))
    else
        log_error "Popper.js installation failed"
        ((FAILED++))
    fi
}

install_progress_tracker() {
    log_info "Installing Progress Tracker $PROGRESS_TRACKER_VERSION..."
    local LIB_DIR="$LIBS_DIR/progress-tracker/$PROGRESS_TRACKER_VERSION"

    if [ -f "$LIB_DIR/src/progress-tracker.js" ]; then
        log_warning "Progress Tracker already installed, skipping"
        return 0
    fi

    cd /tmp
    rm -rf progress-tracker.zip progress-tracker-*

    download_file "https://github.com/NigelOToole/progress-tracker/archive/refs/tags/$PROGRESS_TRACKER_VERSION.zip" "progress-tracker.zip"
    unzip -q progress-tracker.zip

    mkdir -p "$LIB_DIR"
    cp -r progress-tracker-$PROGRESS_TRACKER_VERSION/src "$LIB_DIR/"

    rm -rf progress-tracker.zip progress-tracker-*

    if [ -f "$LIB_DIR/src/progress-tracker.js" ]; then
        save_version "$LIBS_DIR/progress-tracker" "$PROGRESS_TRACKER_VERSION"
        log_success "Progress Tracker installed"
        ((INSTALLED++))
    else
        log_error "Progress Tracker installation failed"
        ((FAILED++))
    fi
}

install_signature_pad() {
    log_info "Installing Signature Pad $SIGNATURE_PAD_VERSION..."
    local LIB_DIR="$LIBS_DIR/signature_pad/$SIGNATURE_PAD_VERSION"

    if [ -f "$LIB_DIR/dist/signature_pad.min.js" ]; then
        log_warning "Signature Pad already installed, skipping"
        return 0
    fi

    cd /tmp
    rm -rf signature_pad.zip signature_pad-*

    download_file "https://github.com/szimek/signature_pad/archive/refs/tags/v$SIGNATURE_PAD_VERSION.zip" "signature_pad.zip"
    unzip -q signature_pad.zip

    mkdir -p "$LIB_DIR"
    cp -r signature_pad-$SIGNATURE_PAD_VERSION/dist "$LIB_DIR/"

    rm -rf signature_pad.zip signature_pad-*

    if [ -f "$LIB_DIR/dist/signature_pad.min.js" ]; then
        save_version "$LIBS_DIR/signature_pad" "$SIGNATURE_PAD_VERSION"
        log_success "Signature Pad installed"
        ((INSTALLED++))
    else
        log_error "Signature Pad installation failed"
        ((FAILED++))
    fi
}

install_tabby() {
    log_info "Installing Tabby $TABBY_VERSION..."
    local LIB_DIR="$LIBS_DIR/tabby/$TABBY_VERSION"

    if [ -f "$LIB_DIR/dist/js/tabby.min.js" ]; then
        log_warning "Tabby already installed, skipping"
        return 0
    fi

    cd /tmp
    rm -rf tabby.zip tabby-*

    download_file "https://github.com/cferdinandi/tabby/archive/refs/tags/$TABBY_VERSION.zip" "tabby.zip"
    unzip -q tabby.zip

    mkdir -p "$LIB_DIR"
    cp -r tabby-$TABBY_VERSION/dist "$LIB_DIR/"

    rm -rf tabby.zip tabby-*

    if [ -f "$LIB_DIR/dist/js/tabby.min.js" ]; then
        save_version "$LIBS_DIR/tabby" "$TABBY_VERSION"
        log_success "Tabby installed"
        ((INSTALLED++))
    else
        log_error "Tabby installation failed"
        ((FAILED++))
    fi
}

install_tippyjs() {
    log_info "Installing Tippy.js $TIPPYJS_VERSION..."
    local LIB_DIR="$LIBS_DIR/tippyjs/$TIPPYJS_VERSION"

    if [ -f "$LIB_DIR/dist/tippy.umd.min.js" ]; then
        log_warning "Tippy.js already installed, skipping"
        return 0
    fi

    mkdir -p "$LIB_DIR/dist"
    download_file "https://cdn.jsdelivr.net/npm/tippy.js@$TIPPYJS_VERSION/dist/tippy.umd.min.js" \
        "$LIB_DIR/dist/tippy.umd.min.js"
    download_file "https://cdn.jsdelivr.net/npm/tippy.js@$TIPPYJS_VERSION/dist/tippy.css" \
        "$LIB_DIR/dist/tippy.css"

    if [ -f "$LIB_DIR/dist/tippy.umd.min.js" ]; then
        save_version "$LIBS_DIR/tippyjs" "$TIPPYJS_VERSION"
        log_success "Tippy.js installed"
        ((INSTALLED++))
    else
        log_error "Tippy.js installation failed"
        ((FAILED++))
    fi
}

# =============================================================================
# Verification
# =============================================================================

verify_installation() {
    echo ""
    echo "=============================================="
    echo "  Installation Verification"
    echo "=============================================="

    local TOTAL=0
    local PASS=0

    check_lib() {
        local name=$1
        local file=$2
        ((TOTAL++))
        if [ -f "$LIBS_DIR/$file" ]; then
            echo -e "${GREEN}✓${NC} $name"
            ((PASS++))
        else
            echo -e "${RED}✗${NC} $name - Missing: $file"
        fi
    }

    check_lib "CodeMirror" "codemirror/$CODEMIRROR_VERSION/lib/codemirror.js"
    check_lib "InputMask" "jquery.inputmask/$INPUTMASK_VERSION/dist/jquery.inputmask.min.js"
    check_lib "Intl-Tel-Input" "jquery.intl-tel-input/$INTL_TEL_INPUT_VERSION/build/js/intlTelInput.min.js"
    check_lib "RateIt" "jquery.rateit/$RATEIT_VERSION/scripts/jquery.rateit.min.js"
    check_lib "Select2" "jquery.select2/$SELECT2_VERSION/dist/js/select2.min.js"
    check_lib "TextCounter" "jquery.textcounter/$TEXTCOUNTER_VERSION/textcounter.min.js"
    check_lib "Timepicker" "jquery.timepicker/$TIMEPICKER_VERSION/jquery.timepicker.min.js"
    check_lib "Popper.js" "popperjs/$POPPERJS_VERSION/dist/umd/popper.min.js"
    check_lib "Progress Tracker" "progress-tracker/$PROGRESS_TRACKER_VERSION/src/progress-tracker.js"
    check_lib "Signature Pad" "signature_pad/$SIGNATURE_PAD_VERSION/dist/signature_pad.min.js"
    check_lib "Tabby" "tabby/$TABBY_VERSION/dist/js/tabby.min.js"
    check_lib "Tippy.js" "tippyjs/$TIPPYJS_VERSION/dist/tippy.umd.min.js"

    echo ""
    echo "Total: $PASS / $TOTAL libraries installed"
}

set_permissions() {
    log_info "Setting file permissions..."
    chmod -R 755 "$LIBS_DIR"
    find "$LIBS_DIR" -type f -exec chmod 644 {} \;
    log_success "Permissions set"
}

# =============================================================================
# Main
# =============================================================================

main() {
    echo "=============================================="
    echo "  Webform External Libraries Installer"
    echo "=============================================="
    echo ""

    # Check requirements
    if ! command -v unzip &> /dev/null; then
        log_error "unzip is required but not installed"
        exit 1
    fi

    detect_downloader
    detect_directories

    echo ""
    echo "Installing libraries..."
    echo ""

    # Install all libraries
    install_codemirror
    install_inputmask
    install_intl_tel_input
    install_rateit
    install_select2
    install_textcounter
    install_timepicker
    install_popperjs
    install_progress_tracker
    install_signature_pad
    install_tabby
    install_tippyjs

    # Set permissions
    set_permissions

    # Verify
    verify_installation

    echo ""
    echo "=============================================="
    echo "  Summary"
    echo "=============================================="
    echo -e "Installed: ${GREEN}$INSTALLED${NC}"
    echo -e "Failed: ${RED}$FAILED${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Clear Drupal cache: drush cr"
    echo "  2. Check status: /admin/reports/status"
    echo ""
}

main "$@"
