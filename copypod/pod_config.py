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

import shlex
import string
from getpass import getuser
from itertools import chain
from random import choices

from kubernetes.client import V1Capabilities, V1EnvVar, V1Pod, V1SecurityContext

from .exceptions import CopypodError


def remove_extra_containers(pod: V1Pod, container_name: str | None) -> V1Pod:
    if not container_name:
        if len(pod.spec.containers) > 1:
            raise CopypodError(
                "Pod contains multiple containers but `--container` wasn't specified"
            )

        return pod

    found_containers = {c.name: c for c in pod.spec.containers}
    if container_name not in found_containers:
        raise CopypodError("The specified container was not found in the pod")

    pod.spec.containers = [found_containers[container_name]]

    return pod


def add_annotations(pod: V1Pod) -> V1Pod:
    """Add annotations that are useful for the ad-hoc pods."""
    if pod.metadata.annotations is None:
        pod.metadata.annotations = {}

    pod.metadata.annotations["creator"] = getuser()
    pod.metadata.annotations["original-pod"] = pod.metadata.name

    # https://karpenter.sh/docs/concepts/disruption/#pod-level-controls
    pod.metadata.annotations["karpenter.sh/do-not-disrupt"] = "true"

    # https://github.com/wichert/k8s-sentry/pull/14
    pod.metadata.annotations["sentry/ignore-pod-updates"] = "true"

    return pod


def clear_fields(pod: V1Pod) -> V1Pod:
    pod.metadata.creation_timestamp = None
    pod.metadata.labels = {"copypod": "true"}
    pod.metadata.owner_references = None
    pod.metadata.resource_version = None
    pod.metadata.uid = None

    pod.spec.containers[0].liveness_probe = None
    pod.spec.containers[0].readiness_probe = None
    pod.spec.containers[0].startup_probe = None
    pod.spec.containers[0].resources = None

    pod.spec.affinity = None
    pod.spec.node_name = None
    pod.spec.restart_policy = "Never"

    pod.status = {}

    return pod


def set_pod_name(pod: V1Pod, suffix: str | None) -> V1Pod:
    if not suffix:
        suffix = "".join(choices(string.ascii_lowercase + string.digits, k=6))  # noqa: S311

    pod.metadata.name = f"pod-copy-{suffix}"

    return pod


def configure_container(
    pod: V1Pod, command: str, image: str | None, environment_variables: list[str] | None
) -> V1Pod:
    pod.spec.containers[0].command = shlex.split(command)
    pod.spec.containers[0].args = None

    if image:
        pod.spec.containers[0].image = image

    if environment_variables:
        if pod.spec.containers[0].env is None:
            pod.spec.containers[0].env = []

        for env_var in environment_variables:
            try:
                name, value = env_var.split("=", 1)
            except ValueError as error:
                raise CopypodError(
                    "Environment variables need to be provided in the format: NAME=value"
                ) from error
            pod.spec.containers[0].env.append(V1EnvVar(name, value))

    return pod


def add_capabilities(pod: V1Pod, capabilities: list[str]) -> V1Pod:
    if not capabilities:
        return pod

    capabilities = list(
        chain.from_iterable([i.upper().split(",") for i in capabilities])
    )

    if not pod.spec.containers[0].security_context:
        pod.spec.containers[0].security_context = V1SecurityContext()
    if not pod.spec.containers[0].security_context.capabilities:
        pod.spec.containers[0].security_context.capabilities = V1Capabilities()

    if pod.spec.containers[0].security_context.capabilities.add:
        pod.spec.containers[0].security_context.capabilities.add.extend(capabilities)
    else:
        pod.spec.containers[0].security_context.capabilities.add = capabilities

    return pod
