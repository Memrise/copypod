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

import sys
from time import sleep

import urllib3
from kubernetes.client import (
    ApiClient,
    ApiException,
    Configuration,
    CoreV1Api,
    V1DeleteOptions,
    V1Pod,
)
from kubernetes.config import load_config

from .exceptions import CopypodError


def get_client(context: str | None) -> CoreV1Api:
    config_kwargs = {"context": context} if context else {}

    configuration = None
    if sys.version_info >= (3, 13):
        # Disable SSL verification if using Python 3.13+.
        # See https://github.com/kubernetes-client/python/issues/2394.
        configuration = Configuration()
        configuration.verify_ssl = False
        urllib3.disable_warnings()

    load_config(client_configuration=configuration, **config_kwargs)

    api_client = ApiClient(configuration)
    return CoreV1Api(api_client)


def wait_until_running(client: CoreV1Api, pod: V1Pod) -> None:
    pod_name = pod.metadata.name
    namespace = pod.metadata.namespace

    while True:
        pod = client.read_namespaced_pod(pod_name, namespace)
        if pod.status.phase == "Running":
            return

        sleep(1)


def get_pod_by_name(client: CoreV1Api, pod_name: str, namespace: str) -> V1Pod:
    try:
        return client.read_namespaced_pod(pod_name, namespace)
    except ApiException as error:
        raise CopypodError(
            f"Error occurred when trying to get information about existing pod: {error.reason}"
        ) from error


def get_pod_matching_labels(
    client: CoreV1Api, selector: str, namespace: str | None
) -> str:
    try:
        pods_list = client.list_namespaced_pod(namespace, label_selector=selector).items
        if pods_list:
            return pods_list[0].metadata.name
    except ApiException as error:
        raise CopypodError(
            f"Error occurred when trying to find pod matching labels: {error.reason}"
        ) from error
    else:
        raise CopypodError("No pods were found which matched the provided labels")


def create_pod(client: CoreV1Api, pod: V1Pod) -> None:
    try:
        client.create_namespaced_pod(pod.metadata.namespace, pod)
    except ApiException as error:
        raise CopypodError(
            f"Error occurred when trying to create copied pod: {error.reason}"
        ) from error


def delete_pod(client: CoreV1Api, pod: V1Pod) -> None:
    try:
        client.delete_namespaced_pod(
            pod.metadata.name,
            pod.metadata.namespace,
            body=V1DeleteOptions(grace_period_seconds=1),
        )
    except ApiException as error:
        raise CopypodError(
            f"Error occurred when trying to delete copied pod: {error.reason}"
        ) from error
