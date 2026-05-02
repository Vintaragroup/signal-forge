from __future__ import annotations

import csv
import re
from io import StringIO
from pathlib import Path
from typing import Any

from bson import ObjectId

from tools.base_tool import BaseTool, clean_text, slugify, utc_now


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

EXPECTED_FIELDS = (
    "company",
    "website",
    "phone",
    "email",
    "city",
    "state",
    "service_category",
    "notes",
    "source_url",
)


class CandidateImportError(ValueError):
    pass


class ManualCandidateImportTool(BaseTool):
    tool_name = "manual_upload"
    mode = "manual_csv_read_only"

    def _collect_row_errors(self, row: dict[str, Any], row_number: int) -> list[dict[str, Any]]:
        """Return a list of per-row validation error dicts (non-fatal)."""
        errors: list[dict[str, Any]] = []
        email = clean_text(row.get("email"))
        if email and not _EMAIL_RE.match(email):
            errors.append({"row": row_number, "field": "email", "error": f"Invalid email format: {email}"})
        return errors

    def parse_csv_text(self, csv_text: str, module: str, source_label: str, workspace_slug: str = "") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Parse CSV text and return (candidates, row_errors).

        Raises CandidateImportError for fatal structural problems (empty file,
        missing required header columns).  Per-row issues are collected in
        row_errors instead of aborting the batch.
        """
        if not clean_text(csv_text):
            raise CandidateImportError("CSV file is empty.")

        reader = csv.DictReader(StringIO(csv_text))
        if not reader.fieldnames:
            raise CandidateImportError("CSV file has no header row.")

        normalized_headers = {clean_text(header).lower() for header in reader.fieldnames}
        missing = [field for field in EXPECTED_FIELDS if field not in normalized_headers]
        if missing:
            raise CandidateImportError(f"CSV is missing required fields: {', '.join(missing)}")

        candidates: list[dict[str, Any]] = []
        row_errors: list[dict[str, Any]] = []
        seen_company_keys: dict[str, int] = {}  # track within-import duplicates
        imported_at = utc_now()

        for row_number, row in enumerate(reader, start=2):
            normalized_row = {clean_text(key).lower(): clean_text(value) for key, value in row.items()}
            if not any(normalized_row.get(field, "") for field in EXPECTED_FIELDS):
                row_errors.append({"row": row_number, "field": None, "error": "Row has no data in expected fields — skipped"})
                continue

            row_errors.extend(self._collect_row_errors(normalized_row, row_number))

            # Detect within-import duplicates by company name
            company = clean_text(normalized_row.get("company")).lower()
            if company:
                if company in seen_company_keys:
                    row_errors.append({
                        "row": row_number,
                        "field": "company",
                        "error": f"Duplicate within import: company '{normalized_row.get('company')}' already appears at row {seen_company_keys[company]}",
                    })
                else:
                    seen_company_keys[company] = row_number

            candidate = self.normalize_row(normalized_row, module, source_label, imported_at, row_number, workspace_slug)
            if candidate:
                candidates.append(candidate)

        if not candidates:
            raise CandidateImportError("CSV has no importable candidate rows.")
        return candidates, row_errors

    def normalize_row(self, row: dict[str, Any], module: str, source_label: str, imported_at, row_number: int, workspace_slug: str = "") -> dict[str, Any] | None:
        company = clean_text(row.get("company"))
        website = clean_text(row.get("website"))
        source_url = clean_text(row.get("source_url")) or website
        phone = clean_text(row.get("phone"))
        email = clean_text(row.get("email")).lower()
        city = clean_text(row.get("city"))
        state = clean_text(row.get("state")).upper()
        service_category = clean_text(row.get("service_category"))
        notes = clean_text(row.get("notes"))

        if not any([company, website, source_url, phone, email]):
            return None

        identity = company or website or source_url or email or phone or str(row_number)
        extracted_fields = {
            "company": company,
            "website": website,
            "phone": phone,
            "email": email,
            "city": city,
            "state": state,
            "service_category": service_category,
            "source_url": source_url,
        }
        extracted_fields = {key: value for key, value in extracted_fields.items() if value}

        return {
            "company": company,
            "website": website,
            "phone": phone,
            "email": email,
            "city": city,
            "state": state,
            "service_category": service_category,
            "notes": notes,
            "raw_summary": notes,
            "candidate_key": slugify(f"manual-{module}-{source_label}-{identity}-{row_number}"),
            "module": module,
            "source": self.tool_name,
            "source_label": source_label,
            "source_url": source_url,
            "confidence": 0,
            "is_mock": False,
            "extracted_fields": extracted_fields,
            "imported_at": imported_at,
            "timestamp": imported_at,
            "csv_row_number": row_number,
            **({"workspace_slug": workspace_slug} if workspace_slug else {}),
        }

    def load_csv_path(self, csv_path: Path) -> str:
        if not csv_path.exists() or not csv_path.is_file():
            raise CandidateImportError(f"CSV file not found: {csv_path}")
        if csv_path.suffix.lower() != ".csv":
            raise CandidateImportError("Import path must point to a .csv file.")
        return csv_path.read_text(encoding="utf-8-sig")

    def run_text(self, csv_text: str, module: str, source_label: str, db=None, file_name: str = "uploaded.csv", workspace_slug: str = "") -> dict[str, Any]:
        candidates, row_errors = self.parse_csv_text(csv_text, module, source_label, workspace_slug)
        input_payload = {
            "module": module,
            "source_label": source_label,
            "file_name": file_name,
            "row_count": len(candidates),
            "mode": self.mode,
        }
        duplicate_count = sum(1 for candidate in candidates if candidate.get("is_duplicate"))
        output_summary = {
            "candidate_count": len(candidates),
            "duplicate_count": duplicate_count,
            "source_label": source_label,
            "outbound_actions_taken": 0,
            "row_errors": row_errors,
            "error_count": len(row_errors),
        }
        tool_run_id = self.record_tool_run(db, input_payload, output_summary)
        candidate_ids = self.insert_candidates(db, candidates, tool_run_id)
        stored_candidates = list(db.scraped_candidates.find({"tool_run_id": tool_run_id})) if db is not None else []
        duplicate_count = sum(1 for candidate in stored_candidates if candidate.get("is_duplicate"))
        tool_run_query: dict[str, Any] = {"_id": tool_run_id}
        if tool_run_id and ObjectId.is_valid(tool_run_id):
            tool_run_query = {"$or": [{"_id": ObjectId(tool_run_id)}, {"_id": tool_run_id}]}
        db.tool_runs.update_one(
            tool_run_query,
            {"$set": {"output_summary": {**output_summary, "duplicate_count": duplicate_count, "candidate_ids": candidate_ids}}},
        )
        artifact_id = self.create_tool_artifact(
            db,
            tool_run_id,
            {
                "input": input_payload,
                "candidate_count": len(candidate_ids),
                "duplicate_count": duplicate_count,
                "error_count": len(row_errors),
                "candidate_ids": candidate_ids,
                "simulation_only": True,
                "outbound_actions_taken": 0,
            },
        )
        return {
            "tool_run_id": tool_run_id,
            "candidate_ids": candidate_ids,
            "artifact_id": artifact_id,
            "candidate_count": len(candidate_ids),
            "duplicate_count": duplicate_count,
            "error_count": len(row_errors),
            "row_errors": row_errors,
            "source_label": source_label,
            "simulation_only": True,
            "outbound_actions_taken": 0,
        }

    def run_path(self, csv_path: Path, module: str, source_label: str, db=None) -> dict[str, Any]:
        return self.run_text(self.load_csv_path(csv_path), module, source_label, db=db, file_name=str(csv_path))
