# Webform External Libraries Installation Guide

This guide provides comprehensive instructions for installing all 12 external JavaScript/CSS libraries required by the Drupal Webform module. Local installation is preferred over CDN delivery for performance, privacy, and reliability.

## Overview

The Webform module uses external libraries to provide enhanced form elements such as code editors, input masks, rating widgets, and signature pads. While these libraries can load from CDN, local installation provides:

- **Faster load times** - Libraries served from your server
- **Privacy compliance** - No external requests to third-party CDNs
- **Offline functionality** - Works without external network access
- **Version control** - Exact versions guaranteed

---

## Prerequisites

| Requirement | Description |
|-------------|-------------|
| Drupal 11.x | With Webform module installed |
| SSH Access | Shell access to remote server |
| wget or curl | For downloading files |
| unzip | For extracting ZIP archives |
| drush | For clearing caches (optional) |

---

## Directory Structure

Libraries are installed in versioned subdirectories within `/libraries` at your Drupal root (or `/web/libraries` if using a web subdirectory structure). Each library has a `.version` file for tracking.

```
/libraries/
├── codemirror/
│   ├── .version                          # Contains "5.65.12"
│   └── 5.65.12/
│       ├── lib/
│       │   ├── codemirror.js
│       │   └── codemirror.css
│       └── mode/
│           ├── css/
│           ├── htmlmixed/
│           ├── javascript/
│           ├── php/
│           ├── twig/
│           ├── xml/
│           └── yaml/
├── jquery.inputmask/
│   ├── .version
│   └── 5.0.9/
│       └── dist/
│           └── jquery.inputmask.min.js
├── jquery.intl-tel-input/
│   ├── .version
│   └── 17.0.19/
│       └── build/
│           ├── js/
│           │   └── intlTelInput.min.js
│           └── css/
│               └── intlTelInput.min.css
├── jquery.rateit/
│   ├── .version
│   └── 1.1.5/
│       └── scripts/
│           └── jquery.rateit.min.js
├── jquery.select2/
│   ├── .version
│   └── 4.0.13/
│       └── dist/
│           ├── js/
│           │   └── select2.min.js
│           └── css/
│               └── select2.min.css
├── jquery.textcounter/
│   ├── .version
│   └── 0.9.1/
│       └── textcounter.min.js
├── jquery.timepicker/
│   ├── .version
│   └── 1.14.0/
│       ├── jquery.timepicker.min.js
│       └── jquery.timepicker.min.css
├── popperjs/
│   ├── .version
│   └── 2.11.6/
│       └── dist/
│           └── umd/
│               └── popper.min.js
├── progress-tracker/
│   ├── .version
│   └── 2.0.7/
│       └── src/
│           ├── progress-tracker.js
│           └── styles/
│               └── progress-tracker.css
├── signature_pad/
│   ├── .version
│   └── 2.3.0/
│       └── dist/
│           └── signature_pad.min.js
├── tabby/
│   ├── .version
│   └── 12.0.3/
│       └── dist/
│           ├── js/
│           │   └── tabby.min.js
│           └── css/
│               └── tabby.min.css
└── tippyjs/
    ├── .version
    └── 6.3.7/
        └── dist/
            ├── tippy.umd.min.js
            └── tippy.css
```

---

## Library Details

| Library | Version | Purpose | Webform Elements |
|---------|---------|---------|------------------|
| CodeMirror | 5.65.12 | Code/text editor | CodeMirror, HTML Editor |
| jQuery InputMask | 5.0.9 | Input formatting | Input masks |
| jQuery Intl-Tel-Input | 17.0.19 | Phone number input | Telephone (International) |
| jQuery RateIt | 1.1.5 | Star rating widget | Rating |
| jQuery Select2 | 4.0.13 | Enhanced select boxes | Select (Select2) |
| jQuery TextCounter | 0.9.1 | Character counter | Textfield, Textarea |
| jQuery Timepicker | 1.14.0 | Time selection | Time |
| Popper.js | 2.11.6 | Tooltip positioning | Help tooltips |
| Progress Tracker | 2.0.7 | Multi-step progress | Wizard progress bar |
| Signature Pad | 2.3.0 | Signature capture | Signature |
| Tabby | 12.0.3 | Tab navigation | Tabs element |
| Tippy.js | 6.3.7 | Tooltips | Help tooltips |

