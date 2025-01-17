# This file is part of curtin. See LICENSE file for copyright and license info.

from curtin.block import lvm

from .helpers import CiTestCase
import mock


class TestBlockLvm(CiTestCase):
    vg_name = 'ubuntu-volgroup'

    @mock.patch('curtin.block.lvm.util')
    def test_filter_lvm_info(self, mock_util):
        """make sure lvm._filter_lvm_info filters properly"""
        match_name = "vg_name"
        query_results = ["lv_1", "lv_2"]
        lvtool_name = 'lvscan'
        query_name = 'lv_name'
        # NOTE: i didn't use textwrap.dedent here on purpose, want to make sure
        #       that the function can handle leading spaces as some of the
        #       tools have spaces before the fist column in their output
        mock_util.subp.return_value = (
            """
            matchfield_bad1{sep}qfield1
            {matchfield_good}{sep}{query_good1}
            matchfield_bad2{sep}qfield2
            {matchfield_good}{sep}{query_good2}
            """.format(matchfield_good=self.vg_name,
                       query_good1=query_results[0],
                       query_good2=query_results[1],
                       sep=lvm._SEP), "")
        result_list = lvm._filter_lvm_info(lvtool_name, match_name,
                                           query_name, self.vg_name)
        self.assertEqual(len(result_list), 2)
        mock_util.subp.assert_called_with(
            [lvtool_name, '-C', '--separator', lvm._SEP, '--noheadings', '-o',
             '{},{}'.format(match_name, query_name)], capture=True)
        self.assertEqual(result_list, query_results)
        # make sure _filter_lvm_info can fail gracefully if no match
        result_list = lvm._filter_lvm_info(lvtool_name, match_name,
                                           query_name, 'bad_match_val')
        self.assertEqual(len(result_list), 0)

    @mock.patch('curtin.block.lvm._filter_lvm_info')
    def test_get_lvm_info(self, mock_filter_lvm_info):
        """
        make sure that the get lvm info functions make the right calls to
        lvm._filter_lvm_info
        """
        lvm.get_pvols_in_volgroup(self.vg_name)
        mock_filter_lvm_info.assert_called_with(
            'pvdisplay', 'vg_name', 'pv_name', self.vg_name)
        lvm.get_lvols_in_volgroup(self.vg_name)
        mock_filter_lvm_info.assert_called_with(
            'lvdisplay', 'vg_name', 'lv_name', self.vg_name)

    @mock.patch('curtin.block.lvm.util')
    def test_split_lvm_name(self, mock_util):
        """
        make sure that split_lvm_name makes the right call to dmsetup splitname
        """
        lv_name = 'root_lvol'
        full_name = '{}-{}'.format(self.vg_name, lv_name)
        mock_util.subp.return_value = (
            '  {vg_name}{sep}{lv_name} '.format(
                vg_name=self.vg_name, lv_name=lv_name, sep=lvm._SEP), '')
        (res_vg_name, res_lv_name) = lvm.split_lvm_name(full_name)
        self.assertEqual(res_vg_name, self.vg_name)
        self.assertEqual(res_lv_name, lv_name)
        mock_util.subp.assert_called_with(
            ['dmsetup', 'splitname', full_name, '-c', '--noheadings',
             '--separator', lvm._SEP, '-o', 'vg_name,lv_name'], capture=True)

    @mock.patch('curtin.block.lvm.lvmetad_running')
    @mock.patch('curtin.block.lvm.util')
    @mock.patch('curtin.block.lvm.distro')
    def test_lvm_scan(self, mock_distro, mock_util, mock_lvmetad):
        """check that lvm_scan formats commands correctly for each release"""
        cmds = [['pvscan'], ['vgscan']]
        for (count, (codename, lvmetad_status, use_cache)) in enumerate(
                [('precise', False, False),
                 ('trusty', False, False),
                 ('xenial', False, False), ('xenial', True, True),
                 (None, True, True), (None, False, False)]):
            mock_distro.lsb_release.return_value = {'codename': codename}
            mock_lvmetad.return_value = lvmetad_status
            lvm.lvm_scan()
            expected = [cmd for cmd in cmds]
            for cmd in expected:
                if lvmetad_status:
                    cmd.append('--cache')

            calls = [mock.call(cmd, capture=True) for cmd in expected]
            self.assertEqual(len(expected), len(mock_util.subp.call_args_list))
            mock_util.subp.has_calls(calls)
            mock_util.subp.reset_mock()

    @mock.patch('curtin.block.lvm.lvmetad_running')
    @mock.patch('curtin.block.lvm.util')
    @mock.patch('curtin.block.lvm.distro')
    def test_lvm_scan_multipath(self, mock_distro, mock_util, mock_lvmetad):
        """check that lvm_scan formats commands correctly for multipath."""
        cmds = [['pvscan'], ['vgscan']]
        mock_distro.lsb_release.return_value = {'codename': 'focal'}
        mock_lvmetad.return_value = False
        lvm.lvm_scan(multipath=True)
        cmd_filter = [
            '--config',
            'devices{ filter = [ "a|%s|", "a|%s|", "r|.*|" ] }' % (
                '/dev/mapper/mpath.*', '/dev/mapper/dm_crypt-.*')
        ]
        expected = [cmd + cmd_filter for cmd in cmds]
        calls = [mock.call(cmd, capture=True) for cmd in expected]
        self.assertEqual(len(expected), len(mock_util.subp.call_args_list))
        mock_util.subp.has_calls(calls)


class TestBlockLvmMultipathFilter(CiTestCase):

    def test_generate_multipath_dev_mapper_filter(self):
        expected = 'filter = [ "a|%s|", "a|%s|", "r|.*|" ]' % (
            '/dev/mapper/mpath.*', '/dev/mapper/dm_crypt-.*')
        self.assertEqual(expected, lvm.generate_multipath_dev_mapper_filter())

    def test_generate_multipath_dm_uuid_filter(self):
        expected = (
            'filter = [ "a|%s|", "a|%s|", "r|.*|" ]' % (
                '/dev/disk/by-id/dm-uuid-.*mpath-.*',
                '/dev/disk/by-id/.*dm_crypt-.*'))
        self.assertEqual(expected, lvm.generate_multipath_dm_uuid_filter())


# vi: ts=4 expandtab syntax=python
