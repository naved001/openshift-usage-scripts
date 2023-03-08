# xdmod-openshift-scripts

xdmod-openshift-scripts contains a script that pulls metric data from an OpenShift Prometheus
endpoint and formats it into a log file suitable for shredding by XDMoD.

## Usage

In order to run the script, you must run `oc login` first.

When running the script, there are two methods of specifying the OpenShift Prometheus
endpoint. The first is through an environment variable:

```
    $ export OPENSHIFT_PROMETHEUS_URL=<prometheus url>
    $ python openshift_metrics/openshift_prometheus_metrics.py 
```

The second is directly on the command line:

```
    $ python openshift_metrics/openshift_prometheus_metrics.py --openshift-url <prometheus url>
```

By default the script will pull data from the previous day. You can also specify a different
date:

```
    $ python openshift_metrics/openshift_prometheus_metrics.py --report-date 2022-03-14
```

The script will generate a log file in the current directory: `2022-03-14.log`. That log can
then be shredded into XDMoD as follows:

```
    $ xdmod-shredder -f slurm -i 2022-03-14.log -r <xdmod resource>
```

## How It Works

The `openshift_prometheus_metrics.py` retrieves metrics at a pod level. It does so with the
following Prometheus query:

```
   <prometheus_url>/api/v1/query_range?query=<metric>&start=<report_date>T00:00:00Z&end=<report_date>T23:59:59Z&step=60s
```

This query generates samples every minute. The script will then merge consecutive samples
together if their metrics are the same.

The script queries the following metrics:

* *kube_pod_resource_request{unit="cores"}*
   * Cores requested by workloads on the cluster, broken down by pod. This shows the core usage the scheduler and kubelet expect per pod.
* *kube_pod_resource_limit{unit="cores"}*
   * Cores limit for workloads on the cluster, broken down by pod. This shows the core usage the scheduler and kubelet expect per pod.
* *kube_pod_resource_limit{unit="bytes"}*
   * Memory (in bytes) limit for workloads on the cluster, broken down by pod. This shows the memory usage the scheduler and kubelet expect per pod.

The script also retrieves further information through annotations.

Each hourly sample corresponds to a single entry in the Slurm job table.
That means that a pod that runs for three hours will generate three or four
entries. As a result queries having to do with a job's specific start or end
time will be inaccurate.

The correspondence between Slurm job columns and OpenShift information is
as follows:


| Slurm          | OpenShift Equivalent                                     |
|----------------|----------------------------------------------------------|
| job_id         | *autogenerated by script*                                |
| job_id_raw     | *autogenerated by script*                                |
| cluster_name   | *openshift cluster annotation*                           |
| partition_name | **blank**                                                |
| qos_name       | **blank**                                                |
| account_name   | *openshift namespace*                                    |
| group_name     | *openshift namespace*                                    |
| gid_number     | **blank**                                                |
| user_name      | **blank***                                               |
| uid_number     | **blank**                                                |
| start_time     | *beginning of sample time*                               |
| end_time       | *end of sample time*                                     |
| submit_time    | *set to start_time*                                      |
| eligible_time  | *set to start_time*                                      |
| elapsed        | *end_time - start_time*                                  |
| timelimit      | * set to elapsed*                                        |
| exit_code      | **blank**                                                |
| state          | **RUNNING**                                              |
| nnodes         | **1**                                                    |
| ncpus          | *kube_pod_resource_request{unit="cores"}*                |
| req_cpus       | *kube_pod_resource_limit{unit="cores"}*                  |
| req_mem        | *kube_pod_resource_limit{unit="bytes"}*                  |
| req_tres       | **cpu=<req_cpus>,mem=<req_mem>**                         |
| alloc_tres     | *set to req_tres*                                        |
| node_list      | **blank**                                                |
| job_name       | *openshift pod name*                                     |

