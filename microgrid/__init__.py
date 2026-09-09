"""Microgrid energy management core package."""

from .data import (
    HERTZ_FILENAME,
    HERTZ_SOURCE_NAME,
    generate_typical_day,
    list_50hertz_dates,
    load_50hertz_day,
    load_scenario_csv,
    locate_50hertz_csv,
    read_50hertz_year,
)
from .models import MicrogridConfig, ScenarioData, default_config
from .analysis import (
    MonteCarloResult,
    MonteCarloSettings,
    SensitivityResult,
    SensitivitySettings,
    run_monte_carlo,
    run_sensitivity_analysis,
)
from .project import ProjectDocument, load_project, save_project
from .scheduler import (
    DispatchPlan,
    DispatchResult,
    execute_dispatch_plan,
    prepare_dispatch_plan,
    run_all_strategies,
    run_baseline,
    run_strategy,
)


def export_report_bundle(*args, **kwargs):
    """Lazily import Matplotlib only when a report is actually exported."""

    from .reporting import export_report_bundle as implementation

    return implementation(*args, **kwargs)

__all__ = [
    "DispatchPlan",
    "DispatchResult",
    "MonteCarloResult",
    "MonteCarloSettings",
    "MicrogridConfig",
    "ProjectDocument",
    "ScenarioData",
    "SensitivityResult",
    "SensitivitySettings",
    "default_config",
    "execute_dispatch_plan",
    "export_report_bundle",
    "generate_typical_day",
    "HERTZ_FILENAME",
    "HERTZ_SOURCE_NAME",
    "list_50hertz_dates",
    "load_50hertz_day",
    "load_project",
    "load_scenario_csv",
    "locate_50hertz_csv",
    "prepare_dispatch_plan",
    "run_all_strategies",
    "run_baseline",
    "run_monte_carlo",
    "run_sensitivity_analysis",
    "run_strategy",
    "read_50hertz_year",
    "save_project",
]
