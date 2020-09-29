#!/usr/bin/python
# coding: utf-8
#
# Copyright 2020 Guillaume Charbonnier (@gucharbon) <gu.charbon@gmail.com>
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function
__metaclass__ = type


ANSIBLE_METADATA = {'metadata_version': '1.1',
                    'status': ['preview'],
                    'supported_by': 'community'}


DOCUMENTATION = u'''
module: docker_plugin
short_description: Manage Docker plugins
description:
  - Install/remove Docker plugins.
  - Performs largely the same function as the C(docker plugin) CLI subcommand.
options:
  name:
    description:
      - Name of the plugin to operate on.
    type: str

  alias:
    description:
      - Alias of the plugin to operate on. Same plugin can be installed with different alias.
    required: true
    type: str

  plugin_options:
    description:
      - Dictionary of plugin settings.
    type: dict

  state:
    description:
      - C(absent) remove the plugin.
      - C(present) install the plugin, if it does not already exist.
      - C(enabled) enable the plugin.
      - C(disabled) disable the plugin.
    default: present
    choices:
      - absent
      - present
      - enabled
      - disabled

extends_documentation_fragment:
  - docker
  - docker.docker_py_2_documentation

author:
  - Guillaume Charbonnier (@gucharbon)

requirements:
  - "L(Docker SDK for Python,https://docker-py.readthedocs.io/en/stable/) >= 1.10.0"
  - "The docker server >= 1.9.0"
'''

EXAMPLES = '''
- name: Install and enable a plugin
  docker_plugin:
    name: grafana/loki-docker-driver:latest
    alias: loki
    state: enabled

- name: Disable a plugin
  docker_plugin:
    alias: loki
    state: disabled

- name: Remove a plugin
  docker_plugin:
    alias: loki
    state: absent

- name: Install a plugin with options
  docker_plugin:
    name: grafana/loki-docker-driver:latest
    alias: loki
    plugin_options:
      LOG_LEVEL: DEBUG
'''

RETURN = '''
facts:
    description: Plugin inspection results for the affected plugin.
    returned: success
    type: dict
    sample: {}
'''

try:
    from docker.errors import APIError, NotFound
    from docker.models.plugins import Plugin
    from docker import DockerClient
except ImportError:
    # missing docker-py handled in ansible.module_utils.docker_common
    pass

from ansible_collections.community.general.plugins.module_utils.docker.common import DockerBaseClass, AnsibleDockerClient, DifferenceTracker
from ansible.module_utils.six import text_type


class TaskParameters(DockerBaseClass):
    def __init__(self, client):
        super(TaskParameters, self).__init__()
        self.client = client

        self.name = None
        self.alias = None
        self.plugin_options = None
        self.debug = None

        for key, value in client.module.params.items():
            setattr(self, key, value)


def prepare_options(options):
    return ['%s=%s' % (k, v if v is not None else "") for k, v in options.items()] if options else []


def parse_options(options_list):
    return dict((k, v) for k, v in map(lambda x: x.split('=', 1), options_list)) if options_list else {}


def wrap_error(prefix, error):
    error_message = text_type(error)
    return ". ".join([str(prefix), str(error_message)])


