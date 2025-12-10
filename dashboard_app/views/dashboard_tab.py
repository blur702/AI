from __future__ import annotations

import logging
import webbrowser
from tkinter import ttk

from dashboard_app.config import AppConfig
from dashboard_app.controllers.ollama_controller import OllamaController
from dashboard_app.controllers.service_controller import ServiceController
from dashboard_app.controllers.vram_controller import VRAMMonitor
from dashboard_app.views.widgets.resource_panel import ResourcePanel
from dashboard_app.views.widgets.service_card import ServiceCard


logger = logging.getLogger(__name__)


class DashboardTab(ttk.Frame):
    """Main dashboard tab: resource panel + service cards."""

    def __init__(
        self,
        master,
        service_controller: ServiceController,
        vram_monitor: VRAMMonitor,
        ollama_controller: OllamaController,
        app_config: AppConfig,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self.service_controller = service_controller
        self.vram_monitor = vram_monitor
        self.ollama_controller = ollama_controller
        self.app_config = app_config

        self.resource_panel = ResourcePanel(
            self, on_toggle=self._on_resource_panel_toggle
        )
        self.resource_panel.add_model_unload_callback(self._on_unload_model)
        self.resource_panel.add_auto_stop_callback(self._on_auto_stop_toggle)
        self.resource_panel.add_timeout_callback(self._on_timeout_change)
        self.resource_panel.set_expanded(self.app_config.resource_panel_expanded)
        self.resource_panel.pack(fill="x", padx=8, pady=8)

        self.cards_container = ttk.Frame(self)
        self.cards_container.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.cards_container.columnconfigure(0, weight=1)

        self.service_cards: dict[str, ServiceCard] = {}
        self.section_headers: list[ttk.Label] = []

        self.refresh_services()
        self.refresh_resources()

    def refresh_services(self) -> None:
        statuses = self.service_controller.get_all_statuses()
        status_by_id = {s["service_id"]: s for s in statuses}

        # Remove cards for services that no longer exist and update existing ones.
        for service_id, card in list(self.service_cards.items()):
            status = status_by_id.get(service_id)
            if status is None:
                card.destroy()
                del self.service_cards[service_id]
            else:
                card.update_status(status)

        # Create cards for new services.
        for status in statuses:
            service_id = status["service_id"]
            if service_id not in self.service_cards:
                card = ServiceCard(
                    self.cards_container,
                    status=status,
                    on_start=self._on_start,
                    on_stop=self._on_stop,
                    on_open=self._on_open,
                )
                self.service_cards[service_id] = card

        # Clear previous layout headers.
        for header in self.section_headers:
            header.destroy()
        self.section_headers.clear()

        # Remove grid placements for all cards; we'll re-grid them below.
        for card in self.service_cards.values():
            card.grid_forget()

        # Group services by section for layout.
        by_section: dict[str, list[str]] = {}
        for status in statuses:
            section = status.get("section") or "Main"
            sid = status["service_id"]
            by_section.setdefault(section, []).append(sid)

        row = 0
        for section, ids in sorted(by_section.items()):
            header = ttk.Label(
                self.cards_container,
                text=section,
                style="Header.TLabel",
            )
            header.grid(row=row, column=0, sticky="w", pady=(4, 2))
            self.section_headers.append(header)
            row += 1
            for service_id in ids:
                card = self.service_cards.get(service_id)
                if card is not None:
                    card.grid(row=row, column=0, sticky="we", pady=4)
                    row += 1

    def refresh_resources(self) -> None:
        gpu = self.vram_monitor.get_gpu_stats()
        models = self.vram_monitor.get_loaded_models()
        procs = self.vram_monitor.get_gpu_processes()
        self.resource_panel.update_from_data(
            gpu_stats=gpu,
            models=models,
            processes=procs,
            auto_stop_enabled=self.app_config.autostop_enabled,
            idle_timeout_minutes=self.app_config.autostop_timeout_minutes,
        )

    def _on_start(self, service_id: str) -> None:
        self.service_controller.start_service(service_id)

    def _on_stop(self, service_id: str) -> None:
        self.service_controller.stop_service(service_id)

    def _on_open(self, status: dict) -> None:
        port = status.get("port")
        if port:
            url = f"http://127.0.0.1:{port}"
            webbrowser.open(url)

    def _on_resource_panel_toggle(self, expanded: bool) -> None:
        self.app_config.resource_panel_expanded = expanded

    def _on_unload_model(self, model_name: str) -> None:
        # Prefer HTTP API unload; fall back to CLI via VRAMMonitor.
        ok = self.ollama_controller.unload_model(model_name)
        if not ok:
            logger.info(
                "HTTP unload failed for model %s; falling back to CLI", model_name
            )
            self.vram_monitor.unload_model(model_name)
        self.refresh_resources()

    def _on_auto_stop_toggle(self, enabled: bool) -> None:
        self.service_controller.enable_auto_stop(enabled)
        self.app_config.autostop_enabled = enabled

    def _on_timeout_change(self, minutes: int) -> None:
        self.service_controller.set_idle_timeout(minutes)
        self.app_config.autostop_timeout_minutes = minutes