---

## Manual Installation Instructions

### 1. CodeMirror 5.65.12

CodeMirror provides syntax-highlighted code editing.

**Download:**
```bash
cd /tmp
wget https://github.com/codemirror/codemirror5/archive/refs/tags/5.65.12.zip -O codemirror.zip
unzip codemirror.zip
mkdir -p /var/www/drupal/libraries/codemirror/5.65.12
cp -r codemirror5-5.65.12/lib /var/www/drupal/libraries/codemirror/5.65.12/
cp -r codemirror5-5.65.12/mode /var/www/drupal/libraries/codemirror/5.65.12/
echo "5.65.12" > /var/www/drupal/libraries/codemirror/.version
rm -rf codemirror.zip codemirror5-5.65.12
```

**Required Files:**
- `5.65.12/lib/codemirror.js`
- `5.65.12/lib/codemirror.css`
- `5.65.12/mode/css/css.js`
- `5.65.12/mode/htmlmixed/htmlmixed.js`
- `5.65.12/mode/javascript/javascript.js`
- `5.65.12/mode/php/php.js`
- `5.65.12/mode/twig/twig.js`
- `5.65.12/mode/xml/xml.js`
- `5.65.12/mode/yaml/yaml.js`

---

### 2. jQuery InputMask 5.0.9

Provides input masking for formatted data entry.

**Download:**
```bash
mkdir -p /var/www/drupal/libraries/jquery.inputmask/5.0.9/dist
cd /var/www/drupal/libraries/jquery.inputmask/5.0.9/dist
wget https://cdnjs.cloudflare.com/ajax/libs/jquery.inputmask/5.0.9/jquery.inputmask.min.js
echo "5.0.9" > /var/www/drupal/libraries/jquery.inputmask/.version
```

**Required Files:**
- `5.0.9/dist/jquery.inputmask.min.js`

---

### 3. jQuery Intl-Tel-Input 17.0.19

International telephone input with country flags and validation.

**Download:**
```bash
cd /tmp
wget https://github.com/jackocnr/intl-tel-input/archive/refs/tags/v17.0.19.zip -O intl-tel-input.zip
unzip intl-tel-input.zip
mkdir -p /var/www/drupal/libraries/jquery.intl-tel-input/17.0.19
cp -r intl-tel-input-17.0.19/build /var/www/drupal/libraries/jquery.intl-tel-input/17.0.19/
echo "17.0.19" > /var/www/drupal/libraries/jquery.intl-tel-input/.version
rm -rf intl-tel-input.zip intl-tel-input-17.0.19
```

**Required Files:**
- `17.0.19/build/js/intlTelInput.min.js`
- `17.0.19/build/css/intlTelInput.min.css`
- `17.0.19/build/img/flags.png`
- `17.0.19/build/img/flags@2x.png`

---

### 4. jQuery RateIt 1.1.5

Star rating widget for form feedback.

**Download:**
```bash
mkdir -p /var/www/drupal/libraries/jquery.rateit/1.1.5/scripts
mkdir -p /var/www/drupal/libraries/jquery.rateit/1.1.5/styles
cd /var/www/drupal/libraries/jquery.rateit/1.1.5/scripts
wget https://cdnjs.cloudflare.com/ajax/libs/jquery.rateit/1.1.5/jquery.rateit.min.js
cd /var/www/drupal/libraries/jquery.rateit/1.1.5/styles
wget https://cdnjs.cloudflare.com/ajax/libs/jquery.rateit/1.1.5/rateit.css
echo "1.1.5" > /var/www/drupal/libraries/jquery.rateit/.version
```

**Required Files:**
- `1.1.5/scripts/jquery.rateit.min.js`
- `1.1.5/styles/rateit.css`

---

### 5. jQuery Select2 4.0.13

Enhanced select boxes with search and multi-select.

