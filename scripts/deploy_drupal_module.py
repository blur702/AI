#!/usr/bin/env python3
"""
Deploys the page_password_protect Drupal module to the remote server.

Provides SSH-based commands, file uploads, Drush invocation, verification,
backup creation, and rollback support. Logs to a timestamped file under logs/.
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from api_gateway.config import settings
from api_gateway.services.drupal_ssh import (
    SSHCommandError,
    build_pscp_command,
    run_drupal_ssh,
)
from api_gateway.utils.logger import get_logger

SCRIPT_LOGGER = get_logger("deploy.drupal_module")

# Full path to Drush on the remote server (not in PATH)
DRUSH_PATH = "/var/www/drupal/vendor/bin/drush"


def ensure_logs_dir() -> Path:
    logs = Path("logs")
    logs.mkdir(exist_ok=True)
    return logs


def attach_deploy_log(verbose: bool = False) -> Path:
    log_dir = ensure_logs_dir()
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    log_file = log_dir / f"drupal_deployment_{timestamp}.log"
    handler = logging.FileHandler(log_file)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    SCRIPT_LOGGER.addHandler(handler)
    if verbose:
        SCRIPT_LOGGER.setLevel(logging.DEBUG)
    return log_file


@dataclass
class DeploymentState:
    commands: List[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)
    backup_id: Optional[str] = None
    uploaded_files: int = 0
    verified: bool = False

    def add_command(self, command: str) -> None:
        self.commands.append(command)

    def report(self) -> Dict[str, str]:
        duration = (datetime.utcnow() - self.start_time).total_seconds()
        return {
            "duration_seconds": f"{duration:.2f}",
            "uploaded_files": str(self.uploaded_files),
            "commands_executed": str(len(self.commands)),
            "backup_id": self.backup_id or "none",
            "verified": str(self.verified),
        }


class DrupalModuleDeployer:
    def __init__(
        self,
        module_name: str,
        local_path: Path,
        remote_root: str,
        dry_run: bool = False,
        force: bool = False,
        skip_backup: bool = False,
    ):
        self.module_name = module_name
        self.local_path = local_path
        self.remote_root = remote_root.rstrip("/")
        self.remote_module_path = f"{self.remote_root}/{self.module_name}"
        self.dry_run = dry_run
        self.force = force
        self.skip_backup = skip_backup
        self.state = DeploymentState()

    def run(self, command: str, **kwargs) -> subprocess.CompletedProcess:
        self.state.add_command(command)
        if self.dry_run:
            SCRIPT_LOGGER.info("[dry-run] %s", command)
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        return run_drupal_ssh(command, **kwargs)

    def remote_module_exists(self) -> bool:
        try:
            self.run(f"test -d {self.remote_module_path}")
            return True
        except SSHCommandError:
            return False

    def create_remote_directory(self) -> None:
        self.run(f"mkdir -p {self.remote_module_path}")

    def upload_module_files(self) -> None:
        remote_temp = f"/tmp/{self.module_name}_upload"
        self.run(f"rm -rf {remote_temp}")
        self.run(f"mkdir -p {remote_temp}")
        command = build_pscp_command(self.local_path, remote_temp)
        SCRIPT_LOGGER.info("Uploading module files...")
        if self.dry_run:
            count = sum(1 for _ in self.local_path.rglob("*") if _.is_file())
            self.state.uploaded_files = count
            return
        self.state.add_command("pscp upload")
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise DeploymentError(f"File upload failed: {proc.stderr.strip()}")
        self.run(f"rm -rf {self.remote_module_path}/*")
        self.run(f"cp -r {remote_temp}/* {self.remote_module_path}/")
        self.run(f"rm -rf {remote_temp}")
        count = sum(1 for _ in self.local_path.rglob("*") if _.is_file())
        self.state.uploaded_files = count
        SCRIPT_LOGGER.info("Uploaded %d files", count)

    def set_permissions(self) -> None:
        self.run(f"chmod -R 755 {self.remote_module_path}")
        self.run(f"chown -R www-data:www-data {self.remote_module_path}")

    def enable_module(self) -> None:
        self.run(f"cd {self.remote_root} && {DRUSH_PATH} pm:enable {self.module_name} -y")

    def run_database_updates(self) -> None:
        self.run(f"cd {self.remote_root} && {DRUSH_PATH} updatedb -y")

    def clear_caches(self) -> None:
        self.run(f"cd {self.remote_root} && {DRUSH_PATH} cache:rebuild")

    def verify_installation(self) -> None:
        if self.dry_run:
            SCRIPT_LOGGER.info("Dry-run mode: skipping verification steps.")
            self.state.verified = True
            return
        stdout = self.run(
            f"cd {self.remote_root} && {DRUSH_PATH} pm:list --status=enabled --type=module | grep {self.module_name}"
        ).stdout
        if self.module_name not in stdout:
            raise DeploymentError("Module verification failed")
        self.state.verified = True
        self.run(f'cd {self.remote_root} && {DRUSH_PATH} sql-query "DESCRIBE page_password_protect"')
        self.run(f'cd {self.remote_root} && {DRUSH_PATH} field:list node | grep field_page_password_protected')

    def create_backup(self) -> str:
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        backup_id = timestamp
        backup_path = f"/tmp/drupal_module_backups/{self.module_name}_{backup_id}"
        self.run(f"mkdir -p {backup_path}")
        self.run(f"cp -r {self.remote_module_path} {backup_path}/module")
        self.run(
            f"cd {self.remote_root} && {DRUSH_PATH} sql-dump --result-file={backup_path}/db_backup_{backup_id}.sql"
        )
        metadata = {
            "module": self.module_name,
            "timestamp": backup_id,
            "path": backup_path,
        }
        SCRIPT_LOGGER.debug("Backup metadata: %s", metadata)
        SCRIPT_LOGGER.info("Created backup %s", backup_id)
        self.state.backup_id = backup_id
        return backup_id

    def rollback(self, backup_id: str) -> None:
        backup_path = f"/tmp/drupal_module_backups/{self.module_name}_{backup_id}"
        self.run(f"rm -rf {self.remote_module_path}")
        self.run(f"cp -r {backup_path}/module {self.remote_module_path}")
        self.run(
            f"cd {self.remote_root} && {DRUSH_PATH} sql-cli < {backup_path}/db_backup_{backup_id}.sql"
        )
        self.clear_caches()
        SCRIPT_LOGGER.info("Rolled back deployment from backup %s", backup_id)

    def list_backups(self) -> List[str]:
        try:
            stdout = self.run("ls /tmp/drupal_module_backups").stdout
        except SSHCommandError:
            return []
        return [line.strip() for line in stdout.strip().splitlines() if line.strip()]

    def deploy(self) -> Dict[str, str]:
        SCRIPT_LOGGER.info("Deploying module %s to %s", self.module_name, self.remote_root)
        if self.remote_module_exists() and not self.force:
            SCRIPT_LOGGER.info("Remote module already exists, creating backup.")
            if not self.skip_backup:
                self.create_backup()
        elif self.dry_run:
            SCRIPT_LOGGER.info("Dry-run: skipping backup.")

        self.create_remote_directory()
        self.upload_module_files()
        self.set_permissions()
        self.enable_module()
        self.run_database_updates()
        self.clear_caches()
        self.verify_installation()
        return self.state.report()


class DeploymentError(Exception):
    """Represents a failure during deployment."""
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy Drupal module via SSH + Drush")
    parser.add_argument("--module-name", default="page_password_protect")
    parser.add_argument(
        "--local-path",
        default="drupal_modules/page_password_protect",
        help="Local module directory",
    )
    parser.add_argument(
        "--remote-path",
        default=settings.DRUPAL_WEB_ROOT + "/modules/custom",
        help="Remote modules directory",
    )
    parser.add_argument("--dry-run", action="store_true", help="Log actions without executing")
    parser.add_argument("--force", action="store_true", help="Force deployment even if module exists")
    parser.add_argument("--skip-backup", action="store_true", help="Skip creating remote backup")
    parser.add_argument("--rollback", help="Rollback to backup ID")
    parser.add_argument("--list-backups", action="store_true", help="List remote backups")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    attach_deploy_log(verbose=args.verbose)

    local_path = Path(args.local_path).resolve()
    if not local_path.exists():
        SCRIPT_LOGGER.error("Local path %s does not exist", local_path)
        sys.exit(1)

    deployer = DrupalModuleDeployer(
        module_name=args.module_name,
        local_path=local_path,
        remote_root=args.remote_path,
        dry_run=args.dry_run,
        force=args.force,
        skip_backup=args.skip_backup,
    )

    try:
        if args.list_backups:
            backups = deployer.list_backups()
            SCRIPT_LOGGER.info("Remote backups: %s", backups or "none")
            return
        if args.rollback:
            deployer.rollback(args.rollback)
            return
        report = deployer.deploy()
        SCRIPT_LOGGER.info("Deployment report: %s", report)
    except (DeploymentError, SSHCommandError) as exc:
        SCRIPT_LOGGER.error("Deployment failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
