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

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys

from copypod.exceptions import CopypodError

from . import __version__, kube, pod_config


def parse_cli_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=f"copypod {__version__}",
        description="Copy a Kubernetes pod and run commands in its environment.",
        epilog=(
            "If the `--interactive` flag is provided, the copied pod will be removed "
            "immediately after the command exits, otherwise the name of the pod will be printed."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--context", type=str, help="Kubectl context to use for configuration"
    )
    parser.add_argument(
        "-n",
        "--namespace",
        type=str,
        default="default",
        help="Namespace for where the source pod is located",
    )
    labels_pod_group = parser.add_mutually_exclusive_group(required=True)
    labels_pod_group.add_argument(
        "-l", "--selector", type=str, help="Label selector of pod to copy"
    )
    labels_pod_group.add_argument(
        "-p", "--pod", type=str, help="Name of the pod to copy"
    )
    parser.add_argument(
        "--container",
        type=str,
        help="Name of container to copy, only needed if the pod has more than one container",
    )
    parser.add_argument(
        "-c",
        "--command",
        type=str,
        default="sleep infinity",
        help="Initial command to run in the copied pod",
    )
    parser.add_argument(
        "-i", "--interactive", type=str, help="Command to run in an interactive console"
    )
    parser.add_argument(
        "--image", type=str, help="Set to alternate Docker image to use for copied pod"
    )
    parser.add_argument(
        "--cap-add",
        action="append",
        help="Capabilities to add for the copied pod, can be specified multiple times",
    )
    parser.add_argument(
        "-s",
        "--suffix",
        type=str,
        help="Set custom suffix for the new pod, otherwise a random suffix is generated",
    )
    parser.add_argument(
        "-e",
        "--env",
        action="append",
        help="Environment variable to set (NAME=value), can be specified multiple times",
    )
    return parser.parse_args()


def run_command_in_pod(
    pod_name: str, namespace: str, context: str | None, command: str
) -> int:
    cmd = ["kubectl", f"--namespace={namespace}"]

    if context:
        cmd += [f"--context={context}"]

    cmd += ["exec", "--stdin", "--tty", pod_name, "--", *shlex.split(command)]
    result = subprocess.run(cmd, check=False)  # noqa: S603

    return result.returncode


def main() -> None:
    args = parse_cli_arguments()
    client = kube.get_client(args.context)

    try:
        src_pod_name = args.pod
        if args.selector:
            src_pod_name = kube.get_pod_matching_labels(
                client, args.selector, args.namespace
            )

        # Get details of the source pod
        src_pod = kube.get_pod_by_name(client, src_pod_name, args.namespace)

        # Prepare the copied pod and create it
        pod = pod_config.remove_extra_containers(src_pod, args.container)
        pod = pod_config.add_annotations(pod)
        pod = pod_config.clear_fields(pod)
        pod = pod_config.set_pod_name(pod, args.suffix)
        pod = pod_config.configure_container(pod, args.command, args.image, args.env)
        pod = pod_config.add_capabilities(pod, args.cap_add)

        kube.create_pod(client, pod)
        kube.wait_until_running(client, pod)

        if not args.interactive:
            # We are not running any interactive commands, so just print the pod name and exit
            print(pod.metadata.name)
            return

        exit_code = run_command_in_pod(
            pod.metadata.name, args.namespace, args.context, args.interactive
        )

        kube.delete_pod(client, pod)

        sys.exit(exit_code)
    except CopypodError as error:
        print(error, file=sys.stderr)
        sys.exit(1)
