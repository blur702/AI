# Drupal Core Update Guide - 11.2.x to 11.3.0

This guide provides a complete, production-ready procedure for updating Drupal core from version 11.2.x to 11.3.0. Drupal 11.3.0 marks the beginning of a new minor release branch that will receive security coverage until Drupal 11.5.0 is released.

**Official Release Notes**: [Drupal 11.3.0](https://www.drupal.org/project/drupal/releases/11.3.0)

---

## Prerequisites

Before starting the update, verify the following requirements:

| Requirement | Minimum | Recommended | Verification Command |
|-------------|---------|-------------|---------------------|
| Composer | 2.x | 2.7+ | `composer --version` |
| Drush | 12.4.3 | 13.x | `drush --version` |
| PHP | 8.3 | 8.4 | `php --version` |
| SSH Access | Required | - | `ssh user@server` |
| Database Backup | Complete | - | See below |

---

## Pre-Update Preparation

### 1. Backup Database

Create a timestamped database backup:

```bash
drush sql:dump --gzip --result-file=../backup-$(date +%Y%m%d-%H%M%S).sql.gz
```

Or without compression:

```bash
drush sql:dump > ../backup-$(date +%Y%m%d-%H%M%S).sql
```

### 2. Backup Files

Backup the entire Drupal directory:

```bash
# Using tar
tar -czvf ../drupal-backup-$(date +%Y%m%d).tar.gz --exclude='vendor' --exclude='node_modules' .

# Or using rsync for incremental backups
rsync -avz --exclude='vendor' --exclude='node_modules' ./ ../drupal-backup/
```

### 3. Backup Composer Files

Create a separate backup of composer files for quick rollback:

```bash
# Create backup directory if it doesn't exist
mkdir -p ../composer-backup

# Copy composer files
cp composer.json composer.lock ../composer-backup/
```

**Note**: This allows fast rollback if the composer update fails, without needing to extract from a full backup archive.

### 4. Verify Current Environment

Check current Drupal version and configuration:

```bash
# Check Drupal version
drush status

# Check current core package version
composer show drupal/core-recommended | grep version

# List all Drupal packages
composer show 'drupal/*'
```

### 5. Dry-Run the Update

Preview what composer will do without making changes:

```bash
composer update --dry-run "drupal/core-*" --with-all-dependencies
```

### 6. Security Audit

Check for known vulnerabilities before updating:

```bash
# Composer security audit
composer audit

# Drupal security status
drush pm:security
```

### 7. Enable Maintenance Mode

Put the site in maintenance mode before updating:

```bash
drush state:set system.maintenance_mode 1 --yes
drush cache:rebuild
```

Verify maintenance mode is active by visiting the site in a browser.

---

## Core Update Procedure

Choose one of the following update options:

### Option A: Pin to Exact 11.3.0 Release (Recommended)

Use this option to update to the exact 11.3.0 release:

```bash
composer require \
  drupal/core-recommended:11.3.0 \
  drupal/core-composer-scaffold:11.3.0 \
  drupal/core-project-message:11.3.0 \
  --update-with-all-dependencies
```

**When to use**: Production environments where you want precise control over the version deployed.

### Option B: Latest 11.3.x Patch Release

Use this option to get the latest patch release in the 11.3.x branch:

```bash
composer update "drupal/core-*" --with-all-dependencies
```

**When to use**: Development environments or when you want automatic patch updates within the 11.3.x branch.

### Expected Output

Composer will:
1. Download new package versions
2. Update the lock file
3. Install updated packages
4. Run any post-install scripts

Watch for any error messages during this process.

---

## Database Updates

After the composer update completes, run database updates:

### 1. Check Pending Updates

```bash
drush updatedb:status
```

This shows any database schema changes that need to be applied.

### 2. Run Database Updates

```bash
drush updatedb -y
```

Or using the alias:

```bash
drush updb -y
```

### 3. Clear All Caches

```bash
drush cache:rebuild
```

Or using the alias:

```bash
drush cr
```

### Alternative: Browser-Based Updates

If Drush is unavailable, navigate to `/update.php` in your browser and follow the on-screen instructions.

---

## Post-Update Verification

### 1. Verify Drupal Version

**Via Command Line:**

```bash
drush status
```

Look for `Drupal version : 11.3.0` in the output.

**Via Composer:**

```bash
composer show drupal/core-recommended | grep version
```

**Via Browser:**

Navigate to `/admin/reports/status` and check the Drupal version.

### 2. Test Critical Functionality

```bash
# Run cron
drush core:cron

# Check for errors in logs
drush watchdog:show --severity=Error

# Show recent log entries
drush watchdog:show --count=20
```

### 3. Review Scaffold File Changes

Composer may have updated scaffold files. Review changes to:

- `.htaccess` (Apache)
- `robots.txt`
- `index.php`
- `web.config` (IIS)

If you have custom modifications to these files, you may need to reapply them.

### 4. Verify Custom Modules

Test all custom modules for compatibility:

```bash
# List all enabled custom modules
drush pm:list --type=module --status=enabled --no-core

# Check for any module errors
drush pm:list --status=enabled --format=table
```

---

## Deactivate Maintenance Mode

Once verification is complete, disable maintenance mode:

```bash
drush state:set system.maintenance_mode 0 --yes
drush cache:rebuild
```

Verify the site is accessible to visitors.

---

## Rollback Procedures

### If Update Fails During Composer

If the composer update fails mid-process:

```bash
# Restore composer files from backup (created in step 3)
cp ../composer-backup/composer.json composer.json
cp ../composer-backup/composer.lock composer.lock

# Reinstall original dependencies
composer install

# Clear caches
drush cache:rebuild

# Verify site functionality
drush status
```

**Alternative (if using Git)**:

```bash
# Restore composer files from version control
git checkout -- composer.json composer.lock

# Reinstall original dependencies
composer install

# Clear caches
drush cache:rebuild
```

### If Update Completes But Site Breaks

If the site is broken after a successful update:

```bash
# Restore database from backup
drush sql:cli < ../backup-YYYYMMDD-HHMMSS.sql

# Or if compressed
gunzip -c ../backup-YYYYMMDD-HHMMSS.sql.gz | drush sql:cli

# Restore codebase from backup
rm -rf vendor web/core
tar -xzf ../drupal-backup-YYYYMMDD.tar.gz

# Reinstall dependencies
composer install

# Clear caches
drush cache:rebuild

# Verify site is functional
drush status
```

### Git-Based Rollback

If using version control:

```bash
# Identify the commit to revert
git log --oneline -5

# Revert the update commit
git revert <commit-hash>

# Sync dependencies
composer install

# Run any necessary database updates
drush updatedb -y
drush cache:rebuild
```

---

## Quick Reference Cheat Sheet

| Step | Command | Purpose |
|------|---------|---------|
| 1 | `drush sql:dump > backup-$(date +%Y%m%d).sql` | Backup database |
| 2 | `mkdir -p ../composer-backup && cp composer.json composer.lock ../composer-backup/` | Backup composer files |
| 3 | `drush state:set system.maintenance_mode 1 -y && drush cr` | Enable maintenance mode |
| 4 | `composer require drupal/core-recommended:11.3.0 drupal/core-composer-scaffold:11.3.0 drupal/core-project-message:11.3.0 --update-with-all-dependencies` | Update core |
| 5 | `drush updb -y && drush cr` | Update database and cache |
| 6 | `drush state:set system.maintenance_mode 0 -y && drush cr` | Disable maintenance mode |
| 7 | `drush status` | Verify version |

---

## Troubleshooting

### Composer Memory Errors

If composer runs out of memory:

```bash
# Run with unlimited memory
php -d memory_limit=-1 $(which composer) require drupal/core-recommended:11.3.0 \
  drupal/core-composer-scaffold:11.3.0 \
  drupal/core-project-message:11.3.0 \
  --update-with-all-dependencies

# Or set memory limit in php.ini temporarily
COMPOSER_MEMORY_LIMIT=-1 composer require ...
```

### Dependency Conflicts

If composer reports dependency conflicts:

```bash
# Diagnose why a version can't be installed
composer why-not drupal/core-recommended:11.3.0

# See what depends on conflicting packages
composer depends drupal/core-recommended

# Update conflicting modules first
composer update drupal/conflicting_module
```

### Database Update Failures

If database updates fail:

```bash
# Check detailed error logs
drush watchdog:show --severity=Error --count=50

# Run updates for a specific module
drush updatedb --module=module_name

# Force update entity schema
drush entity:updates
```

### Permission Errors

If you encounter file permission errors:

```bash
# Verify ownership (adjust user/group as needed)
chown -R www-data:www-data .

# Fix file permissions
find . -type f -exec chmod 644 {} \;
find . -type d -exec chmod 755 {} \;

# Ensure sites/default/files is writable
chmod -R 775 web/sites/default/files
```

### Scaffold Files Overwritten

If custom modifications to scaffold files were lost:

```bash
# Review what scaffold files changed
git diff web/.htaccess web/robots.txt web/index.php

# Reapply custom modifications manually
# Then commit the changes
```

---

## Additional Considerations

### Custom Module Compatibility

Before updating production:

1. Test custom modules (like `congressional_query`) on a staging environment
2. Review module code for deprecated API usage
3. Check the module's `.info.yml` for core version compatibility
4. Run automated tests if available

### Contributed Module Updates

Check for compatible versions of contributed modules:

```bash
# Check for available updates
drush pm:list --status=enabled --format=table

# Update specific contrib modules
composer update drupal/module_name

# Update all contrib modules
composer update 'drupal/*'
```

### Drush Version Upgrade

Consider upgrading to Drush 13 for latest features:

```bash
composer require drush/drush:^13
```

### Commit Lock File

Always commit the updated `composer.lock` to version control:

```bash
git add composer.json composer.lock
git commit -m "Update Drupal core to 11.3.0"
git push
```

### Testing Environment

**Always test on staging before production:**

1. Clone production database to staging
2. Run the update procedure on staging
3. Test all critical functionality
4. Monitor for errors for 24-48 hours
5. Then proceed with production update

---

## Remote Server Notes

Since the Drupal installation is on a remote server:

### SSH Connection

Connect to the remote server before running commands:

```bash
ssh username@your-server.com
cd /path/to/drupal
```

### Server-Specific Considerations

After updating, you may need to:

```bash
# Restart PHP-FPM (if applicable)
sudo systemctl restart php8.3-fpm

# Restart Nginx (if applicable)
sudo systemctl restart nginx

# Restart Apache (if applicable)
sudo systemctl restart apache2
```

### Congressional Query Module

The Congressional Query module's SSH configuration at `/admin/config/services/congressional-query` should continue to work after the core update. However, verify:

1. SSH tunnel connectivity
2. Ollama LLM service connection
3. Weaviate database connection

Test via the Connection Status block or admin dashboard.

---

## References

- [Drupal 11.3.0 Release Notes](https://www.drupal.org/project/drupal/releases/11.3.0)
- [Updating Drupal Core via Composer](https://www.drupal.org/docs/updating-drupal/updating-drupal-core-via-composer)
- [Drush Commands Documentation](https://www.drush.org/latest/commands/)
- [Composer Documentation](https://getcomposer.org/doc/)
- [Drupal Security Advisories](https://www.drupal.org/security)

---

*Last updated: December 2024*