**Download:**
```bash
cd /tmp
wget https://github.com/select2/select2/archive/refs/tags/4.0.13.zip -O select2.zip
unzip select2.zip
mkdir -p /var/www/drupal/libraries/jquery.select2/4.0.13
cp -r select2-4.0.13/dist /var/www/drupal/libraries/jquery.select2/4.0.13/
echo "4.0.13" > /var/www/drupal/libraries/jquery.select2/.version
rm -rf select2.zip select2-4.0.13
```

**Required Files:**
- `4.0.13/dist/js/select2.min.js`
- `4.0.13/dist/css/select2.min.css`

---

### 6. jQuery TextCounter 0.9.1

Character and word counter for text fields.

**Download:**
```bash
cd /tmp
wget https://github.com/ractoon/jQuery-Text-Counter/archive/refs/tags/0.9.1.zip -O textcounter.zip
unzip textcounter.zip
mkdir -p /var/www/drupal/libraries/jquery.textcounter/0.9.1
cp jQuery-Text-Counter-0.9.1/textcounter.min.js /var/www/drupal/libraries/jquery.textcounter/0.9.1/
echo "0.9.1" > /var/www/drupal/libraries/jquery.textcounter/.version
rm -rf textcounter.zip jQuery-Text-Counter-0.9.1
```

**Required Files:**
- `0.9.1/textcounter.min.js`

---

### 7. jQuery Timepicker 1.14.0

Time selection dropdown widget.

**Download:**
```bash
cd /tmp
wget https://github.com/jonthornton/jquery-timepicker/archive/refs/tags/1.14.0.zip -O timepicker.zip
unzip timepicker.zip
mkdir -p /var/www/drupal/libraries/jquery.timepicker/1.14.0
cp jquery-timepicker-1.14.0/jquery.timepicker.min.js /var/www/drupal/libraries/jquery.timepicker/1.14.0/
cp jquery-timepicker-1.14.0/jquery.timepicker.min.css /var/www/drupal/libraries/jquery.timepicker/1.14.0/
echo "1.14.0" > /var/www/drupal/libraries/jquery.timepicker/.version
rm -rf timepicker.zip jquery-timepicker-1.14.0
```

**Required Files:**
- `1.14.0/jquery.timepicker.min.js`
- `1.14.0/jquery.timepicker.min.css`

---

### 8. Popper.js 2.11.6

Tooltip and popover positioning engine.

**Download:**
```bash
mkdir -p /var/www/drupal/libraries/popperjs/2.11.6/dist/umd
cd /var/www/drupal/libraries/popperjs/2.11.6/dist/umd
wget https://cdn.jsdelivr.net/npm/@popperjs/core@2.11.6/dist/umd/popper.min.js
echo "2.11.6" > /var/www/drupal/libraries/popperjs/.version
```

**Required Files:**
- `2.11.6/dist/umd/popper.min.js`

---

### 9. Progress Tracker 2.0.7

Visual progress indicator for multi-step forms.

**Download:**
```bash
cd /tmp
wget https://github.com/NigelOToole/progress-tracker/archive/refs/tags/2.0.7.zip -O progress-tracker.zip
unzip progress-tracker.zip
mkdir -p /var/www/drupal/libraries/progress-tracker/2.0.7
cp -r progress-tracker-2.0.7/src /var/www/drupal/libraries/progress-tracker/2.0.7/
rm -rf progress-tracker.zip progress-tracker-2.0.7
echo "2.0.7" > /var/www/drupal/libraries/progress-tracker/.version
```

**Required Files:**
- `2.0.7/src/progress-tracker.js`
- `2.0.7/src/styles/progress-tracker.css`

---

### 10. Signature Pad 2.3.0

HTML5 canvas-based signature capture.

**Download:**
```bash
cd /tmp
wget https://github.com/szimek/signature_pad/archive/refs/tags/v2.3.0.zip -O signature_pad.zip
unzip signature_pad.zip
mkdir -p /var/www/drupal/libraries/signature_pad/2.3.0
cp -r signature_pad-2.3.0/dist /var/www/drupal/libraries/signature_pad/2.3.0/
rm -rf signature_pad.zip signature_pad-2.3.0
echo "2.3.0" > /var/www/drupal/libraries/signature_pad/.version
```

