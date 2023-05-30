#!/usr/bin/env python3

# Copyright 2021 Memrise Limited

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import getpass
import random
import shlex
import string
import subprocess
import sys
import time
from typing import cast

import kubernetes


def parse_cli_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy a Kubernetes pod and run commands in its environment.",
        epilog=(
            "If the `--interactive` flag is provided, the copied pod will be removed "
            "immediately after the command exits, otherwise the name of the pod will be printed."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--context", type=str, help="Kubectl context to use for configuration")
    parser.add_argument(
        "-n", "--namespace", type=str, default="default", help="Namespace for where the source pod is located"
    )
    labels_pod_group = parser.add_mutually_exclusive_group(required=True)
    labels_pod_group.add_argument("-l", "--selector", type=str, help="Label selector of pod to copy")
    labels_pod_group.add_argument("-p", "--pod", type=str, help="Name of the pod to copy")
    parser.add_argument(
        "--container", type=str, help="Name of container to copy, only needed if the pod has more than one container"
    )
    parser.add_argument(
        "-c", "--command", type=str, default="sleep infinity", help="Initial command to run in the copied pod"
    )
    parser.add_argument("-i", "--interactive", type=str, help="Command to run in an interactive console")
    parser.add_argument("--image", type=str, help="Set to alternate Docker image to use for copied pod")
    return parser.parse_args()


def get_pod_matching_labels(client: kubernetes.client.CoreV1Api, selector: str, namespace: str | None) -> str:
    try:
        pods_list = client.list_namespaced_pod(namespace, label_selector=selector).items
        if pods_list:
            return cast(str, pods_list[0].metadata.name)

        print("No pods were found which matched the provided labels", file=sys.stderr)
        sys.exit(1)
    except kubernetes.client.ApiException as error:
        print(f"Error occurred when trying to find pod matching labels: {error.reason}", file=sys.stderr)
        sys.exit(1)


def random_suffix(length: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def prepare_pod(
    pod: kubernetes.client.V1Pod, command: list[str], container: str | None, image: str | None
) -> kubernetes.client.V1Pod:
    # Metadata
    pod.metadata.annotations["sentry/ignore-pod-updates"] = "true"
    pod.metadata.creation_timestamp = None
    pod.metadata.labels = {"creator": getpass.getuser(), "original-pod": pod.metadata.name}
    pod.metadata.name = f"pod-copy-{random_suffix()}"
    pod.metadata.owner_references = None
    pod.metadata.resource_version = None
    pod.metadata.uid = None

    # Spec
    found_containers = {i.name: i for i in pod.spec.containers}
    if container:
        if container not in found_containers:
            print("Error: The specified container was not found in the pod", file=sys.stderr)
            sys.exit(1)

        pod.spec.containers = [found_containers[container]]

    if len(pod.spec.containers) > 1:
        print("Error: Pod contains multiple containers but `--container` wasn't specified", file=sys.stderr)
        sys.exit(1)

    pod.spec.containers[0].command = command
    pod.spec.containers[0].args = None

    pod.spec.containers[0].liveness_probe = None
    pod.spec.containers[0].readiness_probe = None
    pod.spec.containers[0].startup_probe = None

    pod.spec.containers[0].resources = None

    pod.spec.affinity = None

    if image:
        pod.spec.containers[0].image = image

    pod.spec.restart_policy = "Never"

    pod.status = {}

    return pod


def wait_while_pending(k8s_client: kubernetes.client.CoreV1Api, namespace: str, pod: str) -> None:
    while k8s_client.read_namespaced_pod(pod, namespace).status.phase == "Pending":
        time.sleep(1)


def main() -> None:
    args = parse_cli_arguments()

    pod_name = args.pod

    kube_config_kwargs = {"context": args.context} if args.context else {}
    kubernetes.config.load_config(**kube_config_kwargs)
    k8s_client = kubernetes.client.CoreV1Api()

    if args.selector:
        pod_name = get_pod_matching_labels(k8s_client, args.selector, args.namespace)

    # Get details of the source pod
    try:
        src_pod = k8s_client.read_namespaced_pod(pod_name, args.namespace)
    except kubernetes.client.ApiException as error:
        print(f"Error occurred when trying to get information about existing pod: {error.reason}", file=sys.stderr)
        sys.exit(1)

    # Prepare the copied pod and create it
    dest_pod = prepare_pod(src_pod, shlex.split(args.command), args.container, args.image)
    try:
        k8s_client.create_namespaced_pod(args.namespace, dest_pod)
    except kubernetes.client.ApiException as error:
        print(f"Error occurred when trying to create copied pod: {error.reason}", file=sys.stderr)
        sys.exit(1)

    pod_name = dest_pod.metadata.name
    wait_while_pending(k8s_client, args.namespace, pod_name)

    if not args.interactive:
        # We are not running any interactive commands, so just print the pod name and exit
        print(pod_name)
        sys.exit(0)

    command = ["kubectl", f"--namespace={args.namespace}"]

    if args.context:
        command += [f"--context={args.context}"]

    command += ["exec", "--stdin", "--tty", pod_name, "--", *shlex.split(args.interactive)]
    result = subprocess.run(command)  # noqa: S603

    try:
        k8s_client.delete_namespaced_pod(
            pod_name, args.namespace, body=kubernetes.client.V1DeleteOptions(grace_period_seconds=1)
        )
    except kubernetes.client.ApiException as error:
        print(error)
        print(f"Error occurred when trying to delete copied pod: {error.reason}", file=sys.stderr)

    sys.exit(result.returncode)
