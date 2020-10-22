#
# Copyright (C) 2012-2015 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#


import gettext
import os
import shutil
import tempfile

from otopi import constants as otopicons
from otopi import plugin, util

from ovirt_engine_extension_aaa_ldap_setup import constants


def _(m):
    return gettext.dgettext(
        message=m,
        domain='ovirt-engine-extension-aaa-ldap-setup',
    )


@util.export
class Plugin(plugin.PluginBase):

    def _writeToFile(self, fileName, content, mode):
        self.logger.debug('Writing: %s', fileName)
        with open(
            fileName,
            mode
        ) as f:
            if content is not None:
                if isinstance(content, (list, tuple)):
                    f.write('\n'.join(content) + '\n')
                else:
                    f.write(content)

    def _createToolLayout(self):
        extensionsDir = None
        try:
            extensionsDir = tempfile.mkdtemp()
            os.mkdir(os.path.join(extensionsDir, 'extensions.d'))
            os.mkdir(os.path.join(extensionsDir, 'aaa'))

            for e in (
                (
                    constants.LDAPEnv.CONFIG_AUTHN,
                    self.environment[
                        constants.LDAPEnv.CONFIG_AUTHN_FILE_NAME
                    ],
                    'w',
                ),
                (
                    constants.LDAPEnv.CONFIG_AUTHZ,
                    self.environment[
                        constants.LDAPEnv.CONFIG_AUTHZ_FILE_NAME
                    ],
                    'w',
                ),
                (
                    constants.LDAPEnv.CONFIG_PROFILE,
                    self.environment[
                        constants.LDAPEnv.CONFIG_PROFILE_FILE_NAME
                    ],
                    'w',
                ),
                (
                    constants.LDAPEnv.CONFIG_JKS,
                    self.environment[
                        constants.LDAPEnv.CONFIG_JKS_FILE_NAME
                    ],
                    'w+b', # JKS is a binary file
                ),
            ):
                self._writeToFile(
                    os.path.join(
                        extensionsDir,
                        e[1],
                    ),
                    self.environment[e[0]],
                    e[2],
                )

            ret = extensionsDir
            extensionsDir = None
            return ret
        finally:
            if extensionsDir is not None and os.path.exists(extensionsDir):
                shutil.rmtree(extensionsDir)

    def sequenceLogin(self, extensionsDir, user=None, password=None):
        self.dialog.note(
            text=(
                _('Please provide credentials to test login flow:')
            )
        )
        if user is None:
            user = self.dialog.queryString(
                name='OVAAALDAP_LDAP_TOOL_SEQUENCE_LOGIN_USER',
                note=_(
                    'Enter user name: '
                ),
                prompt=True,
            )
        if password is None:
            password = self.dialog.queryString(
                name='OVAAALDAP_LDAP_TOOL_SEQUENCE_LOGIN_PASSWORD',
                note=_(
                    'Enter user password: '
                ),
                prompt=True,
                hidden=True
            )
        self.environment[
            otopicons.CoreEnv.LOG_FILTER
        ].append(password)

        self.logger.info(_('Executing login sequence...'))
        rc, stdout, stderr = self.execute(
            args=(
                os.path.join(
                    constants.FileLocations.BIN_DIR,
                    'ovirt-engine-extensions-tool',
                ),
                '--extensions-dir=%s/extensions.d' % extensionsDir,
                'aaa', 'login-user',
                '--profile=%s' % self.environment[
                    constants.LDAPEnv.AAA_PROFILE_NAME
                ],
                '--user-name=%s' % user,
                '--password=env:pass',
            ),
            envAppend={
                'pass': password,
            },
            raiseOnError=False,
        )
        self.dialog.note(
            text=(
                (_('Login output:'),) +
                tuple(stderr)
            )
        )
        if rc == 0:
            self.logger.info("Login sequence executed successfully")
            self.dialog.note(
                text=(
                    _(
                        'Please make sure that user details are correct '
                        'and group membership meets expectations '
                        '(search for PrincipalRecord and GroupRecord titles).'
                    ),
                    _(
                        'Abort if output is incorrect.'
                    ),
                )
            )
        else:
            self.logger.error(_('Login sequence failed'))
            self.dialog.note(
                text=(
                    _(
                        'Please investigate details of the failure '
                        '(search for lines containing SEVERE log level).'
                    )
                )
            )
        return rc == 0

    def sequenceSearch(self, extensionsDir):
        self.dialog.note(
            text=(
                _('Please provide parameters for Search sequence:')
            )
        )
        entity = self.dialog.queryString(
            name='OVAAALDAP_LDAP_TOOL_SEQUENCE_SEARCH_ENTITY',
            note=_(
                'Select entity to search (@VALUES@) [@DEFAULT@]: '
            ),
            prompt=True,
            caseSensitive=False,
            validValues=('Principal', 'Group'),
            default='Principal',
        )
        name = self.dialog.queryString(
            name='OVAAALDAP_LDAP_TOOL_SEQUENCE_SEARCH_NAME',
            note=_("Term to search, trailing '*' is allowed: "),
            prompt=True,
        )
        resolveGroups = self.dialog.queryString(
            name='OVAAALDAP_LDAP_TOOL_SEQUENCE_SEARCH_RESOLVE_GROUPS',
            note=_('Resolve Groups (@VALUES@) [@DEFAULT@]: '),
            prompt=True,
            caseSensitive=False,
            validValues=(_('Yes'), _('No')),
            default=_('No'),
        ) != _('No').lower()

        self.logger.info(_('Executing search sequence...'))
        rc, stdout, stderr = self.execute(
            args=(
                os.path.join(
                    constants.FileLocations.BIN_DIR,
                    'ovirt-engine-extensions-tool',
                ),
                '--extensions-dir=%s/extensions.d' % extensionsDir,
                'aaa', 'search',
                '--extension-name=%s%s' % (
                    self.environment[constants.LDAPEnv.AAA_PROFILE_NAME],
                    '' if self.environment[
                        constants.LDAPEnv.AAA_USE_VM_SSO
                    ] else '-authz'
                ),
                '--entity=%s' % entity,
                '--entity-name=%s' % name,
            ) +
            (
                () if not resolveGroups
                else (
                    '--authz-flag=resolve-groups',
                    '--authz-flag=resolve-groups-recursive',
                )
            ),
            raiseOnError=False,
        )
        self.dialog.note(
            text=(
                (_('Login output:'),) +
                tuple(stderr)
            )
        )
        if rc == 0:
            self.logger.info("Search sequence executed successfully")
            self.dialog.note(
                text=(
                    _(
                        'Please make sure that entity details are correct '
                        'and that depending on the type of the query group '
                        'membership meets expectations (search for '
                        'PrincipalRecord and GroupRecord titles).'
                    ),
                    _(
                        'Abort if output is incorrect'
                    ),
                )
            )
        else:
            self.logger.error(_('Search sequence failed'))
            self.dialog.note(
                text=(
                    _(
                        'Please investigate details of the failure '
                        '(search for lines containing SEVERE log level).'
                    )
                )
            )
        return rc == 0

    def __init__(self, context):
        super(Plugin, self).__init__(context=context)

    @plugin.event(
        stage=plugin.Stages.STAGE_INIT,
    )
    def _init(self):
        self.environment.setdefault(
            constants.LDAPEnv.TOOL_ENABLE,
            True
        )

    @plugin.event(
        stage=plugin.Stages.STAGE_VALIDATION,
        condition=lambda self: self.environment[
            constants.LDAPEnv.TOOL_ENABLE
        ],
    )
    def _validation(self):
        extensionsDir = self._createToolLayout()
        try:
            self.dialog.note(
                (
                    ' ',
                    _('NOTE:'),
                    _(
                        'It is highly recommended to test drive the '
                        'configuration before applying it into engine.'
                    ),
                    _(
                        'Login sequence is executed automatically, '
                        'but it is recommended to also execute Search '
                        'sequence manually after successful Login sequence.'
                    ),
                    ' ',
                )
            )
            # By default force user to test login:
            sequenceResult = self.sequenceLogin(extensionsDir)
            while True:
                sequence = self.dialog.queryString(
                    name='OVAAALDAP_LDAP_TOOL_SEQUENCE',
                    note=_(
                        'Select test sequence to execute (@VALUES@) '
                        '[@DEFAULT@]: '
                    ),
                    prompt=True,
                    caseSensitive=False,
                    validValues=(
                        _('Done'),
                        _('Abort'),
                        _('Login'),
                        _('Search'),
                    ),
                    default=_('Done' if sequenceResult else 'Abort'),
                )
                if sequence == _('Done').lower():
                    break
                elif sequence == _('Abort').lower():
                    raise RuntimeError(_('Aborted by user'))
                elif sequence == _('Login').lower():
                    sequenceResult = self.sequenceLogin(extensionsDir)
                elif sequence == _('Search').lower():
                    sequenceResult = self.sequenceSearch(extensionsDir)
        finally:
            if extensionsDir is not None and os.path.exists(extensionsDir):
                shutil.rmtree(extensionsDir)


# vim: expandtab tabstop=4 shiftwidth=4
