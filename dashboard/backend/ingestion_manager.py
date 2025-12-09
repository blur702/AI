"""
Ingestion manager for Weaviate documentation and code indexing.

Manages ingestion state, orchestrates ingestion operations, and emits
WebSocket events for real-time progress updates.
"""

from __future__ import annotations

import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# Add project root to path for imports
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from api_gateway.services.weaviate_connection import (
    WeaviateConnection,
    DOCUMENTATION_COLLECTION_NAME,
    CODE_ENTITY_COLLECTION_NAME,
    DRUPAL_API_COLLECTION_NAME,
    MDN_JAVASCRIPT_COLLECTION_NAME,
    MDN_WEBAPIS_COLLECTION_NAME,
)
from api_gateway.services.doc_ingestion import (
    ingest_documentation,
    collection_status as doc_collection_status,
)
from api_gateway.services.code_ingestion import (
    ingest_code_entities,
    collection_status as code_collection_status,
)
from api_gateway.services.drupal_api_schema import (
    get_collection_stats as drupal_collection_stats,
)
from api_gateway.services.drupal_scraper import (
    scrape_drupal_api,
    ScrapeConfig as DrupalScrapeConfig,
)
from api_gateway.services.mdn_schema import (
    get_mdn_javascript_stats,
    get_mdn_webapis_stats,
)
from api_gateway.services.mdn_javascript_scraper import (
    scrape_mdn_javascript,
    ScrapeConfig as MdnJsScrapeConfig,
)
from api_gateway.services.mdn_webapis_scraper import (
    scrape_mdn_webapis,
    ScrapeConfig as MdnWebScrapeConfig,
)


EmitCallback = Callable[[str, Dict[str, Any]], None]
PauseCheck = Callable[[], bool]


