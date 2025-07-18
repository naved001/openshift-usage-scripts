#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.
#

"""Holds bunch of utility functions"""

import os
import csv
import boto3
import logging

from openshift_metrics import invoice
from decimal import Decimal

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmptyResultError(Exception):
    """Raise when no results are retrieved for a query"""


def upload_to_s3(file, bucket, location):
    s3_endpoint = os.getenv(
        "S3_OUTPUT_ENDPOINT_URL", "https://s3.us-east-005.backblazeb2.com"
    )
    s3_key_id = os.getenv("S3_OUTPUT_ACCESS_KEY_ID")
    s3_secret = os.getenv("S3_OUTPUT_SECRET_ACCESS_KEY")

    if not s3_key_id or not s3_secret:
        raise Exception(
            "Must provide S3_OUTPUT_ACCESS_KEY_ID and"
            " S3_OUTPUT_SECRET_ACCESS_KEY environment variables."
        )
    s3 = boto3.client(
        "s3",
        endpoint_url=s3_endpoint,
        aws_access_key_id=s3_key_id,
        aws_secret_access_key=s3_secret,
    )
    logger.info(f"Uploading {file} to s3://{bucket}/{location}")
    s3.upload_file(file, Bucket=bucket, Key=location)


def csv_writer(rows, file_name):
    """Writes rows as csv to file_name"""
    logger.info(f"Writing report to {file_name}")
    with open(file_name, "w") as csvfile:
        csvwriter = csv.writer(csvfile)
        csvwriter.writerows(rows)


def write_metrics_by_namespace(
    condensed_metrics_dict,
    file_name,
    report_month,
    cluster_name,
    rate,
    ignore_hours=None,
):
    """
    Process metrics dictionary to aggregate usage by namespace and then write that to a file
    """
    invoices = {}
    rows = []
    headers = [
        "Invoice Month",
        "Project - Allocation",
        "Project - Allocation ID",
        "Manager (PI)",
        "Cluster Name",
        "Invoice Email",
        "Invoice Address",
        "Institution",
        "Institution - Specific Code",
        "SU Hours (GBhr or SUhr)",
        "SU Type",
        "Rate",
        "Cost",
    ]

    rows.append(headers)

    for namespace, pvcs in condensed_metrics_dict.items():
        if namespace not in invoices:
            project_invoice = invoice.ProjectInvoce(
                invoice_month=report_month,
                project=namespace,
                project_id=namespace,
                pi="",
                cluster_name=cluster_name,
                invoice_email="",
                invoice_address="",
                intitution="",
                institution_specific_code="",
                rate=rate,
                ignore_hours=ignore_hours,
            )
            invoices[namespace] = project_invoice

        project_invoice = invoices[namespace]

        for pvc, pvc_dict in pvcs.items():
            for epoch_time, pvc_metric_dict in pvc_dict["metrics"].items():
                pvc_obj = invoice.PVC(
                    volume=pvc,
                    persistent_volume_claim=pvc,
                    namespace=namespace,
                    start_time=epoch_time,
                    duration=pvc_metric_dict["duration"],
                    size_gib=Decimal(pvc_metric_dict["storage_metrics"]),
                )
                project_invoice.add_pvc(pvc_obj)

    for project_invoice in invoices.values():
        rows.extend(project_invoice.generate_invoice_rows(report_month))

    csv_writer(rows, file_name)


def write_metrics_by_pvc(
    condensed_metrics_dict, file_name, ignore_hours=None
):
    """
    Generates metrics report by pod.
    """
    rows = []
    headers = [
        "Namespace",
        "PVC Start Time",
        "PVC End Time",
        "Duration (Hours)",
        "PVC Name",
        "Size (GiB)",
    ]
    rows.append(headers)

    for namespace, pvcs in condensed_metrics_dict.items():
        for pvc_name, pvc_dict in pvcs.items():
            class_name = pvc_dict.get("label_nerc_mghpcc_org_class")
            if class_name:
                project_name = f"{namespace}:{class_name}"
            else:
                project_name = f"{namespace}:noclass"

            pvc_metrics_dict = pvc_dict["metrics"]
            for epoch_time, pvc_metric_dict in pvc_metrics_dict.items():
                pod_obj = invoice.PVC(
                    volume=pvc_name,
                    persistent_volume_claim=pvc_name,
                    namespace=project_name,
                    start_time=epoch_time,
                    duration=pvc_metric_dict["duration"],
                    size_gib=pvc_metric_dict["storage_metrics"],
                )
                rows.append(pod_obj.generate_pvc_row(ignore_hours))

    csv_writer(rows, file_name)


def write_metrics_by_classes(
    condensed_metrics_dict,
    file_name,
    report_month,
    namespaces_with_classes,
    cluster_name,
    rate,
    ignore_hours=None,
):
    """
    Process metrics dictionary to aggregate usage by the class label.

    If a pod has a class label, then the project name is composed of namespace:class_name
    otherwise it's namespace:noclass.
    """
    invoices = {}
    rows = []
    headers = [
        "Invoice Month",
        "Project - Allocation",
        "Project - Allocation ID",
        "Manager (PI)",
        "Cluster Name",
        "Invoice Email",
        "Invoice Address",
        "Institution",
        "Institution - Specific Code",
        "SU Hours (GBhr or SUhr)",
        "SU Type",
        "Rate",
        "Cost",
    ]

    rows.append(headers)

    for namespace, pvcs in condensed_metrics_dict.items():
        if namespace not in namespaces_with_classes:
            continue

        # for pod, pod_dict in pods.items():
        for pvc, pvc_dict in pvcs.items():
            class_name = pvc_dict.get("label_nerc_mghpcc_org_class")
            if class_name:
                project_name = f"{namespace}:{class_name}"
            else:
                project_name = f"{namespace}:noclass"

            if project_name not in invoices:
                project_invoice = invoice.ProjectInvoce(
                    invoice_month=report_month,
                    project=project_name,
                    project_id=project_name,
                    pi="",
                    cluster_name=cluster_name,
                    invoice_email="",
                    invoice_address="",
                    intitution="",
                    institution_specific_code="",
                    rate=rate,
                    ignore_hours=ignore_hours,
                )
                invoices[project_name] = project_invoice
            project_invoice = invoices[project_name]

            for epoch_time, pvc_metric_dict in pvc_dict["metrics"].items():
                pvc_obj = invoice.PVC(
                    volume=pvc,
                    persistent_volume_claim=pvc,
                    namespace=namespace,
                    start_time=epoch_time,
                    duration=pvc_metric_dict["duration"],
                    size_gib=Decimal(pvc_metric_dict["storage_metrics"]),
                )
                project_invoice.add_pvc(pvc_obj)

    for project_invoice in invoices.values():
        rows.extend(project_invoice.generate_invoice_rows(report_month))

    csv_writer(rows, file_name)
