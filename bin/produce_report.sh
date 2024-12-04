#!/usr/bin/env sh

python -m openshift_metrics.merge /data/*.json \
    --invoice-file /tmp/invoice.csv \
    --pod-report-file /tmp/pod-report.csv \
    --upload-to-s3 \
    --use-nerc-rates