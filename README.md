# copypod

Utility for copying a running Kubernetes pod so you can run commands in a copy
of its environment, without worrying about it the pod potentially being removed
due to a deploy.

`copypod` can work in two different modes, depending on if the `--interactive`
flag is provided:

-   If the flag is left out, `copypod` will copy the specified pod and start
    it. When the pod reaches the "Running" state the name of the pod will be
    outputted as the only output. This is intended for use in automation
    scenarios.
-   If a command is provided with the `--interactive` flag, then the pod will
    be copied and started as before, but when the pod is running `kubectl` will
    be called and connect to the pod where the provided command is then run
    interactively. When the `kubectl` program exits the pod will be removed.
    This is intended for running ad-hoc tasks and processes.


## Install

You can either install `copypod` into a virtual environment directly with:

    pip install git+ssh://git@github.com/Memrise/copypod.git

then the program will be available as `copypod` inside the virtual environment,
or you can install it by cloning this repository and then use `poetry` to set
up a virtual environment where it will get installed into:

    git clone git@github.com:Memrise/copypod.git
    cd copypod/
    poetry install

Then you can run the program with `poetry run copypod`.


## Usage

    $ copypod --help
    usage: copypod [-h] [--context CONTEXT] [-n NAMESPACE] (-l SELECTOR | -p POD) [--container CONTAINER] [-c COMMAND] [-i INTERACTIVE] [--image IMAGE] [--cap-add CAP_ADD] [--node-name NODE_NAME]

    Copy a Kubernetes pod and run commands in its environment.

    options:
      -h, --help            show this help message and exit
      --context CONTEXT     Kubectl context to use for configuration (default: None)
      -n NAMESPACE, --namespace NAMESPACE
                            Namespace for where the source pod is located (default: default)
      -l SELECTOR, --selector SELECTOR
                            Label selector of pod to copy (default: None)
      -p POD, --pod POD     Name of the pod to copy (default: None)
      --container CONTAINER
                            Name of container to copy, only needed if the pod has more than one container (default: None)
      -c COMMAND, --command COMMAND
                            Initial command to run in the copied pod (default: sleep infinity)
      -i INTERACTIVE, --interactive INTERACTIVE
                            Command to run in an interactive console (default: None)
      --image IMAGE         Set to alternate Docker image to use for copied pod (default: None)
      --cap-add CAP_ADD     Capabilities to add for the copied pod (default: None)
      --node-name NODE_NAME Set the node the pod should run on

    If the `--interactive` flag is provided, the copied pod will be removed immediately after the command exits, otherwise the name of the pod will be printed.


## Examples

Say you wanted to copy the pod named `my-great-pod` and have the copied pod run
until you specifically remove it, you could run:

    $ copypod -p my-great-pod
    pod-copy-girwak

`pod-copy-girwak` is then the name of the new pod created for you, and it will
by default run `sleep infinity` as the starting command, meaning it will keep
running forever until it's deleted.

At this point you can enter the pod and run commands as you'd like, for
instance start a shell inside the pod with:

    $ kubectl exec -it pod-copy-girwak -- bash
    root@pod-copy-girwak:/#

When you are done you can remove the copied pod again with `kubectl`:

    $ kubectl delete pod pod-copy-girwak
    pod "pod-copy-girwak" deleted


---

Say you instead would like to copy a pod, start a shell in the copied pod and
have the pod be deleted when you exit the shell, you can do that by supplying
the `--interactive` flag like this:

    $ copypod -p my-great-pod -i bash
    root@pod-copy-i41u04:/# ps -ef
    UID        PID  PPID  C STIME TTY          TIME CMD
    root         1     0  0 10:43 ?        00:00:00 sleep infinity
    root         7     0  0 10:43 ?        00:00:00 bash
    root        13     7  0 10:43 ?        00:00:00 ps -ef

When you are done doing what you needed the pod for, you can exit the shell and
the pod will be removed immediately.

The value for the `--interactive` flag is the command you'd like to start
inside the pod.

---

Instead of having to look up the name of a pod before running `copypod`, you
can also specify labels which match one or more pods that you'd like to copy.
`copypod` will then pick the first pod matching the lables and copy that for
you. This can be done with the `--selector` flag. It works the same way as for
the `kubectl` command.

If we for example have one or more pods with the label `app: my-great-service`
we can copy any of those pods without having to know the exact pod name by
running:

    $ copypod -l app=my-great-service -i bash
    root@pod-copy-1gk57f:/#


## Note regarding Alpine Linux

The `sleep` command in images based on Alpine Linux does not
support "infinity" as an argument unless the "coreutils" package is installed.
As a work around you can instead specify `--command "sleep 1d"` as an argument
to `copypod` to change the command run in the new pod.
