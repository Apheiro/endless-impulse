"""UX bridge regression tests. Every host read, permission and CLI call is mocked."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

BRIDGE = Path(__file__).resolve().parents[1] / 'src/quickshell/scripts/firewalld/control.py'
spec = importlib.util.spec_from_file_location('firewall_ux_bridge', BRIDGE)
fw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fw)

CAPABILITIES = ['new-zone', 'new-service', 'new-ipset', 'change-interface', 'get-ipsets',
                'get-icmptypes', 'info-service', 'info-ipset', 'add-port', 'remove-port',
                'add-entry', 'remove-entry'] + [prefix + field for prefix in ('add-', 'remove-')
                    for field in ('protocol', 'source-port', 'icmp-block', 'rich-rule', 'source')]


def state():
    zones = [{'name': 'custom-lab', 'active': True, 'fields': {
        'interfaces': 'radio9', 'sources': '', 'services': 'ssh', 'ports': '', 'protocols': 'esp',
        'source-ports': '53/udp', 'icmp-blocks': 'echo-request',
        'rich rules': 'rule family="ipv4" source address="192.0.2.0/24" log prefix="test: ñ" accept',
        'forward-ports': 'port=8080:proto=tcp:toport=80:toaddr=192.0.2.1',
        'masquerade': 'no', 'forward': 'yes'}},
        {'name': 'second-zone', 'active': False, 'fields': {'interfaces': '', 'sources': ''}}]
    snapshot = dict(connected=True, complete=True, defaultZone='second-zone', services=['ssh'],
                    capabilities=CAPABILITIES, connections=[],
                    scopes={scope: dict(zones=copy.deepcopy(zones), policies=[]) for scope in ('runtime', 'permanent')},
                    catalogs={scope: dict(services=['ssh', 'custom-service'], ipsets=['lab-set'], icmptypes=['echo-request', 'echo-reply'])
                              for scope in ('runtime', 'permanent')})
    snapshot['revision'] = fw.revision(snapshot)
    return snapshot


class FirewallUxTests(unittest.TestCase):
    def setUp(self):
        self.client = fw.Firewall('/fixture/firewall-cmd')
        self.state = state()
        self.call = patch.object(self.client, 'call', return_value='success').start()
        self.addCleanup(patch.stopall)

    def request(self, action, value=None, scope='runtime', **extra):
        return dict(action=action, value=value, scope=scope, zone='custom-lab',
                    revision=self.state['revision'], confirmed=True, **extra)

    def test_mapping_independent_of_type_default_and_nonstandard_zone_names(self):
        links = [dict(ifname='radio9', operstate='UP'), dict(ifname='cable9', operstate='DOWN'),
                 dict(ifname='tunnel9', operstate='UNKNOWN', linkinfo={'info_kind': 'wireguard'})]
        nm = '''GENERAL.DEVICE:radio9
GENERAL.TYPE:wifi
GENERAL.STATE:100 (connected)
GENERAL.CONNECTION:Lab\\: network
GENERAL.NM-MANAGED:yes
GENERAL.DEVICE:cable9
GENERAL.TYPE:ethernet
GENERAL.STATE:30 (disconnected)
GENERAL.CONNECTION:--
GENERAL.NM-MANAGED:no
'''
        def read(argv):
            if argv[0] == 'nmcli': return nm
            if 'address' in argv: return json.dumps(links)
            return json.dumps([dict(dev='radio9', metric=600), dict(dev='cable9', metric=900)])
        with patch.object(self.client, 'host_read', side_effect=read):
            rows = {c['interface']: c for c in self.client.connections(self.state)}
        self.assertEqual(rows['radio9']['zone'], 'custom-lab')
        self.assertEqual(rows['radio9']['name'], 'Lab: network')
        self.assertEqual(rows['radio9']['type'], 'wifi')
        self.assertEqual(rows['radio9']['manager'], 'NetworkManager')
        self.assertFalse(rows['radio9']['canAssign'])
        self.assertTrue(rows['radio9']['primary'])
        self.assertEqual(rows['cable9']['zone'], 'second-zone')
        self.assertEqual(rows['cable9']['binding'], 'default')
        self.assertTrue(rows['cable9']['canAssign'])
        self.assertFalse(rows['tunnel9']['canAssign'])
        self.assertEqual(rows['tunnel9']['zone'], 'second-zone')
        self.assertEqual(sum(c['primary'] for c in rows.values()), 1)
        self.call.assert_not_called()

    def test_missing_inventory_is_not_a_fictitious_primary_or_type(self):
        with patch.object(self.client, 'host_read', return_value=''):
            rows = self.client.connections(self.state)
        self.assertEqual([r['interface'] for r in rows], ['radio9'])
        self.assertEqual(rows[0]['type'], 'Unknown')
        self.assertFalse(rows[0]['primary'])
        self.assertFalse(rows[0]['canAssign'])
        self.assertTrue(rows[0]['assignmentReason'])

    def test_assignment_scope_ownership_confirmation_and_actual_postcondition(self):
        connection = dict(interface='cable9', zone='second-zone', binding='default', permanentZone='', canAssign=True)
        self.state['connections'] = [connection]
        self.state['revision'] = fw.revision(self.state)
        for scope in ('runtime', 'permanent'):
            request = self.request('change-interface', 'cable9', scope)
            command = self.client.command(request, self.state)
            self.assertEqual(command, (['--permanent'] if scope == 'permanent' else []) + ['--zone=custom-lab', '--change-interface=cable9'])
            applied = copy.deepcopy(self.state)
            applied['connections'][0]['zone' if scope == 'runtime' else 'permanentZone'] = 'custom-lab'
            with patch.object(self.client, 'snapshot', side_effect=[self.state, applied]):
                self.assertEqual(self.client.handle(request)['operationState'], 'applied')
            with patch.object(self.client, 'snapshot', return_value=self.state):
                self.assertEqual(self.client.handle(request)['operationState'], 'applied-unverified')
        self.state['connections'][0]['canAssign'] = False
        with self.assertRaises(ValueError):
            self.client.command(self.request('change-interface', 'cable9'), self.state)
        with self.assertRaises(ValueError):
            self.client.command(self.request('change-interface', '--reload'), self.state)

    def test_definition_creation_permanent_only_and_no_implicit_assignment_or_reload(self):
        for kind in ('zone', 'service', 'ipset'):
            request = self.request('new-' + kind, 'new-lab', 'permanent')
            command = self.client.command(request, self.state)
            self.assertEqual(command[:2], ['--permanent', '--new-' + kind + '=new-lab'])
            self.assertNotIn('--zone=custom-lab', command)
            self.assertFalse(any('reload' in arg or 'add-source' in arg or 'add-service' in arg for arg in command))
            if kind == 'ipset': self.assertEqual(command[2:], ['--type=hash:ip', '--option=family=inet'])
            with self.assertRaises(ValueError): self.client.command(self.request('new-' + kind, 'new-lab'), self.state)
            for name in ('', '--reload', 'two words', 'x;id', 'ñ', 'a' * 18):
                with self.subTest(kind=kind, name=name), self.assertRaises(ValueError):
                    self.client.command(self.request('new-' + kind, name, 'permanent'), self.state)
        with self.assertRaises(ValueError): self.client.command(self.request('new-zone', 'custom-lab', 'permanent'), self.state)
        with self.assertRaises(ValueError): self.client.command(self.request('new-service', 'ssh', 'permanent'), self.state)
        for action in ('delete-zone', 'duplicate-zone', 'delete-service', 'delete-ipset', 'reload', 'runtime-to-permanent'):
            with self.assertRaises(ValueError): self.client.command(self.request(action, 'new-lab', 'permanent'), self.state)
        self.call.assert_not_called()

    def test_creation_postcondition_requires_catalog_observation(self):
        for kind in ('zone', 'service', 'ipset'):
            request = self.request('new-' + kind, 'new-lab', 'permanent')
            after = copy.deepcopy(self.state)
            if kind == 'zone': after['scopes']['permanent']['zones'].append(dict(name='new-lab', fields={}))
            else: after['catalogs']['permanent'][kind + 's'].append('new-lab')
            with patch.object(self.client, 'snapshot', side_effect=[self.state, after]):
                self.assertEqual(self.client.handle(request)['operationState'], 'applied')
            with patch.object(self.client, 'snapshot', return_value=self.state):
                self.assertEqual(self.client.handle(request)['operationState'], 'applied-unverified')

    def test_advanced_arguments_preserve_whole_rich_rules_and_semantics(self):
        rich = self.state['scopes']['runtime']['zones'][0]['fields']['rich rules']
        for action, value in [('add-protocol', '47'), ('remove-protocol', 'esp'),
                              ('add-source-port', '1000-1010/udp'), ('remove-source-port', '53/udp'),
                              ('add-icmp-block', 'echo-reply'), ('remove-icmp-block', 'echo-request'),
                              ('add-source', '2001:db8::/32'), ('add-source', 'ipset:lab-set'),
                              ('remove-rich-rule', rich), ('add-rich-rule', 'rule service name="http" accept')]:
            with self.subTest(action=action):
                command = self.client.command(self.request(action, value), self.state)
                self.assertEqual(command, ['--zone=custom-lab', '--' + action + '=' + value])
        for action, value in [('add-protocol', '256'), ('add-protocol', '--reload'),
                              ('add-source-port', '0/tcp'), ('add-icmp-block', 'made-up'),
                              ('add-source', 'not a source'), ('add-source', 'ipset:missing'),
                              ('add-rich-rule', 'rule accept\n--reload')]:
            with self.subTest(action=action), self.assertRaises(ValueError):
                self.client.command(self.request(action, value), self.state)
        for action in ('add-forward-port', 'set-target', 'set-icmp-block-inversion'):
            with self.assertRaises(ValueError): self.client.command(self.request(action, 'x'), self.state)
        self.call.assert_not_called()

    def test_bare_source_address_is_not_rewritten_as_a_different_binding(self):
        self.state['scopes']['runtime']['zones'][0]['fields']['sources'] = '192.0.2.1'
        command = self.client.command(self.request('remove-source', '192.0.2.1'), self.state)
        self.assertEqual(command[-1], '--remove-source=192.0.2.1')
        command = self.client.command(self.request('add-source', '192.0.2.2'), self.state)
        self.assertEqual(command[-1], '--add-source=192.0.2.2')

    def test_zone_metadata_exposes_deletion_only_after_dependency_preflight(self):
        detail = dict(name='custom-lab', fields={}, origin='custom', documentRevision='document')
        request = dict(action='inspect', kind='zone', name='custom-lab', scope='permanent')
        with patch.object(self.client, 'definition', return_value=detail), \
             patch.object(self.client, 'snapshot', return_value=self.state), \
             patch.object(self.client, 'check_zone_dependencies', side_effect=ValueError('Unresolved profiles')) as dependencies:
            result = self.client.handle(request)
            self.assertTrue(result['ok'])
            self.assertFalse(result['definition']['deletionAllowed'])
            self.assertEqual(result['definition']['deletionReason'], 'Unresolved profiles')
            dependencies.assert_called_once_with('custom-lab', self.state)
            dependencies.side_effect = None
            result = self.client.handle(request)
            self.assertTrue(result['definition']['deletionAllowed'])
            self.assertEqual(result['definition']['deletionRevision'], self.state['revision'])
        self.call.assert_not_called()

    def test_advanced_postconditions_use_full_line_and_selected_scope(self):
        rich = self.state['scopes']['runtime']['zones'][0]['fields']['rich rules']
        for action, value, field, observed in [('remove-rich-rule', rich, 'rich rules', ''),
                                              ('add-protocol', 'ah', 'protocols', 'esp ah'),
                                              ('add-source-port', '443/tcp', 'source-ports', '53/udp 443/tcp'),
                                              ('add-source', 'ipset:lab-set', 'sources', 'ipset:lab-set')]:
            after = copy.deepcopy(self.state)
            after['scopes']['permanent']['zones'][0]['fields'][field] = observed
            request = self.request(action, value, 'permanent')
            with patch.object(self.client, 'snapshot', side_effect=[self.state, after]):
                self.assertEqual(self.client.handle(request)['operationState'], 'applied')
            # A matching runtime edit must not be presented as a permanent success.
            with patch.object(self.client, 'snapshot', return_value=self.state):
                self.assertEqual(self.client.handle(request)['operationState'], 'applied-unverified')

    def test_definition_inspection_preserves_fields_without_mutation_or_interaction(self):
        self.call.return_value = 'custom-service\n  ports: 8080/tcp\n  includes: ssh\n  description: A real service\n  future-field: preserved'
        response = self.client.handle(dict(action='inspect', kind='service', name='custom-service', scope='permanent'))
        self.assertTrue(response['ok'])
        self.assertEqual(response['definition']['fields']['includes'], 'ssh')
        self.assertEqual(response['definition']['fields']['future-field'], 'preserved')
        self.assertTrue(response['definition']['revision'])
        self.assertFalse(self.client.allow_interaction)
        self.call.assert_called_once_with(['--permanent', '--info-service=custom-service'])
        self.call.reset_mock()
        for name in ('--reload', 'x;id', '../etc', None):
            self.assertFalse(self.client.handle(dict(action='inspect', kind='service', name=name, scope='runtime'))['ok'])
        self.call.assert_not_called()

    def test_definition_edits_have_separate_revision_and_type_safeguards(self):
        detail = dict(name='custom-service', revision='definition-1', fields={'ports': '8080/tcp'})
        with patch.object(self.client, 'definition', return_value=detail):
            request = self.request('definition-add-port', '443/tcp', 'permanent', name='custom-service', definitionRevision='definition-1')
            self.assertEqual(self.client.command(request, self.state), ['--permanent', '--service=custom-service', '--add-port=443/tcp'])
            request['definitionRevision'] = 'old'
            with self.assertRaises(fw.Failure): self.client.command(request, self.state)
        detail = dict(name='lab-set', revision='set-1', fields={'type': 'hash:ip', 'options': 'family=inet', 'entries': '192.0.2.1'})
        with patch.object(self.client, 'definition', return_value=detail):
            request = self.request('definition-add-entry', '192.0.2.2', 'permanent', name='lab-set', definitionRevision='set-1')
            self.assertEqual(self.client.command(request, self.state), ['--permanent', '--ipset=lab-set', '--add-entry=192.0.2.2'])
            detail['fields']['type'] = 'hash:net'
            with self.assertRaises(ValueError): self.client.command(request, self.state)
            detail['fields']['type'] = 'hash:ip'
            detail['fields']['options'] = 'family=inet timeout=60'
            with self.assertRaises(ValueError): self.client.command(request, self.state)
            detail['fields']['options'] = 'family=inet6'
            with self.assertRaises(ValueError): self.client.command(request, self.state)
        self.call.assert_not_called()

    def test_zone_duplicate_is_lossless_unbound_and_temporary_file_is_removed(self):
        document = b'''<zone target="DROP"><!-- license fixture --><short>Lab</short>
<description>Real metadata</description><interface name="radio9"/>
<source address="192.0.2.0/24"/><service name="ssh"/>
<rule family="ipv4"><source address="192.0.2.0/24"/><accept/></rule>
<future-field value="preserved"/></zone>'''
        self.state['capabilities'] += ['new-zone-from-file', 'path-zone', 'delete-zone']
        request = self.request('duplicate-zone', 'duplicate-lab', 'permanent', documentRevision=hashlib.sha256(document).hexdigest())
        temporary_paths = []
        copied_documents = []
        after = copy.deepcopy(self.state)
        after['scopes']['permanent']['zones'].append(dict(name='duplicate-lab', fields={}))
        def apply(command):
            self.assertEqual(command[0], '--permanent')
            self.assertEqual(command[-1], '--name=duplicate-lab')
            path = Path(command[1].split('=', 1)[1])
            temporary_paths.append(path)
            copied = path.read_bytes()
            copied_documents.append(copied)
            tree = ET.fromstring(copied)
            self.assertEqual(tree.attrib['target'], 'DROP')
            self.assertIn(b'license fixture', copied)
            self.assertEqual(tree.findtext('description'), 'Real metadata')
            self.assertEqual(tree.find('future-field').attrib['value'], 'preserved')
            self.assertIsNone(tree.find('interface'))
            self.assertIsNone(tree.find('source'))
            self.assertIsNotNone(tree.find('rule/source'))
            return 'success'
        self.call.side_effect = apply
        def document_read(name):
            return (copied_documents[-1] if name == 'duplicate-lab' else document), 'vendor'
        with patch.object(self.client, 'zone_document', side_effect=document_read), \
             patch.object(self.client, 'snapshot', side_effect=[self.state, after]):
            self.assertEqual(self.client.handle(request)['operationState'], 'applied')
        self.assertTrue(temporary_paths)
        self.assertFalse(temporary_paths[0].exists())
        self.assertFalse(temporary_paths[0].parent.exists())
        with patch.object(self.client, 'zone_document', return_value=(document, 'custom')):
            request['documentRevision'] = 'old'
            with self.assertRaises(fw.Failure): self.client.command(request, self.state)

    def test_zone_deletion_origin_default_bindings_policies_and_inactive_profiles(self):
        document = b'<zone><short>Unused custom zone</short></zone>'
        self.state['capabilities'] += ['path-zone', 'delete-zone']
        for configuration in self.state['scopes'].values():
            configuration['zones'][0]['fields']['interfaces'] = ''
        self.state['revision'] = fw.revision(self.state)
        request = self.request('delete-zone', None, 'permanent', documentRevision=hashlib.sha256(document).hexdigest())
        with patch.object(self.client, 'zone_document', return_value=(document, 'custom')), \
             patch.object(self.client, 'host_result', return_value=subprocess.CompletedProcess([], 0, '', '')):
            self.assertEqual(self.client.command(request, self.state), ['--permanent', '--delete-zone=custom-lab'])
            for scope in ('runtime', 'permanent'):
                for field in ('interfaces', 'sources'):
                    configuration = self.state['scopes'][scope]
                    configuration['zones'][0]['fields'][field] = 'dependency'
                    with self.assertRaises(ValueError): self.client.command(request, self.state)
                    configuration['zones'][0]['fields'][field] = ''
                configuration['policies'] = [dict(name='policy', fields={'ingress-zones': 'custom-lab'})]
                with self.assertRaises(ValueError): self.client.command(request, self.state)
                configuration['policies'] = []
            self.state['defaultZone'] = 'custom-lab'
            with self.assertRaises(ValueError): self.client.command(request, self.state)
            self.state['defaultZone'] = 'second-zone'
        for origin in ('vendor', 'override'):
            with patch.object(self.client, 'zone_document', return_value=(document, origin)), self.assertRaises(ValueError):
                self.client.command(request, self.state)
        with patch.object(self.client, 'zone_document', return_value=(document, 'custom')):
            with patch.object(self.client, 'host_result', return_value=None), self.assertRaises(ValueError):
                self.client.command(request, self.state)
            results = [subprocess.CompletedProcess([], 0, '11111111-1111-1111-1111-111111111111', ''),
                       subprocess.CompletedProcess([], 0, 'custom-lab', '')]
            with patch.object(self.client, 'host_result', side_effect=results), self.assertRaises(ValueError):
                self.client.command(request, self.state)
        self.call.assert_not_called()

    def test_zone_origin_rejects_arbitrary_paths_before_file_read(self):
        for path in ('/tmp/zone.xml', '/etc/firewalld/zones/../other.xml', '/etc/firewalld/zones/mismatch.xml'):
            self.call.return_value = path
            with patch.object(fw.os, 'open') as opened, self.assertRaises(ValueError):
                self.client.zone_document('custom-lab')
            opened.assert_not_called()

    def test_capabilities_and_read_failures_do_not_fake_success(self):
        self.state['capabilities'] = []
        for action, value in [('new-zone', 'new-lab'), ('add-protocol', 'ah'), ('change-interface', 'radio9')]:
            with self.assertRaises(ValueError): self.client.command(self.request(action, value, 'permanent'), self.state)
        self.call.side_effect = fw.Failure('access-denied', 'Protected inspection')
        result = self.client.handle(dict(action='inspect', kind='ipset', name='lab-set', scope='runtime'))
        self.assertFalse(result['ok'])
        self.assertNotIn('definition', result)
        self.assertFalse(self.client.allow_interaction)

    def test_inventory_and_catalog_changes_invalidate_review(self):
        for key, value in [('connections', [dict(interface='new-interface', canAssign=False)]),
                           ('catalogs', {'runtime': {'services': ['new-service']}})]:
            changed = copy.deepcopy(self.state)
            changed[key] = value
            changed['revision'] = fw.revision(changed)
            with patch.object(self.client, 'snapshot', return_value=changed):
                result = self.client.handle(self.request('add-service', 'custom-service'))
            self.assertFalse(result['ok'])
            self.assertEqual(result['operationState'], 'conflict')
        self.call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
