import json
from typing import List, Dict
from collections import namedtuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GPU_UNKNOWN_TYPE = "GPU_UNKNOWN_TYPE"
GPUInfo = namedtuple("GPUInfo", ["gpu_type", "gpu_resource", "node_model"])


class MetricsProcessor:
    """Provides methods for merging metrics and processing it for billing purposes"""

    def __init__(
        self,
        interval_minutes: int = 15,
        merged_data: dict = None,
    ):
        self.interval_minutes = interval_minutes
        self.merged_data = merged_data if merged_data is not None else {}

    def merge_metrics(self, metric_name, metric_list):
        """Merge metrics (cpu, memory, gpu) by pod"""
        for metric in metric_list:
            persistentvolumeclaim = metric["metric"]["persistentvolumeclaim"]
            volume = metric["metric"]["volume"] # this is the name that it's attached as to the pod
            namespace = metric["metric"]["namespace"]

            self.merged_data.setdefault(namespace, {})
            self.merged_data[namespace].setdefault(persistentvolumeclaim, {"metrics": {}})

            class_name = metric["metric"].get("label_nerc_mghpcc_org_class")
            if class_name is not None:
                self.merged_data[namespace][persistentvolumeclaim]["label_nerc_mghpcc_org_class"] = (
                    class_name
                )

            for epoch_time, metric_value in metric["values"]:
                self.merged_data[namespace][persistentvolumeclaim]["metrics"].setdefault(epoch_time, {})

                self.merged_data[namespace][persistentvolumeclaim]["metrics"][epoch_time][metric_name] = (
                    metric_value
                )

    def condense_metrics(self, metrics_to_check: List[str]) -> Dict:
        """
        Checks if the value of metrics is the same, and removes redundant
        metrics while updating the duration. If there's a gap in the reported
        metrics then don't count that as part of duration.
        """
        interval = self.interval_minutes * 60
        condensed_dict = {}

        for namespace, pvcs in self.merged_data.items():
            condensed_dict.setdefault(namespace, {})

            for pvc, pvc_dict in pvcs.items():
                metrics_dict = pvc_dict["metrics"]
                new_metrics_dict = {}
                epoch_times_list = sorted(metrics_dict.keys())

                start_epoch_time = epoch_times_list[0]

                start_metric_dict = metrics_dict[start_epoch_time].copy()

                for i in range(1, len(epoch_times_list)):
                    current_time = epoch_times_list[i]
                    previous_time = epoch_times_list[i - 1]

                    metrics_changed = self._are_metrics_different(
                        metrics_dict[start_epoch_time],
                        metrics_dict[current_time],
                        metrics_to_check,
                    )

                    pod_was_stopped = self._was_pod_stopped(
                        current_time=current_time,
                        previous_time=previous_time,
                        interval=interval,
                    )

                    if metrics_changed or pod_was_stopped:
                        duration = previous_time - start_epoch_time + interval
                        start_metric_dict["duration"] = duration
                        new_metrics_dict[start_epoch_time] = start_metric_dict

                        # Reset start_epoch_time and start_metric_dict
                        start_epoch_time = current_time
                        start_metric_dict = metrics_dict[start_epoch_time].copy()

                # Final block after the loop
                duration = epoch_times_list[-1] - start_epoch_time + interval
                start_metric_dict["duration"] = duration
                new_metrics_dict[start_epoch_time] = start_metric_dict

                # Update the pod dict with the condensed data
                new_pvc_dict = pvc_dict.copy()
                new_pvc_dict["metrics"] = new_metrics_dict
                condensed_dict[namespace][pvc] = new_pvc_dict

        return condensed_dict

    @staticmethod
    def _are_metrics_different(
        metrics_a: Dict, metrics_b: Dict, metrics_to_check: List[str]
    ) -> bool:
        """Method that compares all the metrics in metrics_to_check are different in
        metrics_a and metrics_b
        """
        return any(
            metrics_a.get(metric, 0) != metrics_b.get(metric, 0)
            for metric in metrics_to_check
        )

    @staticmethod
    def _was_pod_stopped(current_time: int, previous_time: int, interval: int) -> bool:
        """
        A pod is assumed to be stopped if the the gap between two consecutive timestamps
        is more than the frequency of our metric collection
        """
        return (current_time - previous_time) > interval

    @staticmethod
    def insert_node_labels(node_labels: list, resource_request_metrics: list) -> list:
        """Inserts node labels into resource_request_metrics"""
        node_label_dict = {}
        for node_label in node_labels:
            node = node_label["metric"]["node"]
            gpu = node_label["metric"].get("label_nvidia_com_gpu_product")
            machine = node_label["metric"].get("label_nvidia_com_gpu_machine")
            node_label_dict[node] = {"gpu": gpu, "machine": machine}
        for pod in resource_request_metrics:
            node = pod["metric"]["node"]
            if node not in node_label_dict:
                logger.warning("Could not find labels for node: %s", node)
                continue
            pod["metric"]["label_nvidia_com_gpu_product"] = node_label_dict[node].get(
                "gpu"
            )
            pod["metric"]["label_nvidia_com_gpu_machine"] = node_label_dict[node].get(
                "machine"
            )
        return resource_request_metrics

    @staticmethod
    def insert_pod_labels(pod_labels: list, resource_request_metrics: list) -> list:
        """Inserts `label_nerc_mghpcc_org_class` label into resource_request_metrics"""
        pod_label_dict = {}
        for pod_label in pod_labels:
            pod_name = pod_label["metric"]["pod"]
            class_name = pod_label["metric"].get("label_nerc_mghpcc_org_class")
            pod_label_dict[pod_name] = {"class": class_name}

        for pod in resource_request_metrics:
            pod_name = pod["metric"]["pod"]
            if pod_name not in pod_label_dict:
                continue
            pod["metric"]["label_nerc_mghpcc_org_class"] = pod_label_dict[pod_name].get(
                "class"
            )
        return resource_request_metrics
