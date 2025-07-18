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

"""Collect and save metrics from prometheus"""

import argparse
from datetime import datetime, timedelta
import os
import sys
import json
import logging

from openshift_metrics import utils
from openshift_metrics.prometheus_client import PrometheusClient
from openshift_metrics.metrics_processor import MetricsProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STORAGE_BYTES = ('(kube_pod_spec_volumes_persistentvolumeclaims_info{cluster="nerc-ocp-prod"}'
                 '* on (pod, namespace)'
                 'group_left(label_nerc_mghpcc_org_class)'
                 'max by (pod, namespace, label_nerc_mghpcc_org_class)'
                 '(kube_pod_labels{cluster="nerc-ocp-prod", label_nerc_mghpcc_org_class!=""}))'
                 '* on (persistentvolumeclaim, namespace) group_left() '
                 'max by (persistentvolumeclaim, namespace) '
                 '(kubelet_volume_stats_used_bytes{cluster="nerc-ocp-prod"}) / 1024^3'
            )

URL_CLUSTER_NAME_MAPPING = {
    "https://thanos-querier-openshift-monitoring.apps.shift.nerc.mghpcc.org": "ocp-prod",
    "https://thanos-querier-openshift-monitoring.apps.ocp-test.nerc.mghpcc.org": "ocp-test",
    "https://grafana.apps.obs.nerc.mghpcc.org/api/datasources/proxy/1": "ocp-prod",
}


def main():
    """This method kick starts the process of collecting and saving the metrics"""
    print(STORAGE_BYTES)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--openshift-url",
        help="OpenShift Prometheus URL",
        default=os.getenv("OPENSHIFT_PROMETHEUS_URL"),
    )
    parser.add_argument(
        "--report-start-date",
        help="report date (ex: 2022-03-14)",
        default=(datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    parser.add_argument(
        "--report-end-date",
        help="report date (ex: 2022-03-14)",
        default=(datetime.today() - timedelta(days=1)).strftime("%Y-%m-%d"),
    )
    parser.add_argument("--upload-to-s3", action="store_true")
    parser.add_argument("--output-file")

    args = parser.parse_args()
    if not args.openshift_url:
        sys.exit(
            "Must specify --openshift-url or set OPENSHIFT_PROMETHEUS_URL in your environment"
        )
    openshift_url = args.openshift_url

    report_start_date = args.report_start_date
    report_end_date = args.report_end_date

    report_length = datetime.strptime(report_end_date, "%Y-%m-%d") - datetime.strptime(
        report_start_date, "%Y-%m-%d"
    )
    assert report_length.days >= 0, "report_start_date cannot be after report_end_date"

    if args.output_file:
        output_file = args.output_file
    elif report_start_date == report_end_date:
        output_file = f"metrics-{report_start_date}.json"
    else:
        output_file = f"metrics-{report_start_date}-to-{report_end_date}.json"

    logger.info(
        f"Generating report starting {report_start_date} and ending {report_end_date} in {output_file}"
    )

    token = os.environ.get("OPENSHIFT_TOKEN")
    assert token is not None, "Set the openshift token"
    prom_client = PrometheusClient(openshift_url, token)

    metrics_dict = {}
    metrics_dict["start_date"] = report_start_date
    metrics_dict["end_date"] = report_end_date
    metrics_dict["cluster_name"] = URL_CLUSTER_NAME_MAPPING.get(
        args.openshift_url, args.openshift_url
    )

    try:
        storage_metrics = prom_client.query_metric(
            STORAGE_BYTES, report_start_date, report_end_date
        )
        metrics_dict["storage_metrics"] = storage_metrics
    except utils.EmptyResultError:
        logger.info(
            f"No storage metrics found for the period {report_start_date} to {report_end_date}"
        )
        pass

    month_year = datetime.strptime(report_start_date, "%Y-%m-%d").strftime("%Y-%m")

    if report_start_date == report_end_date:
        s3_location = f"data_{month_year}/metrics-{report_start_date}.json"
    else:
        s3_location = (
            f"data_{month_year}/metrics-{report_start_date}-to-{report_end_date}.json"
        )

    with open(output_file, "w") as file:
        logger.info(f"Writing metrics to {output_file}")
        json.dump(metrics_dict, file)

    if args.upload_to_s3:
        bucket_name = os.environ.get("S3_METRICS_BUCKET", "openshift_metrics")
        utils.upload_to_s3(output_file, bucket_name, s3_location)


if __name__ == "__main__":
    main()
