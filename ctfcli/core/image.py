import click
import json
import socket
import subprocess
import tempfile
from os import PathLike
from pathlib import Path
from timeit import default_timer
from typing import Dict, List, Optional, Union


class Image:
    def __init__(self, name: str, build_path: Optional[Union[str, PathLike]] = None):
        # name can be either a new name to assign or an existing image name
        self.name = name

        # if the image is a remote image (eg. ghcr.io/.../...), extract the basename
        self.basename = name
        if "/" in self.name or ":" in self.name:
            self.basename = self.name.split(":")[0].split("/")[-1]

        self.built = True

        # if the image provides a build path, assume it is not built yet
        if build_path:
            self.build_path = Path(build_path)
            self.built = False
        
        # Should be None when no container is running and str when one is
        # str with no container is an unexpected state
        self.container = None
        self._ip = None

    @property
    def ip(self) -> Optional[str]:
        if not self.running:
            return
        if not self._ip:
            result = subprocess.run(["docker", "inspect", self.container, "--format={{.NetworkSettings.IPAddress}}"], capture_output=True, text=True, check=True)
            self._ip = result.stdout.strip()
        return self._ip

    @property
    def running(self) -> bool:
        if not self.container:
            return False
        result = subprocess.run(["docker", "inspect", self.container, "--format={{json .State.Running}}"], capture_output=True, text=True, check=True)
        output = result.stdout.strip()
        if output == "true":
            return True
        else:
            # If we reach here, stop has not been called (self.container != None with no container running)
            # Warn the user
            click.secho(
                f"Container from {self.name} exited unexpectedly.",
                fg="yellow",
            )
            self.container = None
            return False

    def build(self) -> Optional[str]:
        docker_build = subprocess.call(["docker", "build", "-t", self.name, "."], cwd=self.build_path.absolute())
        if docker_build != 0:
            return

        self.built = True
        return self.name
    
    def run(self, environment: Dict[str, str]) -> Optional[str]:
        if not self.built:
            self.build()
        if self.running:
            return self.container

        command = ["docker", "run", "--rm", "-d"]
        for variable in environment:
            command.append("-e")
            command.append(variable + "=" + environment[variable])
        command.append(self.name)

        result = subprocess.run(command, capture_output=True, text=True, check=True)
        # Will return a container ID
        self.container = result.stdout.strip()
        return self.container
    
    def stop(self) -> Optional[str]:
        if not self.running:
            return
        subprocess.check_call(["docker", "stop", self.container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return_value = self.container
        # This means the container down state is expected
        self.container = None
        return return_value


    def pull(self) -> Optional[str]:
        docker_pull = subprocess.call(["docker", "pull", self.name])
        if docker_pull != 0:
            return

        return self.name

    def push(self, location: str) -> Optional[str]:
        if not self.built:
            self.build()

        docker_tag = subprocess.call(["docker", "tag", self.name, location])
        docker_push = subprocess.call(["docker", "push", location])

        if any(r != 0 for r in [docker_tag, docker_push]):
            return

        return location

    def export(self) -> Optional[str]:
        if not self.built:
            self.build()

        image_tar = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{self.basename}.docker.tar")
        docker_save = subprocess.call(["docker", "save", "--output", image_tar.name, self.name])

        if docker_save != 0:
            return

        return image_tar.name
    
    def _get_exposed_port_strings(self) -> Optional[List[str]]:
        if not self.built:
            self.build()

        try:
            docker_output = subprocess.check_output(
                ["docker", "inspect", "--format={{json .Config.ExposedPorts}}", self.name]
            )
        except subprocess.CalledProcessError:
            return

        ports_data = json.loads(docker_output)
        if ports_data:
            ports = list(ports_data.keys())
            return ports
    
    def ports_by_protocol(self, protocol: str = "tcp") -> Optional[List[int]]:
        raw_ports = self._get_exposed_port_strings()
        if not raw_ports:
            return
        ports = []
        for port in raw_ports:
            num, proto = port.split("/")
            if proto == protocol:
                ports.append(int(num))
        return ports
    
    def wait_for_exposed_ports(self, timeout=30) -> bool:
        if not self.running:
            # We could run, but the user might have environment variables they want
            return False
        ports = self.ports_by_protocol("tcp")
        start_time = default_timer()

        for port in ports:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)

            while default_timer() - start_time < timeout:
                if not s.connect_ex((self.ip, port)):
                    # Break out of the loop for this port,
                    # indicating success
                    break
            else:
                # If we exit the loop due to a timeout
                click.secho(
                    f"Timeout reached waiting for {self.name} to bring up exposed ports.",
                    fg="yellow",
                )
                # Break out of the overarching loop
                break
        else:
            # This runs only if we successfully connect to each port
            return True
        # And if we don't:
        return False