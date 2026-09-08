from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import paramiko

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SSHCredentials:
    host: str
    port: int
    username: str
    password: str | None = None
    key_filename: str | None = None


def connect(credentials: SSHCredentials, timeout: float) -> tuple[paramiko.SSHClient, paramiko.Channel]:
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    if os.getenv("RTR_SSH_AUTO_ADD_HOST_KEY", "1") == "1":
        logger.warning("Unknown SSH host keys are accepted; set RTR_SSH_AUTO_ADD_HOST_KEY=0 for strict checking")
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    client.connect(
        hostname=credentials.host,
        port=credentials.port,
        username=credentials.username,
        password=credentials.password,
        key_filename=credentials.key_filename,
        timeout=timeout,
        banner_timeout=timeout,
        auth_timeout=timeout,
        look_for_keys=credentials.password is None and credentials.key_filename is None,
        allow_agent=credentials.password is None and credentials.key_filename is None,
    )
    channel = client.invoke_shell(term="xterm-256color", width=140, height=40)
    channel.settimeout(0.5)
    return client, channel