**Required Files:**
- `2.3.0/dist/signature_pad.min.js`

---

### 11. Tabby 12.0.3

Lightweight tab navigation.

**Download:**
```bash
cd /tmp
wget https://github.com/cferdinandi/tabby/archive/refs/tags/12.0.3.zip -O tabby.zip
unzip tabby.zip
mkdir -p /var/www/drupal/libraries/tabby/12.0.3
cp -r tabby-12.0.3/dist /var/www/drupal/libraries/tabby/12.0.3/
rm -rf tabby.zip tabby-12.0.3
echo "12.0.3" > /var/www/drupal/libraries/tabby/.version
```

**Required Files:**
- `12.0.3/dist/js/tabby.min.js`
- `12.0.3/dist/css/tabby.min.css`

---

### 12. Tippy.js 6.3.7

Modern tooltip library built on Popper.js.

**Download:**
```bash
mkdir -p /var/www/drupal/libraries/tippyjs/6.3.7/dist
cd /var/www/drupal/libraries/tippyjs/6.3.7/dist
wget https://cdn.jsdelivr.net/npm/tippy.js@6.3.7/dist/tippy.umd.min.js
wget https://cdn.jsdelivr.net/npm/tippy.js@6.3.7/dist/tippy.css
echo "6.3.7" > /var/www/drupal/libraries/tippyjs/.version
```

**Required Files:**
- `6.3.7/dist/tippy.umd.min.js`
- `6.3.7/dist/tippy.css`

---

## Automated Installation

Use the provided installation scripts for automated setup:

### Bash (Linux/macOS)

```bash
# On remote server
cd /var/www/drupal
bash modules/custom/drupal_modules/scripts/install_webform_libraries.sh
```

### PowerShell (Windows)

```powershell
# Run from Drupal root
.\modules\custom\drupal_modules\scripts\Install-WebformLibraries.ps1
```

### Via SSH from Local Machine

```bash
ssh user@remote-server 'cd /var/www/drupal && bash modules/custom/drupal_modules/scripts/install_webform_libraries.sh'
```

---

## Verification

### 1. Check Status Report

Navigate to `/admin/reports/status` in Drupal. Look for the "Webform: External libraries" section. All 12 libraries should show as **Installed** (green) instead of **CDN** (yellow).

### 2. Verify Files Exist

Run this command to verify all critical files:

```bash
DRUPAL_ROOT="/var/www/drupal"
LIBS="$DRUPAL_ROOT/libraries"

echo "Checking library installations..."
[ -f "$LIBS/codemirror/5.65.12/lib/codemirror.js" ] && echo "✓ CodeMirror" || echo "✗ CodeMirror"
[ -f "$LIBS/jquery.inputmask/5.0.9/dist/jquery.inputmask.min.js" ] && echo "✓ InputMask" || echo "✗ InputMask"
[ -f "$LIBS/jquery.intl-tel-input/17.0.19/build/js/intlTelInput.min.js" ] && echo "✓ Intl-Tel-Input" || echo "✗ Intl-Tel-Input"
[ -f "$LIBS/jquery.rateit/1.1.5/scripts/jquery.rateit.min.js" ] && echo "✓ RateIt" || echo "✗ RateIt"
[ -f "$LIBS/jquery.select2/4.0.13/dist/js/select2.min.js" ] && echo "✓ Select2" || echo "✗ Select2"
[ -f "$LIBS/jquery.textcounter/0.9.1/textcounter.min.js" ] && echo "✓ TextCounter" || echo "✗ TextCounter"
[ -f "$LIBS/jquery.timepicker/1.14.0/jquery.timepicker.min.js" ] && echo "✓ Timepicker" || echo "✗ Timepicker"
[ -f "$LIBS/popperjs/2.11.6/dist/umd/popper.min.js" ] && echo "✓ Popper.js" || echo "✗ Popper.js"
[ -f "$LIBS/progress-tracker/2.0.7/src/progress-tracker.js" ] && echo "✓ Progress Tracker" || echo "✗ Progress Tracker"
[ -f "$LIBS/signature_pad/2.3.0/dist/signature_pad.min.js" ] && echo "✓ Signature Pad" || echo "✗ Signature Pad"
[ -f "$LIBS/tabby/12.0.3/dist/js/tabby.min.js" ] && echo "✓ Tabby" || echo "✗ Tabby"
[ -f "$LIBS/tippyjs/6.3.7/dist/tippy.umd.min.js" ] && echo "✓ Tippy.js" || echo "✗ Tippy.js"
```

