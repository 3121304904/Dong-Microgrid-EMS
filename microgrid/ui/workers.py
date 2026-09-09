"""Background workers for long-running uncertainty experiments."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal, Slot

from ..analysis import (
    AnalysisCancelled,
    MonteCarloSettings,
    SensitivitySettings,
    run_monte_carlo,
    run_sensitivity_analysis,
)
from ..models import MicrogridConfig, ScenarioData


@dataclass
class CancellationToken:
    cancelled: bool = False


class AnalysisWorker(QObject):
    progress = Signal(int)
    completed = Signal(str, object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(
        self,
        kind: str,
        data: ScenarioData,
        config: MicrogridConfig,
        confidence_pct: float,
        settings: MonteCarloSettings | SensitivitySettings,
        token: CancellationToken,
    ) -> None:
        super().__init__()
        self.kind = kind
        self.data = data
        self.config = config
        self.confidence_pct = confidence_pct
        self.settings = settings
        self.token = token

    @Slot()
    def run(self) -> None:
        try:
            callback = lambda current, total: self.progress.emit(
                int(round(100.0 * current / max(1, total)))
            )
            if self.kind == "monte_carlo":
                result = run_monte_carlo(
                    self.data,
                    self.config,
                    self.confidence_pct,
                    self.settings,
                    callback,
                    lambda: self.token.cancelled,
                )
            else:
                result = run_sensitivity_analysis(
                    self.data,
                    self.config,
                    self.confidence_pct,
                    self.settings,
                    callback,
                    lambda: self.token.cancelled,
                )
            self.completed.emit(self.kind, result)
        except AnalysisCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))

