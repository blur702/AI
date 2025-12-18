# Webform Libraries Quick Start

One-page quick reference for installing Webform external libraries. For detailed instructions, see [WEBFORM_LIBRARIES_INSTALLATION.md](./WEBFORM_LIBRARIES_INSTALLATION.md).

---

## One-Command Installation

### On Remote Server (SSH)

```bash
cd /var/www/drupal
bash modules/custom/drupal_modules/scripts/install_webform_libraries.sh
```

### Via SSH from Local Machine

```bash
ssh user@remote-server 'cd /var/www/drupal && bash modules/custom/drupal_modules/scripts/install_webform_libraries.sh'
```

### Windows PowerShell

```powershell
cd C:\path\to\drupal
.\modules\custom\drupal_modules\scripts\Install-WebformLibraries.ps1
```

---

## Manual Quick Install

Run these commands in order from your Drupal root:

```bash
# Set variables
DRUPAL_ROOT="/var/www/drupal"
LIBS="$DRUPAL_ROOT/libraries"
mkdir -p "$LIBS"
cd /tmp

# 1. CodeMirror 5.65.12
wget -q https://github.com/codemirror/codemirror5/archive/refs/tags/5.65.12.zip -O cm.zip
unzip -q cm.zip && mkdir -p "$LIBS/codemirror/5.65.12"
cp -r codemirror5-5.65.12/lib codemirror5-5.65.12/mode "$LIBS/codemirror/5.65.12/"
echo "5.65.12" > "$LIBS/codemirror/.version"
rm -rf cm.zip codemirror5-5.65.12

# 2. jQuery InputMask 5.0.9
mkdir -p "$LIBS/jquery.inputmask/5.0.9/dist"
wget -q https://cdnjs.cloudflare.com/ajax/libs/jquery.inputmask/5.0.9/jquery.inputmask.min.js \
  -O "$LIBS/jquery.inputmask/5.0.9/dist/jquery.inputmask.min.js"
echo "5.0.9" > "$LIBS/jquery.inputmask/.version"

# 3. Intl-Tel-Input 17.0.19
wget -q https://github.com/jackocnr/intl-tel-input/archive/refs/tags/v17.0.19.zip -O iti.zip
unzip -q iti.zip && mkdir -p "$LIBS/jquery.intl-tel-input/17.0.19"
cp -r intl-tel-input-17.0.19/build "$LIBS/jquery.intl-tel-input/17.0.19/"
echo "17.0.19" > "$LIBS/jquery.intl-tel-input/.version"
rm -rf iti.zip intl-tel-input-17.0.19

# 4. RateIt 1.1.5
mkdir -p "$LIBS/jquery.rateit/1.1.5/scripts" "$LIBS/jquery.rateit/1.1.5/styles"
wget -q https://cdnjs.cloudflare.com/ajax/libs/jquery.rateit/1.1.5/jquery.rateit.min.js \
  -O "$LIBS/jquery.rateit/1.1.5/scripts/jquery.rateit.min.js"
wget -q https://cdnjs.cloudflare.com/ajax/libs/jquery.rateit/1.1.5/rateit.css \
  -O "$LIBS/jquery.rateit/1.1.5/styles/rateit.css"
echo "1.1.5" > "$LIBS/jquery.rateit/.version"

# 5. Select2 4.0.13
wget -q https://github.com/select2/select2/archive/refs/tags/4.0.13.zip -O s2.zip
unzip -q s2.zip && mkdir -p "$LIBS/jquery.select2/4.0.13"
cp -r select2-4.0.13/dist "$LIBS/jquery.select2/4.0.13/"
echo "4.0.13" > "$LIBS/jquery.select2/.version"
rm -rf s2.zip select2-4.0.13

# 6. TextCounter 0.9.1
wget -q https://github.com/ractoon/jQuery-Text-Counter/archive/refs/tags/0.9.1.zip -O tc.zip
unzip -q tc.zip && mkdir -p "$LIBS/jquery.textcounter/0.9.1"
cp jQuery-Text-Counter-0.9.1/textcounter.min.js "$LIBS/jquery.textcounter/0.9.1/"
echo "0.9.1" > "$LIBS/jquery.textcounter/.version"
rm -rf tc.zip jQuery-Text-Counter-0.9.1

# 7. Timepicker 1.14.0
wget -q https://github.com/jonthornton/jquery-timepicker/archive/refs/tags/1.14.0.zip -O tp.zip
unzip -q tp.zip && mkdir -p "$LIBS/jquery.timepicker/1.14.0"
cp jquery-timepicker-1.14.0/jquery.timepicker.min.* "$LIBS/jquery.timepicker/1.14.0/"
echo "1.14.0" > "$LIBS/jquery.timepicker/.version"
rm -rf tp.zip jquery-timepicker-1.14.0

# 8. Popper.js 2.11.6
mkdir -p "$LIBS/popperjs/2.11.6/dist/umd"
wget -q https://cdn.jsdelivr.net/npm/@popperjs/core@2.11.6/dist/umd/popper.min.js \
  -O "$LIBS/popperjs/2.11.6/dist/umd/popper.min.js"
echo "2.11.6" > "$LIBS/popperjs/.version"

# 9. Progress Tracker 2.0.7
wget -q https://github.com/NigelOToole/progress-tracker/archive/refs/tags/2.0.7.zip -O pt.zip
unzip -q pt.zip && mkdir -p "$LIBS/progress-tracker/2.0.7"
cp -r progress-tracker-2.0.7/src "$LIBS/progress-tracker/2.0.7/"
echo "2.0.7" > "$LIBS/progress-tracker/.version"
rm -rf pt.zip progress-tracker-2.0.7

# 10. Signature Pad 2.3.0
wget -q https://github.com/szimek/signature_pad/archive/refs/tags/v2.3.0.zip -O sp.zip
unzip -q sp.zip && mkdir -p "$LIBS/signature_pad/2.3.0"
cp -r signature_pad-2.3.0/dist "$LIBS/signature_pad/2.3.0/"
echo "2.3.0" > "$LIBS/signature_pad/.version"
rm -rf sp.zip signature_pad-2.3.0

# 11. Tabby 12.0.3
wget -q https://github.com/cferdinandi/tabby/archive/refs/tags/12.0.3.zip -O tabby.zip
unzip -q tabby.zip && mkdir -p "$LIBS/tabby/12.0.3"
cp -r tabby-12.0.3/dist "$LIBS/tabby/12.0.3/"
echo "12.0.3" > "$LIBS/tabby/.version"
rm -rf tabby.zip tabby-12.0.3

# 12. Tippy.js 6.3.7
mkdir -p "$LIBS/tippyjs/6.3.7/dist"
wget -q https://cdn.jsdelivr.net/npm/tippy.js@6.3.7/dist/tippy.umd.min.js \
  -O "$LIBS/tippyjs/6.3.7/dist/tippy.umd.min.js"
wget -q https://cdn.jsdelivr.net/npm/tippy.js@6.3.7/dist/tippy.css \
  -O "$LIBS/tippyjs/6.3.7/dist/tippy.css"
echo "6.3.7" > "$LIBS/tippyjs/.version"

# Set permissions
chmod -R 755 "$LIBS"
find "$LIBS" -type f -exec chmod 644 {} \;

echo "Done! Clear cache with: drush cr"
```