### 3. Clear Drupal Cache

After installation, clear all caches:

```bash
drush cr
```

Or via admin UI: **Configuration > Development > Performance > Clear all caches**

### 4. Test Webform Elements

Create a test webform at `/admin/structure/webform/add` and add elements that use each library:

| Element to Add | Library Tested |
|----------------|----------------|
| CodeMirror (YAML) | CodeMirror |
| Telephone (International) | Intl-Tel-Input |
| Rating | RateIt |
| Select (Select2) | Select2 |
| Textfield with counter | TextCounter |
| Time | Timepicker |
| Signature | Signature Pad |
| Tabs container | Tabby |

---

## Troubleshooting

### Library Not Detected

**Symptoms:** Library shows as "CDN" or "Not installed" in status report.

**Solutions:**
1. **Check directory name** - Must match exactly (e.g., `jquery.select2` not `select2`)
2. **Check file structure** - Files must be in correct subdirectories
3. **Clear cache** - Run `drush cr` after any changes
4. **Check permissions** - Files must be readable by web server

```bash
# Fix permissions
chmod -R 755 /var/www/drupal/libraries
find /var/www/drupal/libraries -type f -exec chmod 644 {} \;
```

### Download Failures

**Alternative CDN URLs:**

| Library | Alternative URL |
|---------|-----------------|
| CodeMirror | `https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.12/codemirror.min.js` |
| InputMask | `https://unpkg.com/inputmask@5.0.9/dist/jquery.inputmask.min.js` |
| Select2 | `https://cdnjs.cloudflare.com/ajax/libs/select2/4.0.13/js/select2.min.js` |
| Tippy.js | `https://unpkg.com/tippy.js@6.3.7/dist/tippy-bundle.umd.min.js` |

### Version Mismatches

Check installed version against required:

```bash
# Check Webform's expected versions
drush pm:show webform | grep -i libraries
```

To upgrade a library:
1. Remove old library directory
2. Download new version following instructions above
3. Clear cache

### Permission Errors

```bash
# Check current ownership
ls -la /var/www/drupal/libraries

# Set correct ownership (adjust user/group as needed)
sudo chown -R www-data:www-data /var/www/drupal/libraries
```

---

## Webform Configuration

After installation, configure Webform library settings:

1. Navigate to `/admin/structure/webform/config/libraries`
2. Review "External libraries" section
3. Optionally disable CDN fallback warnings
4. Configure which libraries to load globally vs. per-form

---

## Library Update Process

To update libraries to newer versions:

1. **Backup existing libraries:**
   ```bash
   tar -czvf libraries-backup-$(date +%Y%m%d).tar.gz /var/www/drupal/libraries
   ```

2. **Check Webform compatibility:**
   - Review Webform module release notes for library version requirements
   - Test in development environment first

3. **Download new versions:**
   - Follow manual installation instructions with new version numbers
   - Or use update script: `bash scripts/update_webform_libraries.sh`

4. **Test thoroughly:**
   - Test all webform elements using the updated libraries
   - Check browser console for JavaScript errors

5. **Clear cache:**
   ```bash
   drush cr
   ```

---

## References

- [Webform Module Documentation](https://www.drupal.org/docs/contributed-modules/webform)
- [Webform Libraries Configuration](https://www.drupal.org/docs/contributed-modules/webform/webform-libraries)
- [CodeMirror 5 Documentation](https://codemirror.net/5/)
- [Select2 Documentation](https://select2.org/)
- [Signature Pad Documentation](https://github.com/szimek/signature_pad)
- [Tippy.js Documentation](https://atomiks.github.io/tippyjs/)

---

*Last updated: December 2024*