class IngestionManager:
    """
    Manages Weaviate ingestion operations with thread-safe state tracking.

    Provides:
    - Concurrent ingestion prevention (mutex)
    - Progress callbacks via WebSocket
    - Cancellation support
    - Collection status retrieval
    """

    def __init__(self, emit_callback: EmitCallback):
        """
        Initialize the ingestion manager.

        Args:
            emit_callback: Function to emit WebSocket events.
                          Signature: emit_callback(event_name, data_dict)
        """
        self.emit = emit_callback
        self.is_running = False
        self.paused = False
        self.task_id: Optional[str] = None
        self.current_type: Optional[str] = None
        self.started_at: Optional[float] = None
        self.cancel_requested = False
        self.lock = threading.Lock()
        self._stats: Dict[str, Any] = {}

    def get_status(self) -> Dict[str, Any]:
        """
        Get current ingestion status and collection statistics.

        Returns:
            Dictionary with:
            - is_running: Whether ingestion is in progress
            - task_id: Current task ID (if running)
            - current_type: Current ingestion type (if running)
            - started_at: Unix timestamp when ingestion started
            - collections: Statistics for each collection
        """
        collections = {
            "documentation": {"exists": False, "object_count": 0},
            "code_entity": {"exists": False, "object_count": 0},
            "drupal_api": {"exists": False, "object_count": 0, "entity_counts": {}},
            "mdn_javascript": {"exists": False, "object_count": 0},
            "mdn_webapis": {"exists": False, "object_count": 0},
        }

        try:
            with WeaviateConnection() as client:
                # Documentation collection
                if client.collections.exists(DOCUMENTATION_COLLECTION_NAME):
                    doc_stats = doc_collection_status(client)
                    collections["documentation"] = {
                        "exists": True,
                        "object_count": doc_stats.get("object_count", 0),
                    }

                # Code entity collection
                if client.collections.exists(CODE_ENTITY_COLLECTION_NAME):
                    code_stats = code_collection_status(client)
                    collections["code_entity"] = {
                        "exists": code_stats.get("exists", True),
                        "object_count": code_stats.get("object_count", 0),
                    }

                # Drupal API collection
                if client.collections.exists(DRUPAL_API_COLLECTION_NAME):
                    drupal_stats = drupal_collection_stats(client)
                    collections["drupal_api"] = {
                        "exists": drupal_stats.get("exists", True),
                        "object_count": drupal_stats.get("object_count", 0),
                        "entity_counts": drupal_stats.get("entity_counts", {}),
                    }

                # MDN JavaScript collection
                if client.collections.exists(MDN_JAVASCRIPT_COLLECTION_NAME):
                    mdn_js_stats = get_mdn_javascript_stats(client)
                    collections["mdn_javascript"] = {
                        "exists": mdn_js_stats.get("exists", True),
                        "object_count": mdn_js_stats.get("object_count", 0),
                    }

                # MDN Web APIs collection
                if client.collections.exists(MDN_WEBAPIS_COLLECTION_NAME):
                    mdn_web_stats = get_mdn_webapis_stats(client)
                    collections["mdn_webapis"] = {
                        "exists": mdn_web_stats.get("exists", True),
                        "object_count": mdn_web_stats.get("object_count", 0),
                    }
        except Exception as exc:
            # Return status even if Weaviate is unavailable
            collections["error"] = str(exc)

        return {
            "is_running": self.is_running,
            "paused": self.paused,
            "task_id": self.task_id,
            "current_type": self.current_type,
            "started_at": self.started_at,
            "collections": collections,
        }

    def start_ingestion(
        self,
        types: List[str],
        reindex: bool = False,
        code_service: str = "all",
        drupal_limit: Optional[int] = None,
        mdn_limit: Optional[int] = None,
        mdn_section: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Start ingestion in the background.

        Args:
            types: List of types to ingest ("documentation", "code", "drupal", "mdn_javascript", "mdn_webapis")
            reindex: If True, delete existing collections before ingesting
            code_service: For code ingestion: "core", "all", or specific service
            drupal_limit: For drupal ingestion: max entities to scrape (None = unlimited)
            mdn_limit: For MDN ingestion: max documents to scrape (None = unlimited)
            mdn_section: For mdn_webapis: filter by section ("css", "html", "webapi")

        Returns:
            Dictionary with success status and task_id or error message.
        """
        with self.lock:
            if self.is_running:
                return {
                    "success": False,
                    "error": "Ingestion already in progress",
                    "task_id": self.task_id,
                }

            self.is_running = True
            self.paused = False
            self.task_id = str(uuid.uuid4())
            self.cancel_requested = False
            self.started_at = time.time()
            self._stats = {}

        # Return immediately, ingestion runs in background
        return {
            "success": True,
            "task_id": self.task_id,
            "message": "Ingestion started",
        }

    def run_ingestion(
        self,
        types: List[str],
        reindex: bool = False,
        code_service: str = "all",
        drupal_limit: Optional[int] = None,
        mdn_limit: Optional[int] = None,
        mdn_section: Optional[str] = None,
    ) -> None:
        """
        Run the actual ingestion (called from background task).

        Args:
            types: List of types to ingest
            reindex: Whether to force reindex
            code_service: Code service target
            drupal_limit: Max entities for Drupal scraper
            mdn_limit: Max documents for MDN scrapers
            mdn_section: Section filter for mdn_webapis
        """
        task_id = self.task_id
        start_time = self.started_at or time.time()

        self.emit("ingestion_started", {
            "task_id": task_id,
            "types": types,
            "reindex": reindex,
        })

        all_stats: Dict[str, Any] = {}
        success = True

        try:
            with WeaviateConnection() as client:
                # Process documentation
                if "documentation" in types:
                    if self.cancel_requested or self._wait_if_paused():
                        raise InterruptedError("Cancelled")

                    self.current_type = "documentation"
                    doc_stats = ingest_documentation(
                        client,
                        force_reindex=reindex,
                        progress_callback=lambda phase, current, total, msg: self._emit_progress(
                            task_id, "documentation", phase, current, total, msg
                        ),
                        check_cancelled=lambda: self.cancel_requested,
                        check_paused=self.check_paused,
                    )
                    all_stats["documentation"] = doc_stats

                    self.emit("ingestion_phase_complete", {
                        "task_id": task_id,
                        "type": "documentation",
                        "stats": doc_stats,
                    })

                    if doc_stats.get("cancelled"):
                        raise InterruptedError("Cancelled")

                # Process code
                if "code" in types:
                    if self.cancel_requested or self._wait_if_paused():
                        raise InterruptedError("Cancelled")

                    self.current_type = "code"
                    code_stats = ingest_code_entities(
                        client,
                        force_reindex=reindex,
                        service_name=code_service,
                        progress_callback=lambda phase, current, total, msg: self._emit_progress(
                            task_id, "code", phase, current, total, msg
                        ),
                        check_cancelled=lambda: self.cancel_requested,
                        check_paused=self.check_paused,
                    )
                    all_stats["code"] = code_stats

                    self.emit("ingestion_phase_complete", {
                        "task_id": task_id,
                        "type": "code",
                        "stats": code_stats,
                    })

                    if code_stats.get("cancelled"):
                        raise InterruptedError("Cancelled")

                # Process Drupal API
                if "drupal" in types:
                    if self.cancel_requested or self._wait_if_paused():
                        raise InterruptedError("Cancelled")

                    self.current_type = "drupal"

                    # Configure Drupal scraper
                    drupal_config = DrupalScrapeConfig(
                        max_entities=drupal_limit,
                    )

                    # For reindex, delete existing collection first
                    if reindex:
                        from api_gateway.services.drupal_api_schema import (
                            create_drupal_api_collection,
                        )
                        create_drupal_api_collection(client, force_reindex=True)

                    drupal_stats = scrape_drupal_api(
                        config=drupal_config,
                        progress_callback=lambda phase, current, total, msg: self._emit_progress(
                            task_id, "drupal", phase, current, total, msg
                        ),
                        check_cancelled=lambda: self.cancel_requested,
                        check_paused=self.check_paused,
                    )
                    all_stats["drupal"] = drupal_stats

                    self.emit("ingestion_phase_complete", {
                        "task_id": task_id,
                        "type": "drupal",
                        "stats": drupal_stats,
                    })

                    if drupal_stats.get("cancelled"):
                        raise InterruptedError("Cancelled")

                # Process MDN JavaScript
                if "mdn_javascript" in types:
                    if self.cancel_requested or self._wait_if_paused():
                        raise InterruptedError("Cancelled")

                    self.current_type = "mdn_javascript"

                    # Configure MDN JavaScript scraper
                    mdn_js_config = MdnJsScrapeConfig(
                        max_entities=mdn_limit,
                    )

                    # For reindex, delete existing collection first
                    if reindex:
                        from api_gateway.services.mdn_schema import (
                            create_mdn_javascript_collection,
                        )
                        create_mdn_javascript_collection(client, force_reindex=True)

                    mdn_js_stats = scrape_mdn_javascript(
                        config=mdn_js_config,
                        progress_callback=lambda phase, current, total, msg: self._emit_progress(
                            task_id, "mdn_javascript", phase, current, total, msg
                        ),
                        check_cancelled=lambda: self.cancel_requested,
                        check_paused=self.check_paused,
                    )
                    all_stats["mdn_javascript"] = mdn_js_stats

                    self.emit("ingestion_phase_complete", {
                        "task_id": task_id,
                        "type": "mdn_javascript",
                        "stats": mdn_js_stats,
                    })

                    if mdn_js_stats.get("cancelled"):
                        raise InterruptedError("Cancelled")

                # Process MDN Web APIs
                if "mdn_webapis" in types:
                    if self.cancel_requested or self._wait_if_paused():
                        raise InterruptedError("Cancelled")

                    self.current_type = "mdn_webapis"

                    # Configure MDN Web APIs scraper
                    mdn_web_config = MdnWebScrapeConfig(
                        max_entities=mdn_limit,
                        section_filter=mdn_section if mdn_section else None,
                    )

                    # For reindex, delete existing collection first
                    if reindex:
                        from api_gateway.services.mdn_schema import (
                            create_mdn_webapis_collection,
                        )
                        create_mdn_webapis_collection(client, force_reindex=True)

                    mdn_web_stats = scrape_mdn_webapis(
                        config=mdn_web_config,
                        progress_callback=lambda phase, current, total, msg: self._emit_progress(
                            task_id, "mdn_webapis", phase, current, total, msg
                        ),
                        check_cancelled=lambda: self.cancel_requested,
                        check_paused=self.check_paused,
                    )
                    all_stats["mdn_webapis"] = mdn_web_stats

                    self.emit("ingestion_phase_complete", {
                        "task_id": task_id,
                        "type": "mdn_webapis",
                        "stats": mdn_web_stats,
                    })

                    if mdn_web_stats.get("cancelled"):
                        raise InterruptedError("Cancelled")

        except InterruptedError:
            success = False
            self.emit("ingestion_cancelled", {"task_id": task_id})

        except Exception as exc:
            success = False
            self.emit("ingestion_error", {
                "task_id": task_id,
                "error": str(exc),
                "type": self.current_type,
            })

        finally:
            duration = time.time() - start_time

            if success:
                self.emit("ingestion_complete", {
                    "task_id": task_id,
                    "success": True,
                    "stats": all_stats,
                    "duration_seconds": round(duration, 2),
                })

            with self.lock:
                self.is_running = False
                self.paused = False
                self.task_id = None
                self.current_type = None
                self.started_at = None
                self._stats = all_stats

    def cancel_ingestion(self) -> Dict[str, Any]:
        """
        Request cancellation of the current ingestion.

        Returns:
            Dictionary with success status.
        """
        with self.lock:
            if not self.is_running:
                return {
                    "success": False,
                    "error": "No ingestion in progress",
                }

            self.cancel_requested = True
            return {
                "success": True,
                "message": "Cancellation requested",
                "task_id": self.task_id,
            }

    def pause_ingestion(self) -> Dict[str, Any]:
        """
        Pause the current ingestion.

        Returns:
            Dictionary with success status.
        """
        with self.lock:
            if not self.is_running:
                return {
                    "success": False,
                    "error": "No ingestion in progress",
                }

            if self.paused:
                return {
                    "success": False,
                    "error": "Ingestion already paused",
                }

            self.paused = True
            task_id = self.task_id

        self.emit("ingestion_paused", {
            "task_id": task_id,
            "timestamp": time.time(),
        })

        return {
            "success": True,
            "message": "Ingestion paused",
            "task_id": task_id,
        }

    def resume_ingestion(self) -> Dict[str, Any]:
        """
        Resume a paused ingestion.

        Returns:
            Dictionary with success status.
        """
        with self.lock:
            if not self.is_running:
                return {
                    "success": False,
                    "error": "No ingestion in progress",
                }

            if not self.paused:
                return {
                    "success": False,
                    "error": "Ingestion is not paused",
                }

            self.paused = False
            task_id = self.task_id

        self.emit("ingestion_resumed", {
            "task_id": task_id,
            "timestamp": time.time(),
        })

        return {
            "success": True,
            "message": "Ingestion resumed",
            "task_id": task_id,
        }

    def _emit_progress(
        self,
        task_id: str,
        ingestion_type: str,
        phase: str,
        current: int,
        total: int,
        message: str,
    ) -> None:
        """Emit a progress update via WebSocket."""
        self.emit("ingestion_progress", {
            "task_id": task_id,
            "type": ingestion_type,
            "phase": phase,
            "current": current,
            "total": total,
            "message": message,
            "paused": self.paused,
        })

    def _wait_if_paused(self) -> bool:
        """
        Wait while ingestion is paused.

        Returns:
            True if cancelled during wait, False otherwise.
        """
        while self.paused and not self.cancel_requested:
            time.sleep(0.5)
        return self.cancel_requested

    def check_paused(self) -> bool:
        """
        Check if paused and wait until resumed.

        This method is intended to be passed as a callback to ingestion/scraper
        functions so they can cooperatively pause during long-running operations.

        Returns:
            True if cancelled during pause wait, False otherwise (continue work).
        """
        if not self.paused:
            return self.cancel_requested
        return self._wait_if_paused()


# Singleton instance (initialized by app.py)
_manager: Optional[IngestionManager] = None


def get_ingestion_manager(emit_callback: Optional[EmitCallback] = None) -> IngestionManager:
    """
    Get or create the singleton IngestionManager instance.

    Args:
        emit_callback: Required on first call to initialize the manager.

    Returns:
        The IngestionManager singleton.
    """
    global _manager
    if _manager is None:
        if emit_callback is None:
            raise RuntimeError("emit_callback required for first initialization")
        _manager = IngestionManager(emit_callback)
    return _manager