---

## Post-Installation

```bash
# 1. Clear Drupal cache
drush cr

# 2. Verify installation
drush status-report | grep -i webform

# 3. Check status page
# Navigate to: /admin/reports/status
```

---

## Verify Installation

```bash
LIBS="/var/www/drupal/libraries"
echo "Library Status:"
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

---

## Quick Fixes

```bash
# Permission fix
sudo chown -R www-data:www-data /var/www/drupal/libraries
chmod -R 755 /var/www/drupal/libraries

# Clear cache
drush cr

# Check Webform status
drush pm:show webform
```

---

## Library Versions

| Library | Version | Size |
|---------|---------|------|
| CodeMirror | 5.65.12 | ~2MB |
| jQuery InputMask | 5.0.9 | ~100KB |
| jQuery Intl-Tel-Input | 17.0.19 | ~500KB |
| jQuery RateIt | 1.1.5 | ~50KB |
| jQuery Select2 | 4.0.13 | ~300KB |
| jQuery TextCounter | 0.9.1 | ~10KB |
| jQuery Timepicker | 1.14.0 | ~100KB |
| Popper.js | 2.11.6 | ~50KB |
| Progress Tracker | 2.0.7 | ~30KB |
| Signature Pad | 2.3.0 | ~20KB |
| Tabby | 12.0.3 | ~40KB |
| Tippy.js | 6.3.7 | ~100KB |

**Total: ~3.3MB**

---

*For detailed instructions, see [WEBFORM_LIBRARIES_INSTALLATION.md](./WEBFORM_LIBRARIES_INSTALLATION.md)*