class DockerPluginManager(object):

    def __init__(self, client):
        self.client = client

        self.dclient = DockerClient(**self.client._connect_params)
        self.dclient.api = client

        self.parameters = TaskParameters(client)
        self.check_mode = self.client.check_mode
        self.results = {
            u'changed': False,
            u'actions': []
        }
        self.diff = self.client.module._diff
        self.diff_tracker = DifferenceTracker()
        self.diff_result = dict()

        self.existing_plugin = self.get_existing_plugin()

        state = self.parameters.state
        if state == 'present':
            self.present()
        elif state == 'absent':
            self.absent()
        elif state == 'enabled':
            self.enable()
        elif state == 'disabled':
            self.disable()

        if self.diff or self.check_mode or self.parameters.debug:
            if self.diff:
                self.diff_result['before'], self.diff_result['after'] = self.diff_tracker.get_before_after()
            self.results['diff'] = self.diff_result


    def get_existing_plugin(self):
        """Return an existing plugin or None."""
        alias = self.parameters.alias
        try:
            plugin = self.dclient.plugins.get(alias)
        except NotFound:
            return None
        except APIError as error:
            msg = wrap_error("Failed to query existing plugins", error)
            self.client.fail(msg)
        else:
            return plugin
        return None

    def has_different_config(self):
        """
        Return the list of differences between the current parameters and the existing plugin.

        :return: list of options that differ
        """
        differences = DifferenceTracker()
        if self.parameters.plugin_options:
            existing_options = parse_options(self.existing_plugin.settings['Env'])
            if not existing_options:
                differences.add('plugin_options', parameter=self.parameters.plugin_options, active=existing_options)
            else:
                for key, value in self.parameters.plugin_options.items():
                    active_value = existing_options.get(key)
                    if active_value != value:
                        differences.add('plugin_options.%s' % key, parameter=value, active=active_value)
        return differences

    def install_plugin(self):
        # Perform action only when plugin is not already installed
        if not self.existing_plugin:
            if not self.check_mode:
                try:
                    self.existing_plugin = self.dclient.plugins.install(self.parameters.name, self.parameters.alias)
                except APIError as error:
                    msg = wrap_error(
                        prefix="Failed to install local docker logging plugin %s from %s" % (self.parameters.alias, self.parameters.name),
                        error=error
                    )
                    self.client.fail(msg)
            # Set results
            self.results['actions'].append("Installed local docker logging plugin %s from %s." % (self.parameters.alias, self.parameters.name))
            self.results['changed'] = True

    def remove_plugin(self):
        # Perform action only when plugin is installed
        if self.existing_plugin:
            if not self.check_mode:
                try:
                    self.existing_plugin.remove()
                except APIError as error:
                    msg = wrap_error(
                        prefix="Failed to remove local docker logging plugin %s" % self.parameters.alias,
                        error=error
                    )
                    self.client.fail(msg)
            # Set results
            self.results['actions'].append("Removed local docker logging plugin %s." % self.parameters.alias)
            self.results['changed'] = True

    def enable_plugin(self, main_action=True):
        # We want to know if the plugin is installed
        self.existing_plugin = self.get_existing_plugin()
        if not self.existing_plugin.enabled:
            if not self.check_mode:
                try:
                    self.existing_plugin.enable(1)
                except APIError as error:
                    msg = wrap_error(
                        prefix=(
                            "Failed to enable local docker logging plugin %s. " % self.parameters.alias,
                        ),
                        error=error
                    )
                    self.client.fail(msg)
            # Set results optionnaly
            if main_action:
                self.results['actions'].append("Enabled local docker logging plugin %s." % self.parameters.alias)
                self.results['changed'] = True

    def disable_plugin(self, main_action=True):
        if self.existing_plugin: 
            if self.existing_plugin.enabled:
                if not self.check_mode:
                    try:
                        self.existing_plugin.disable()
                    except APIError as error:
                        msg = wrap_error(
                            prefix=(
                                "Failed to disable local docker logging plugin %s. " % self.parameters.alias,
                            ),
                            error=error
                        )
                        self.client.fail(msg)
                # Set results optionnaly
                if main_action:
                    self.results['actions'].append("Disabled local docker logging plugin %s." % self.parameters.alias)
                    self.results['changed'] = True

    def update_plugin(self, differences):
        if not self.check_mode:
            must_enable = self.parameters.state == "enabled"
            # Plugin must be disabled to be updated
            if self.existing_plugin.enabled:
                self.disable_plugin(main_action=False)
                if self.parameters.state in ["present", "enabled"]:
                    need_enable = True
            # Update the configuration
            try:
                self.existing_plugin.configure(prepare_options(self.parameters.plugin_options))
            except APIError as error:
                msg = wrap_error(
                    prefix=(
                        "Failed to update local docker logging plugin %s" % self.parameters.alias,
                    ),
                    error=error
                )
                self.client.fail(msg)
            # Enable the plugin when needed
            if must_enable:
                self.enable_plugin(main_action=False)
        # Set results
        self.results['actions'].append("Updated local docker logging plugin %s settings." % self.parameters.alias)
        self.results['changed'] = True

    def present(self):
        differences = DifferenceTracker()

        if self.existing_plugin:
            differences = self.has_different_config()

        self.diff_tracker.add('exists', parameter=True, active=self.existing_plugin is not None)

        if not differences.empty:
            # Plugin already exists
            self.update_plugin(differences)
        else:
            # Let's install plugin
            self.install_plugin()

        if self.diff or self.check_mode or self.parameters.debug:
            self.results['diff'] = differences.get_legacy_docker_diffs()
            self.diff_tracker.merge(differences)

        if not self.check_mode and not self.parameters.debug:
            self.results.pop('actions')

    def absent(self):
        self.remove_plugin()

    def enable(self):
        differences = DifferenceTracker()

        if self.existing_plugin:
            differences = self.has_different_config()

        self.diff_tracker.add('exists', parameter=True, active=self.existing_plugin is not None)

        # Plugin already exists
        if not differences.empty:
            # Let's update plugin
            self.update_plugin(differences)
        else:
            # Or install and enable plugin
            self.install_plugin()
            self.enable_plugin()

        if self.diff or self.check_mode or self.parameters.debug:
            self.results['diff'] = differences.get_legacy_docker_diffs()
            self.diff_tracker.merge(differences)

        if not self.check_mode and not self.parameters.debug:
            self.results.pop('actions')

    def disable(self):
        self.disable_plugin()


def main():
    argument_spec = dict(
        name=dict(type='str'),
        alias=dict(type='str', required=True),
        state=dict(type='str', default='present', choices=['present', 'absent', 'enabled', 'disabled']),
        plugin_options=dict(type='dict', default={}),
        debug=dict(type='bool', default=False)
    )

    required_if = [
        ('state', 'present', ['name'])
    ]

    client = AnsibleDockerClient(
        argument_spec=argument_spec,
        required_if=required_if,
        supports_check_mode=True,
        min_docker_version='2.6.0',
        min_docker_api_version='1.25'
    )

    cm = DockerPluginManager(client)
    client.module.exit_json(**cm.results)


if __name__ == '__main__':
    main()
