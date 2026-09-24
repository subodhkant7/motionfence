"""Assurance and adversarial evaluation report generator and JSON persistence."""

import json
import os
from typing import Optional
from motionfence.assurance.models import AssuranceReport


class AssuranceReportWriter:
    """Handles serialization and persistence of AssuranceReport objects."""

    @staticmethod
    def save_report(report: AssuranceReport, output_path: str = ".assurance/latest_report.json") -> str:
        """Persist AssuranceReport as structured JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2)
        return output_path

    @staticmethod
    def load_report(input_path: str) -> Optional[AssuranceReport]:
        """Load and deserialize an AssuranceReport from disk."""
        if not os.path.exists(input_path):
            return None
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AssuranceReport.model_validate(data)
