# Drupal Core Update Quick Reference

One-page command reference for experienced administrators. For detailed explanations, see [DRUPAL_CORE_UPDATE.md](./DRUPAL_CORE_UPDATE.md).

---

## Pre-Update

```bash
# Backup database
drush sql:dump --gzip --result-file=../backup-$(date +%Y%m%d).sql.gz

# Backup files
tar -czvf ../drupal-backup-$(date +%Y%m%d).tar.gz --exclude='vendor' .

# Backup composer files (for quick rollback)
mkdir -p ../composer-backup && cp composer.json composer.lock ../composer-backup/

# Check current version
drush status | grep "Drupal version"

# Dry run
composer update --dry-run "drupal/core-*" --with-all-dependencies

# Enable maintenance mode
drush state:set system.maintenance_mode 1 -y && drush cr
```

---

## Update Core to 11.3.0

```bash
composer require \
  drupal/core-recommended:11.3.0 \
  drupal/core-composer-scaffold:11.3.0 \
  drupal/core-project-message:11.3.0 \
  --update-with-all-dependencies
```

---

## Post-Update

```bash
# Database updates
drush updb -y

# Clear cache
drush cr

# Disable maintenance mode
drush state:set system.maintenance_mode 0 -y && drush cr

# Verify version
drush status | grep "Drupal version"
```

---

## Full Sequence (Copy-Paste)

```bash
# Complete update sequence - run line by line
drush sql:dump --gzip --result-file=../backup-$(date +%Y%m%d-%H%M%S).sql.gz
mkdir -p ../composer-backup && cp composer.json composer.lock ../composer-backup/
drush state:set system.maintenance_mode 1 -y && drush cr
composer require drupal/core-recommended:11.3.0 drupal/core-composer-scaffold:11.3.0 drupal/core-project-message:11.3.0 --update-with-all-dependencies
drush updb -y && drush cr
drush state:set system.maintenance_mode 0 -y && drush cr
drush status
```

---

## Rollback

```bash
# Restore composer files (from backup created above)
cp ../composer-backup/composer.json composer.json
cp ../composer-backup/composer.lock composer.lock
composer install
drush cr

# OR if using Git
git checkout -- composer.json composer.lock
composer install
drush cr

# If database also needs restore
gunzip -c ../backup-YYYYMMDD-HHMMSS.sql.gz | drush sql:cli
drush cr
```

---

## Common Fixes

```bash
# Memory error
php -d memory_limit=-1 $(which composer) require ...

# Dependency conflict
composer why-not drupal/core-recommended:11.3.0

# Permission fix
chmod -R 775 web/sites/default/files

# Check errors
drush watchdog:show --severity=Error
```

---

_For detailed procedures and troubleshooting, see [DRUPAL_CORE_UPDATE.md](./DRUPAL_CORE_UPDATE.md)_
