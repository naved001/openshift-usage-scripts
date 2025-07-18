import math
from dataclasses import dataclass, field
from collections import namedtuple
from typing import List, Tuple, Optional
from decimal import Decimal, ROUND_HALF_UP
import datetime

SU_STORAGE = "OpenShift Storage"

@dataclass
class PVC:
    """an object that represents a pvc"""
    volume: str
    persistent_volume_claim: str
    namespace: str
    start_time: int
    duration: int
    size_gib: Decimal

    def get_runtime(
        self, ignore_times: List[Tuple[datetime.datetime, datetime.datetime]] = None
    ) -> Decimal:
        """Return runtime eligible for billing in hours"""

        total_runtime = self.duration

        if ignore_times:
            for ignore_start_date, ignore_end_date in ignore_times:
                ignore_start = int(ignore_start_date.timestamp())
                ignore_end = int(ignore_end_date.timestamp())
                if ignore_end <= self.start_time or ignore_start >= self.end_time:
                    continue
                overlap_start = max(self.start_time, ignore_start)
                overlap_end = min(self.end_time, ignore_end)

                overlap_duration = max(0, overlap_end - overlap_start)
                total_runtime = max(0, total_runtime - overlap_duration)

        return Decimal(total_runtime) / 3600

    @property
    def end_time(self) -> int:
        return self.start_time + self.duration

    def generate_pvc_row(self, ignore_times):
        """
        This returns a row to represent pod data.
        It converts the epoch_time stamps to datetime timestamps so it's more readable.
        Additionally, some metrics are rounded for readibility.
        """
        start_time = datetime.datetime.fromtimestamp(
            self.start_time, datetime.UTC
        ).strftime("%Y-%m-%dT%H:%M:%S")
        end_time = datetime.datetime.fromtimestamp(
            self.end_time, datetime.UTC
        ).strftime("%Y-%m-%dT%H:%M:%S")
        runtime = self.get_runtime(ignore_times).quantize(
            Decimal(".0001"), rounding=ROUND_HALF_UP
        )
        return [
            self.namespace,
            start_time,
            end_time,
            runtime,
            self.persistent_volume_claim,
            self.size_gib,
        ]

@dataclass
class ProjectInvoce:
    """Represents the invoicing data for a project."""

    invoice_month: str
    project: str
    project_id: str
    pi: str
    cluster_name: str
    invoice_email: str
    invoice_address: str
    intitution: str
    institution_specific_code: str
    rate: Decimal
    ignore_hours: Optional[List[Tuple[datetime.datetime, datetime.datetime]]] = None
    su_hours: dict = field(
        default_factory=lambda: {
            SU_STORAGE: 0,
        }
    )

    def add_pvc(self, pvc: PVC) -> None:
        """Aggregate a pods data"""
        duration_in_hours = pvc.get_runtime(self.ignore_hours)
        self.su_hours[SU_STORAGE] += pvc.size_gib * duration_in_hours

    def generate_invoice_rows(self, report_month) -> List[str]:
        rows = []
        for su_type, hours in self.su_hours.items():
            if hours > 0:
                hours = math.ceil(hours)
                cost = (self.rate * hours).quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
                row = [
                    report_month,
                    self.project,
                    self.project_id,
                    self.pi,
                    self.cluster_name,
                    self.invoice_email,
                    self.invoice_address,
                    self.intitution,
                    self.institution_specific_code,
                    hours,
                    su_type,
                    self.rate,
                    cost,
                ]
                rows.append(row)
        return rows
