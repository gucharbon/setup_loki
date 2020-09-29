# Setup LOki

Quicly setup loki on an Ubuntu server:

- Download binary
- Define systemd service
- Start service

## Requirements

You need to have an SSH access to the remote host in order to play this role. The remote host must run a modern systemd-base distribution.

## Role Variables

| Variable name                   | Default value | Description                                        |
| ------------------------------- | ------------- | -------------------------------------------------- |
| loki_version                    | `1.6.1`       | version of loki                                    |
| loki_system_user                | `loki`        | user for running loki                              |
| loki_system_group               | `loki`        | group for running loki                             |
| loki_server_http_listen_port    | `3100`        | listen port for loki                               |
| loki_server_http_listen_address | `localhost`   | listen address for loki                            |
| loki_directories                | `{}`          | array of directories to create before running loki |
| loki_schema_config              | default dict  | YAML with schema config                            |
| loki_storage_config             | default dict  | YAML with storage config                           |
| loki_ingester                   | default dict  | YAML with ingester settings                        |
| loki_limits_config              | default dict  | YAML with limits settings                          |
| loki_chunk_store_config         | default dict  | YAML with chuck store settings                     |
| loki_table_manager              | default dict  | YAML with table manager settings                   |

## Example Playbook

A minimal example playbook to bind loki to all interfaces:

```yaml
- hosts: localhost
  roles:
    - role: gucharbon.setup_loki
      vars:
        loki_server_http_listen_address: 0.0.0.0
```

## License

MIT
