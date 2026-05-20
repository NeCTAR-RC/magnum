#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Starter script for magnum-template-manage.

Operator-only utility for managing the ``upgrade_targets`` label on cluster
templates. The label is a comma-separated list of cluster template UUIDs
that clusters using the template are permitted to upgrade to. An empty
string blocks all upgrades for clusters using that template.

The script writes directly to the database and bypasses the API-level
restriction that prevents updates to cluster templates already referenced
by an existing cluster.
"""

import sys

from oslo_config import cfg
from oslo_log import log as logging

import magnum.conf
from magnum.db.sqlalchemy import api as db_sa
from magnum.db.sqlalchemy import models

CONF = magnum.conf.CONF
LABEL_KEY = 'upgrade_targets'


def _find_template(session, ident):
    query = session.query(models.ClusterTemplate)
    template = query.filter_by(uuid=ident).first()
    if template is None:
        template = query.filter_by(name=ident).first()
    return template


def _apply_targets(template, targets):
    # Reassign rather than mutate in place so SQLAlchemy detects the change
    # on the JSONEncodedDict column.
    labels = dict(template.labels or {})
    labels[LABEL_KEY] = targets
    template.labels = labels


def _confirm(prompt):
    try:
        answer = input("%s [y/N]: " % prompt)
    except EOFError:
        return False
    return answer.strip().lower() in ('y', 'yes')


def do_set_upgrade_targets():
    args = CONF.command
    targets = args.targets

    with db_sa._session_for_write() as session:
        if args.all:
            if not args.yes and not _confirm(
                    "Set %s=%r on ALL cluster templates?" % (
                        LABEL_KEY, targets)):
                print("Aborted.", file=sys.stderr)
                return 1
            templates = session.query(models.ClusterTemplate).all()
            for template in templates:
                _apply_targets(template, targets)
                print("Updated %s (%s)" % (template.name, template.uuid))
            print("Updated %d cluster template(s)." % len(templates))
            return 0

        if not args.template:
            print("error: provide a template UUID/name or pass --all",
                  file=sys.stderr)
            return 2

        template = _find_template(session, args.template)
        if template is None:
            print("No cluster template found matching %r" % args.template,
                  file=sys.stderr)
            return 1
        _apply_targets(template, targets)
        print("Updated %s (%s): %s=%r" % (
            template.name, template.uuid, LABEL_KEY, targets))
        return 0


def add_command_parsers(subparsers):
    set_p = subparsers.add_parser(
        'set-upgrade-targets',
        help="Set the upgrade_targets label on one or all cluster templates.")
    set_p.add_argument(
        'template', nargs='?',
        help="UUID or name of the cluster template to update. Omit when "
             "using --all.")
    set_p.add_argument(
        '--all', action='store_true',
        help="Apply to every cluster template. Requires confirmation unless "
             "--yes is given.")
    set_p.add_argument(
        '--targets', required=True,
        help="Comma-separated list of cluster template UUIDs to allow as "
             "upgrade targets. Pass '' to block all upgrades.")
    set_p.add_argument(
        '--yes', action='store_true',
        help="Skip the confirmation prompt for --all.")
    set_p.set_defaults(func=do_set_upgrade_targets)


command_opt = cfg.SubCommandOpt('command',
                                title='Command',
                                help='Available commands',
                                handler=add_command_parsers)


def main():
    logging.register_options(CONF)
    CONF.register_cli_opt(command_opt)
    CONF(project='magnum')
    sys.exit(CONF.command.func() or 0)
